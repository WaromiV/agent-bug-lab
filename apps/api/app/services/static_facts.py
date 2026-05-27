"""
Static-facts service — deterministic, no-LLM extraction of Solidity facts
that downstream agents (prepare, searcher, debaters, judge) read verbatim.

Pipeline:
  1. Detect Solidity (foundry.toml or any .sol)
  2. rsync target repo to scratch (out/, cache/, .git/ excluded) — target
     stays untouched per FIXED_REPO_ROOT read-only discipline
  3. soldeer install if soldeer.lock present and dependencies/ missing
  4. forge build with FOUNDRY_BUILD_INFO_LEGACY=1 (forge 1.0+ ships a slim
     build-info; crytic-compile only parses the legacy full standard-json
     format, hence the env var)
  5. Slither(scratch_dir, ignore_compile=True) → callgraph + external
     functions + modifiers + delegatecall sinks via the Python API
  6. `forge inspect <Contract> storageLayout --json` per user contract

Output: a single JSON dict written to <project_dir>/static_facts/facts.json
AND returned to the caller. Persisted onto projects.static_facts so agents
read it from the project row.

Non-goals:
- Detectors (slither's vulnerability findings). Different problem; the LLM
  agents are our finders. We only want raw ground-truth facts here.
- AST embedding / cross-file alias analysis. MDASH does it; we don't.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.core.paths import static_facts_dir, write_json

log = get_logger(__name__)


# ── tunables ──────────────────────────────────────────────────────────
# Soft caps on output size. Agents read this in their input JSON; if it
# blows past ~50 KB the prompt context starts to suffer.
MAX_EXTERNAL_FNS_PER_CONTRACT = 80
MAX_CALLGRAPH_EDGES = 800
MAX_DELEGATECALL_SINKS_PER_CONTRACT = 20
MAX_STORAGE_ENTRIES_PER_CONTRACT = 60

# forge build is the dominant cost (compile time on a medium repo).
FORGE_BUILD_TIMEOUT_SEC = 600
SOLDEER_INSTALL_TIMEOUT_SEC = 300
SLITHER_TIMEOUT_SEC = 300
FORGE_INSPECT_TIMEOUT_SEC = 60

# Paths inside the scratch copy that we always exclude from analysis.
EXCLUDE_PATH_FRAGMENTS = (
    "/dependencies/",
    "/lib/",
    "/test/",
    "/script/",
    "/broadcast/",
    "/node_modules/",
)


class StaticFactsError(RuntimeError):
    """Raised when the pass can't produce ANY useful output. Callers should
    log + persist a stub (errors filled) and continue without facts."""


HARDHAT_CONFIGS = ("hardhat.config.cjs", "hardhat.config.ts", "hardhat.config.js")
SUBPROJECT_SEARCH_MAX_DEPTH = 4


def is_solidity_target(repo_path: Path) -> bool:
    """A Solidity project = a foundry/hardhat root anywhere within the repo
    (up to depth 4, skipping common dep dirs).

    Stricter than "any .sol file": Go projects (e.g. polygon-bor) ship
    .sol test fixtures and ABI codegen samples that would falsely qualify."""
    return find_solidity_root(repo_path) is not None


def find_solidity_root(repo_path: Path) -> Path | None:
    """Return the path to the foundry/hardhat root inside `repo_path`.

    Order of preference:
      1. repo_path itself, if it has foundry.toml or hardhat.config.*
      2. nearest subdir (BFS, up to SUBPROJECT_SEARCH_MAX_DEPTH) with
         foundry.toml — preferred, since slither integrates with foundry
      3. nearest subdir with hardhat config

    Skips common dep dirs (dependencies/, lib/, node_modules/) so we don't
    return e.g. forge-std's own foundry.toml from inside a dependency tree.
    """
    if not repo_path.is_dir():
        return None

    if (repo_path / "foundry.toml").is_file():
        return repo_path
    for cfg in HARDHAT_CONFIGS:
        if (repo_path / cfg).is_file():
            return repo_path

    def _depth(p: Path) -> int:
        try:
            return len(p.relative_to(repo_path).parts)
        except ValueError:
            return 999

    def _not_in_deps(p: Path) -> bool:
        # Skip dep dirs AND obvious test/util/script fixtures inside the
        # monorepo. e2e/testdata/gnosis/script subdirs ship throwaway
        # foundry projects that we never want to pick over the real one.
        s = str(p)
        bad_fragments = EXCLUDE_PATH_FRAGMENTS + (
            "/e2e/", "/e2eutils/", "/testdata/", "/gnosis/",
        )
        return not any(f in s for f in bad_fragments)

    def _candidates(pattern: str) -> list[Path]:
        out = [
            p for p in repo_path.rglob(pattern)
            if _depth(p) <= SUBPROJECT_SEARCH_MAX_DEPTH and _not_in_deps(p)
        ]
        # Rank: shallow wins; tiebreak lexicographic.
        out.sort(key=lambda p: (_depth(p), str(p)))
        return out

    foundry = _candidates("foundry.toml")
    if foundry:
        return foundry[0].parent
    for cfg in HARDHAT_CONFIGS:
        hardhat = _candidates(cfg)
        if hardhat:
            return hardhat[0].parent
    return None


def collect(project_id: str, repo_path: Path) -> dict[str, Any]:
    """Run the full pass for `project_id`. Returns the facts dict.

    Best-effort: every sub-step is wrapped; a failure produces a stub with
    `build_ok=False` + `errors=[...]` so the caller can still persist
    something and the prepare agent isn't blocked.
    """
    out_dir = static_facts_dir(project_id)
    scratch = out_dir / "scratch"
    facts_path = out_dir / "facts.json"

    facts: dict[str, Any] = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "language": "unknown",
        "build_system": None,
        "build_ok": False,
        "build_error": None,
        "solc_root": None,
        "solc_versions": [],
        "tool_versions": {},
        "stats": {},
        "contracts": [],
        "callgraph": {"edges": []},
        "errors": [],
    }

    solidity_root = find_solidity_root(repo_path)
    if solidity_root is None:
        facts["language"] = "non-solidity"
        facts["errors"].append("repo is not a Solidity project (no foundry.toml/hardhat config found)")
        write_json(facts_path, facts)
        return facts

    facts["language"] = "solidity"
    facts["tool_versions"] = _tool_versions()
    # Record the resolved Solidity root relative to repo_path so consumers
    # know whether we're scanning a monorepo sub-project.
    try:
        facts["solc_root"] = str(solidity_root.relative_to(repo_path)) or "."
    except ValueError:
        facts["solc_root"] = str(solidity_root)

    # ── 1. rsync to scratch ──
    try:
        _prepare_scratch(solidity_root, scratch)
    except StaticFactsError as e:
        facts["errors"].append(f"scratch prep: {e}")
        write_json(facts_path, facts)
        return facts

    # ── 2. soldeer install (if applicable) ──
    if (scratch / "soldeer.lock").is_file() and not (scratch / "dependencies").is_dir():
        try:
            _run_soldeer(scratch)
        except StaticFactsError as e:
            facts["errors"].append(f"soldeer: {e}")
            # Keep going — build may still succeed if deps are vendored
            # under lib/ or remappings resolve elsewhere

    # ── 3. forge build (legacy build-info) ──
    facts["build_system"] = "foundry" if (scratch / "foundry.toml").is_file() else "hardhat"
    if facts["build_system"] == "foundry":
        try:
            _run_forge_build(scratch)
            facts["build_ok"] = True
        except StaticFactsError as e:
            facts["build_ok"] = False
            facts["build_error"] = str(e)
            facts["errors"].append(f"forge build: {e}")
            write_json(facts_path, facts)
            return facts
    else:
        facts["build_error"] = "hardhat builds not implemented yet"
        facts["errors"].append("hardhat builds not implemented; first cut is foundry-only")
        write_json(facts_path, facts)
        return facts

    # ── 4. slither python API extraction ──
    try:
        slither_facts = _extract_with_slither(scratch)
        # Multi-compiler-profile foundry builds (e.g. contracts-bedrock's
        # default + dispute + validator profiles) parse the same contract
        # multiple times. Dedupe by (path, name) — same source location
        # means same logical contract; the bytecode-level differences
        # don't change the facts surface we care about.
        seen: set[tuple[str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for c in slither_facts["contracts"]:
            k = (c.get("path", ""), c.get("name", ""))
            if k in seen:
                continue
            seen.add(k)
            deduped.append(c)
        facts["contracts"] = deduped
        facts["callgraph"] = slither_facts["callgraph"]
        facts["solc_versions"] = slither_facts["solc_versions"]
    except StaticFactsError as e:
        facts["errors"].append(f"slither: {e}")

    # ── 5. forge inspect for storage layout per user contract ──
    for c in facts["contracts"]:
        try:
            layout = _forge_inspect_storage(scratch, c["path"], c["name"])
            c["storage_layout"] = layout[:MAX_STORAGE_ENTRIES_PER_CONTRACT]
        except Exception as e:  # noqa: BLE001
            c["storage_layout"] = []
            facts["errors"].append(f"forge inspect {c['name']}: {e}")

    # ── 6. compute stats ──
    facts["stats"] = {
        "user_contracts": len(facts["contracts"]),
        "external_functions": sum(len(c.get("external_functions", [])) for c in facts["contracts"]),
        "callgraph_edges": len(facts["callgraph"]["edges"]),
        "delegatecall_sinks": sum(
            len(c.get("delegatecall_sinks", [])) for c in facts["contracts"]
        ),
        "storage_entries": sum(len(c.get("storage_layout", [])) for c in facts["contracts"]),
    }

    write_json(facts_path, facts)
    log.info(
        "static_facts.done",
        project_id=project_id,
        **facts["stats"],
        errors=len(facts["errors"]),
    )
    return facts


# ── implementation details ────────────────────────────────────────────


def _prepare_scratch(src: Path, scratch: Path) -> None:
    """Mirror target repo into a writable scratch dir. We never touch the
    original target — `data/targets/<repo>/` stays read-only by discipline.

    `--delete` keeps scratch in sync if source changes, BUT we exclude the
    `dependencies/` directory from both transfer AND deletion. Reason:
    soldeer reaches out to S3 (https://soldeer-revisions.s3.amazonaws.com)
    which intermittently times out. If we wiped + redownloaded every run,
    a single soldeer flake would brick every static_facts pass on the
    project until the bucket is happy again. Persisting dependencies/
    across runs makes the second run a cheap forge-build refresh.
    """
    if not shutil.which("rsync"):
        raise StaticFactsError("rsync not on PATH")
    scratch.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "rsync", "-a", "--delete",
        "--exclude=out",
        "--exclude=cache",
        "--exclude=.git",
        "--exclude=node_modules",
        "--exclude=dependencies",
        f"{src}/",
        f"{scratch}/",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise StaticFactsError(f"rsync failed: {r.stderr.strip()[:400]}")

    # Drop test/tests dirs entirely. forge --skip 'test/**/*' still parses
    # imports inside test files (it's a "don't compile this target"
    # filter, not a "don't see this file" filter), so test files
    # importing now-deleted scripts/* break compilation. Removing the
    # dirs makes the build cleanly src + lib + surviving scripts/libraries.
    for dirname in ("test", "tests"):
        target = scratch / dirname
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
    # Aggressive scripts/ pruning. Foundry `scripts/` trees are typically
    # tangled orchestration code that pulls in test/mocks/ and forge
    # cheatcodes. We don't need any of it for src-level facts — but src
    # sometimes imports library-style helpers (e.g. contracts-bedrock's
    # src/libraries/Predeploys.sol imports scripts/libraries/Config.sol).
    #
    # Strategy: walk scripts/ once, delete anything whose `import` lines
    # reach back into test/ or *.s.sol. Whatever survives compiles cleanly
    # because its only deps are forge-std / lib / src.
    scripts_dir = scratch / "scripts"
    if scripts_dir.is_dir():
        _prune_tangled_scripts(scripts_dir)
    # Foundry script entry-points anywhere (*.s.sol) — never imported by
    # src or library code; safe to drop.
    for s_sol in scratch.rglob("*.s.sol"):
        try:
            s_sol.unlink()
        except OSError:
            pass


def _prune_tangled_scripts(scripts_dir: Path) -> None:
    """Iteratively delete script .sol files whose imports are unresolvable.

    Three taint criteria:
      1. Imports `test/...` (test trees are removed earlier).
      2. Imports anything ending `.s.sol` (script entry-points are removed).
      3. Imports `scripts/...` where the target file no longer exists in
         the scratch tree (transitive tangle from earlier deletions).

    Runs until a pass makes no deletions, so deletion cascades through the
    dependency graph (A imports B; B gets deleted on pass N; A gets
    deleted on pass N+1).

    Files that survive only import from forge-std / lib / src / surviving
    scripts/libraries files, so the build can resolve them.
    """
    import re
    import_re = re.compile(r'^\s*import\s+.*?from\s+["\']([^"\']+)["\']', re.MULTILINE)
    scratch_root = scripts_dir.parent
    while True:
        deleted_any = False
        for sol in list(scripts_dir.rglob("*.sol")):
            if not sol.exists():
                continue
            try:
                text = sol.read_text(errors="ignore")
            except OSError:
                continue
            bad = False
            for m in import_re.finditer(text):
                path = m.group(1)
                if path.startswith("test/") or path.startswith("./test/") or "/test/" in path:
                    bad = True
                    break
                if path.endswith(".s.sol"):
                    bad = True
                    break
                # Imports that reference scripts/<x> where <x> no longer
                # exists on disk — transitive tangle.
                if path.startswith("scripts/"):
                    candidate = scratch_root / path
                    if not candidate.is_file():
                        bad = True
                        break
            if bad:
                try:
                    sol.unlink()
                    deleted_any = True
                except OSError:
                    pass
        if not deleted_any:
            return


def _run_soldeer(scratch: Path) -> None:
    r = subprocess.run(
        ["forge", "soldeer", "install"],
        cwd=scratch,
        capture_output=True, text=True,
        timeout=SOLDEER_INSTALL_TIMEOUT_SEC,
    )
    if r.returncode != 0:
        raise StaticFactsError(f"soldeer install failed: {(r.stderr or r.stdout).strip()[:400]}")


def _run_forge_build(scratch: Path) -> None:
    """forge build with build-info pinned at out/build-info.

    Two foundry-side knobs cause slither integration to break if left at
    the project's own values:
      • `out` (default 'out'). Some monorepos override this — e.g.
        contracts-bedrock uses 'forge-artifacts'.
      • `build_info_path` (default '<out>/build-info'). contracts-bedrock
        sends it to 'artifacts/build-info' which decouples from out_path.

    crytic-compile hardcodes `<out>/build-info` as the build-info location,
    so we force both via CLI flags. We also set FOUNDRY_BUILD_INFO_LEGACY=1
    because forge 1.0+ ships a slim build-info that crytic-compile can't
    parse; the legacy env flag re-emits the full standard-json shape.
    """
    import os
    full_env = {**os.environ, "FOUNDRY_BUILD_INFO_LEGACY": "1"}
    r = subprocess.run(
        [
            "forge", "build",
            "--out", "out",
            "--build-info",
            "--build-info-path", "out/build-info",
            # Skip test/ trees: tests aren't in our static-facts surface
            # AND projects regularly have test fixtures that won't compile
            # without infrastructure we don't reproduce (forge-std cheatcodes
            # mocks, etc). Do NOT skip script/: contracts-bedrock's src
            # imports from scripts/libraries/Config.sol — skipping breaks
            # src too.
            "--skip", "test/**/*",
            "--skip", "tests/**/*",
            "--force",
        ],
        cwd=scratch,
        capture_output=True, text=True,
        env=full_env,
        timeout=FORGE_BUILD_TIMEOUT_SEC,
    )
    if r.returncode != 0:
        combined = (r.stderr or "") + (r.stdout or "")

        # Some solc versions aren't available on aarch64. When forge
        # fails to install a version, it exits non-zero and writes NO
        # build-info — even for the versions that compiled fine.
        # Fix: parse the failing version, delete the .sol files that
        # require it, and retry. The lost files are typically old/legacy
        # contracts that aren't the primary audit surface.
        import re
        bad_versions = re.findall(
            r"Failed to install solc (\d+\.\d+\.\d+)", combined
        )
        if bad_versions:
            # Find and delete .sol files whose pragma matches the bad version
            deleted = 0
            for sol in scratch.rglob("*.sol"):
                try:
                    text = sol.read_text(errors="ignore")
                except OSError:
                    continue
                for ver in bad_versions:
                    # Match exact version or range that resolves to it
                    if f"solidity {ver}" in text or f"solidity <={ver}" in text:
                        sol.unlink()
                        deleted += 1
                        break
            if deleted > 0:
                log.info(
                    "static_facts.forge.skip_bad_solc",
                    versions=bad_versions,
                    deleted_files=deleted,
                )
                # Retry without the problem files
                r2 = subprocess.run(
                    [
                        "forge", "build",
                        "--out", "out",
                        "--build-info",
                        "--build-info-path", "out/build-info",
                        "--skip", "test/**/*",
                        "--skip", "tests/**/*",
                        "--force",
                    ],
                    cwd=scratch,
                    capture_output=True, text=True,
                    env=full_env,
                    timeout=FORGE_BUILD_TIMEOUT_SEC,
                )
                if r2.returncode == 0:
                    return
                # Check partial
                bi_dir = scratch / "out" / "build-info"
                if bi_dir.is_dir() and any(bi_dir.iterdir()):
                    return
                combined = (r2.stderr or "") + (r2.stdout or "")

        msg = combined[-800:].strip()
        raise StaticFactsError(f"forge build failed: {msg}")


def _extract_with_slither(scratch: Path) -> dict[str, Any]:
    """Use slither's Python API for everything except storage layout.

    Slither requires the foundry build-info to already exist (we passed
    `--ignore-compile`-equivalent via ignore_compile=True). Filtering of
    dependency contracts happens by source-mapping path, NOT slither's
    own --filter-paths (we want the contracts gone from `slither.contracts`
    iteration, not just from the printer output)."""
    try:
        from slither import Slither
        from slither.slithir.operations import HighLevelCall, LowLevelCall
    except ImportError as e:
        raise StaticFactsError(f"slither python API not importable: {e}") from e

    try:
        # `foundry_out_directory='out'` aligns with the explicit --out flag
        # we passed to forge build. Without this slither would read out_path
        # from the project's foundry.toml — which the project may set to
        # something other than 'out' (e.g. contracts-bedrock's
        # 'forge-artifacts').
        slither = Slither(str(scratch), ignore_compile=True, foundry_out_directory="out")
    except Exception as e:  # noqa: BLE001
        raise StaticFactsError(f"slither parse failed: {e}") from e

    solc_versions = sorted({
        cu.compiler_version.version
        for cu in slither.compilation_units
        if cu.compiler_version and cu.compiler_version.version
    })

    def is_user(c: Any) -> bool:
        try:
            p = c.source_mapping.filename.absolute
        except Exception:  # noqa: BLE001
            return False
        return not any(frag in p for frag in EXCLUDE_PATH_FRAGMENTS)

    user_contracts = [c for c in slither.contracts if is_user(c)]
    log.info("static_facts.slither.parsed", contracts=len(user_contracts))

    contracts_out: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []

    for c in user_contracts:
        # skip pure interfaces — they have no implementation facts of interest
        if c.is_interface:
            continue

        rel_path = _rel_path(c.source_mapping.filename.absolute, scratch)

        external_fns: list[dict[str, Any]] = []
        for f in c.functions_entry_points:
            try:
                mutability = (
                    "view" if f.view else
                    "pure" if f.pure else
                    "payable" if f.payable else
                    "nonpayable"
                )
                mods = [m.name for m in f.modifiers]
                external_fns.append({
                    "name": f.name,
                    "signature": f.full_name,
                    "visibility": f.visibility,
                    "mutability": mutability,
                    "modifiers": mods,
                    "is_constructor": f.is_constructor,
                })
            except Exception as e:  # noqa: BLE001
                log.warning("static_facts.fn.skipped", contract=c.name, error=str(e))

        # cap
        external_fns = external_fns[:MAX_EXTERNAL_FNS_PER_CONTRACT]

        # delegatecall sinks (also low-level call/staticcall — those move
        # ETH or read arbitrary state, all interesting for debate)
        delegatecall_sinks: list[dict[str, Any]] = []
        for f in c.functions:
            for node in f.nodes:
                for ir in node.irs:
                    if isinstance(ir, LowLevelCall):
                        # ir.function_name can be a slither Constant; coerce
                        fn = str(getattr(ir, "function_name", "") or "")
                        if fn in ("delegatecall", "staticcall", "call"):
                            try:
                                line0 = int(node.source_mapping.lines[0])
                            except Exception:  # noqa: BLE001
                                line0 = 0
                            delegatecall_sinks.append({
                                "in_function": f.full_name,
                                "kind": fn,
                                "file": rel_path,
                                "line": line0,
                            })
                            if len(delegatecall_sinks) >= MAX_DELEGATECALL_SINKS_PER_CONTRACT:
                                break
                if len(delegatecall_sinks) >= MAX_DELEGATECALL_SINKS_PER_CONTRACT:
                    break

        # modifier definitions (this contract's own — useful for showing
        # auth surface in one glance)
        modifier_defs = [m.name for m in c.modifiers if m.contract == c]

        # inheritance chain for context
        inherits = [base.name for base in c.inheritance]

        contracts_out.append({
            "name": c.name,
            "path": rel_path,
            "is_abstract": c.is_abstract,
            "inherits": inherits,
            "external_functions": external_fns,
            "modifier_definitions": modifier_defs,
            "delegatecall_sinks": delegatecall_sinks,
            "storage_layout": [],  # filled by forge inspect later
        })

        # callgraph: only HighLevelCalls between USER contracts (so we
        # don't drown in dep-internal edges)
        user_contract_names = {c2.name for c2 in user_contracts}
        for f in c.functions:
            for node in f.nodes:
                for ir in node.irs:
                    if isinstance(ir, HighLevelCall):
                        callee_contract = None
                        callee_fn = None
                        try:
                            callee_fn = ir.function.full_name if ir.function else None
                            if ir.function and getattr(ir.function, "contract", None):
                                callee_contract = ir.function.contract.name
                        except Exception:  # noqa: BLE001
                            pass
                        if callee_contract and callee_contract in user_contract_names and callee_fn:
                            edges.append({
                                "from": f"{c.name}.{f.full_name}",
                                "to": f"{callee_contract}.{callee_fn}",
                            })

    # dedupe + cap edges
    seen: set[tuple[str, str]] = set()
    unique_edges: list[dict[str, str]] = []
    for e in edges:
        k = (e["from"], e["to"])
        if k not in seen:
            seen.add(k)
            unique_edges.append(e)
    unique_edges = unique_edges[:MAX_CALLGRAPH_EDGES]

    return {
        "contracts": contracts_out,
        "callgraph": {"edges": unique_edges},
        "solc_versions": solc_versions,
    }


def _forge_inspect_storage(scratch: Path, contract_path: str, contract_name: str) -> list[dict[str, Any]]:
    """`forge inspect <path>:<Name> storageLayout --json` for one contract.

    Skips silently on stateless contracts (libraries/interfaces): forge
    returns empty storage. Errors bubble up as exceptions handled by caller.
    """
    target = f"{contract_path}:{contract_name}"
    r = subprocess.run(
        ["forge", "inspect", target, "storageLayout", "--json"],
        cwd=scratch,
        capture_output=True, text=True,
        timeout=FORGE_INSPECT_TIMEOUT_SEC,
    )
    if r.returncode != 0:
        # forge inspect fails on libraries and stateless contracts; that's
        # fine, return empty
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    out: list[dict[str, Any]] = []
    for entry in data.get("storage", []):
        out.append({
            "slot": int(entry.get("slot", 0)),
            "offset": int(entry.get("offset", 0)),
            "label": entry.get("label", ""),
            "type": _resolve_storage_type(entry.get("type", ""), data.get("types", {})),
        })
    return out


def _resolve_storage_type(type_id: str, types: dict[str, Any]) -> str:
    """Walk forge's `t_*` type encoding back to a human label.

    forge encodes types like `t_mapping(t_uint16,t_struct(...)_storage)`. The
    `types` table has a `label` field for each. Prefer that; fall back to
    the raw encoding."""
    entry = types.get(type_id)
    if entry and entry.get("label"):
        return entry["label"]
    return type_id


def _rel_path(absolute: str, scratch: Path) -> str:
    try:
        return str(Path(absolute).resolve().relative_to(scratch.resolve()))
    except Exception:  # noqa: BLE001
        return absolute


def _tool_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    try:
        import slither  # type: ignore[import-not-found]
        versions["slither"] = getattr(slither, "__version__", "unknown")
    except Exception:  # noqa: BLE001
        pass
    try:
        r = subprocess.run(
            ["forge", "--version"], capture_output=True, text=True, timeout=5
        )
        first = (r.stdout or "").splitlines()[0] if r.stdout else ""
        if first:
            versions["forge"] = first.replace("forge Version: ", "").strip()
    except Exception:  # noqa: BLE001
        pass
    versions["python"] = sys.version.split()[0]
    return versions


AGENT_SUMMARY_MAX_CONTRACTS = 200


def to_agent_summary(facts: dict[str, Any] | None) -> dict[str, Any] | None:
    """Compact summary to inject into agent raw_input JSON.

    For small repos (sPOL: 10 contracts) this is the full facts. For large
    monorepos (contracts-bedrock: 200+ unique contracts) we filter:
      - drop contracts under lib/ vendor/ scripts/ (deps/utilities, not
        in-scope for any bounty)
      - drop contracts with empty external surface AND no delegatecall
        sinks (pure-internal helpers; agents don't reason about them)
      - cap at AGENT_SUMMARY_MAX_CONTRACTS by ext-function count desc
    storage_layout is summarized to {slot, label, type} (drops offset/
    astId for context-window economy).
    """
    if not facts or facts.get("language") != "solidity":
        return None
    contracts_in = facts.get("contracts", [])
    # Filter
    def keep(c: dict[str, Any]) -> bool:
        path = c.get("path", "")
        if any(seg in path for seg in ("lib/", "vendor/", "scripts/")):
            return False
        if not c.get("external_functions") and not c.get("delegatecall_sinks"):
            return False
        return True
    filtered = [c for c in contracts_in if keep(c)]
    # Rank by external-surface size (proxy for "how attackable")
    filtered.sort(
        key=lambda c: (len(c.get("delegatecall_sinks", [])) * 10 + len(c.get("external_functions", []))),
        reverse=True,
    )
    capped = filtered[:AGENT_SUMMARY_MAX_CONTRACTS]
    truncated = len(filtered) > len(capped)

    return {
        "version": facts.get("version"),
        "generated_at": facts.get("generated_at"),
        "build_ok": facts.get("build_ok"),
        "solc_root": facts.get("solc_root"),
        "stats": facts.get("stats", {}),
        "solc_versions": facts.get("solc_versions", []),
        "contracts_truncated": truncated,
        "contracts": [
            {
                "name": c["name"],
                "path": c["path"],
                "is_abstract": c.get("is_abstract", False),
                "inherits": c.get("inherits", []),
                "external_functions": c.get("external_functions", []),
                "modifier_definitions": c.get("modifier_definitions", []),
                "delegatecall_sinks": c.get("delegatecall_sinks", []),
                "storage_layout_summary": [
                    {"slot": s["slot"], "label": s["label"], "type": s["type"]}
                    for s in c.get("storage_layout", [])
                ],
            }
            for c in capped
        ],
        "callgraph": facts.get("callgraph", {"edges": []}),
        "errors": facts.get("errors", []),
    }
