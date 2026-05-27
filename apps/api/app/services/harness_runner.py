"""
Harness runner — the ONE place that knows how to invoke external agent CLIs.

Design
------
Each supported CLI is represented by a HarnessSpec subclass. The subclass
owns:
  - how to compose argv for a fresh run vs a resumed run
  - how to deliver the input payload (as a text prompt on stdin)
  - how to extract the model's JSON response from the CLI's output

`run_harness` is the orchestrator: spawn → stream → capture → parse. It is
harness-agnostic and never references CLI-specific flags.

Adding a new harness == adding a new HarnessSpec subclass and entry in
HARNESS_REGISTRY. Nothing else changes (OCP).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


# ── prompt wrapping ─────────────────────────────────────────────────────────
# Real CLIs read a *prompt* (string), not a JSON object. We wrap the JSON
# input into a prompt that instructs the model to follow `objective` exactly
# and emit JSON-only output.
_PROMPT_TEMPLATE = """\
You are operating inside agent-bug-lab, an automated security research workbench.

Your role and detailed instructions are embedded as JSON below. Read the
`role`, `objective`, and `constraints` fields carefully and follow them EXACTLY.

CRITICAL OUTPUT RULES — read these before doing any analysis:
  • Your entire final response must be a single JSON object.
  • No prose. No commentary. No code fences. No preamble.
  • The object must match the output contract described in `objective`.
  • You are READ-ONLY against the repository at `project.repo_path`. Never
    modify, write, execute, or network-call any code in it.

============ AGENT INPUT (JSON) ============
{payload}
============ END AGENT INPUT ============

Begin your JSON response now.
"""


def build_prompt(input_payload: dict[str, Any]) -> str:
    return _PROMPT_TEMPLATE.format(payload=json.dumps(input_payload, indent=2))


# ── JSON extraction (forgiving — strips fences and surrounding prose) ───────
_FENCE_RE = re.compile(r"^```(?:json|JSON)?\s*\n(.*?)\n```\s*$", re.DOTALL)


def parse_model_json(text: str) -> dict[str, Any]:
    """Parse model output to JSON; tolerate code fences and trailing text."""
    stripped = text.strip()
    m = _FENCE_RE.match(stripped)
    if m:
        stripped = m.group(1).strip()
    # Try whole string first
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    # Fall back to first `{...}` block by brace balance
    start = stripped.find("{")
    if start < 0:
        raise json.JSONDecodeError("no '{' found in model output", stripped, 0)
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(stripped)):
        c = stripped[i]
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(stripped[start : i + 1])
    raise json.JSONDecodeError("unbalanced braces in model output", stripped, 0)


# ── harness specs ───────────────────────────────────────────────────────────
class HarnessSpec(ABC):
    name: str = ""
    bin_env: str = ""
    model_arg: str = "--model"
    resume_arg: str = "--resume"
    supports_resume: bool = True
    supports_raw_json: bool = True

    @abstractmethod
    def build_argv(
        self,
        *,
        binary: str,
        model: str,
        resume_session: str | None,
        data_dir: Path,
    ) -> list[str]: ...

    def build_stdin(self, input_payload: dict[str, Any]) -> bytes:
        return build_prompt(input_payload).encode()

    @abstractmethod
    def extract_output(
        self,
        *,
        stdout: str,
        stderr: str,
        exit_code: int,
        data_dir: Path,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Return (parsed_output, parse_error). Exactly one is non-None on success/failure."""
        ...

    def effort_args(self, effort: str | None) -> list[str]:
        """Per-harness effort flag. Default: harness does not expose effort
        as a CLI option (Codex configures it via ~/.codex/config.toml).
        Subclasses override when the CLI accepts a flag."""
        return []


class CodexSpec(HarnessSpec):
    name = "codex"
    bin_env = "CODEX_CLI_BIN"
    model_arg = "-m"
    resume_arg = "resume"  # `codex exec resume <session_id>` is a subcommand
    supports_resume = True
    supports_raw_json = True

    def build_argv(self, *, binary, model, resume_session, data_dir):
        last_msg = data_dir / "codex_last_message.txt"
        base = [
            binary,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "-m",
            model,
            "-o",
            str(last_msg),
            "-",  # read prompt from stdin
        ]
        if resume_session:
            # codex exec resume <session_id> [opts] [PROMPT|-]
            return [
                binary,
                "exec",
                "resume",
                resume_session,
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "-m",
                model,
                "-o",
                str(last_msg),
                "-",
            ]
        return base

    def extract_output(self, *, stdout, stderr, exit_code, data_dir):
        last = data_dir / "codex_last_message.txt"
        text = last.read_text() if last.exists() else stdout
        if not text.strip():
            return None, "codex produced empty output"
        try:
            return parse_model_json(text), None
        except json.JSONDecodeError as e:
            return None, f"codex output not JSON: {e}"


class ClaudeCodeSpec(HarnessSpec):
    name = "claude_code"
    bin_env = "CLAUDE_CODE_CLI_BIN"
    model_arg = "--model"
    resume_arg = "--resume"
    supports_resume = True
    supports_raw_json = True

    def build_argv(self, *, binary, model, resume_session, data_dir):
        argv = [
            binary,
            "-p",
            "--model",
            model,
            "--output-format",
            "json",
            "--permission-mode",
            "bypassPermissions",
        ]
        if resume_session:
            argv += ["--resume", resume_session]
        return argv

    def effort_args(self, effort: str | None) -> list[str]:
        # Claude Code: `--effort low|medium|high|xhigh|max`.
        return ["--effort", effort] if effort else []

    def extract_output(self, *, stdout, stderr, exit_code, data_dir):
        if not stdout.strip():
            return None, "claude produced empty stdout"
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError as e:
            return None, f"claude envelope not JSON: {e}"
        # Claude's --output-format json wraps the result; the model's text
        # is in `.result`.
        result_text = envelope.get("result")
        if not isinstance(result_text, str):
            return None, "claude envelope missing string `result`"
        try:
            payload = parse_model_json(result_text)
        except json.JSONDecodeError as e:
            return None, f"claude result text not JSON: {e}"
        # Bubble up session_id so we can resume.
        sid = envelope.get("session_id")
        if isinstance(sid, str) and "harness_session_id" not in payload:
            payload["harness_session_id"] = sid
        return payload, None


HARNESS_REGISTRY: dict[str, HarnessSpec] = {
    "codex": CodexSpec(),
    "claude_code": ClaudeCodeSpec(),
}


def get_harness(name: str) -> HarnessSpec:
    try:
        return HARNESS_REGISTRY[name]
    except KeyError as e:
        raise ValueError(f"unknown harness: {name!r}") from e


def list_harnesses() -> list[HarnessSpec]:
    return list(HARNESS_REGISTRY.values())


def resolve_binary(spec: HarnessSpec) -> str:
    settings = get_settings()
    fallback = getattr(settings, spec.bin_env.lower(), None)
    return os.environ.get(spec.bin_env) or fallback or spec.name


# ── orchestrator ────────────────────────────────────────────────────────────
@dataclass
class HarnessResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    raw_output: dict[str, Any] | None
    parse_error: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


LineHandler = Callable[[str, str], Awaitable[None]]


async def _stream_reader(
    reader: asyncio.StreamReader | None,
    stream_name: str,
    sink: list[str],
    handler: LineHandler | None,
) -> None:
    if reader is None:
        return
    while True:
        raw = await reader.readline()
        if not raw:
            break
        line = raw.decode(errors="replace").rstrip("\n")
        sink.append(line)
        if handler is not None:
            try:
                await handler(stream_name, line)
            except Exception:  # noqa: BLE001
                log.exception("harness.stream_handler.error", stream=stream_name)


async def run_harness(
    spec: HarnessSpec,
    *,
    model: str,
    input_payload: dict[str, Any],
    data_dir: Path,
    resume_session: str | None = None,
    timeout_seconds: int | None = None,
    on_line: LineHandler | None = None,
    effort: str | None = None,
) -> HarnessResult:
    """Run a harness CLI and return parsed model JSON.

    Writes harness_command.json, input.json, stdout.log, stderr.log,
    output.json into `data_dir`. Streams stdout/stderr line-by-line through
    `on_line` so workers can persist live logs.
    """
    settings = get_settings()
    timeout = timeout_seconds or settings.run_timeout_seconds
    binary = resolve_binary(spec)
    cmd = spec.build_argv(
        binary=binary, model=model, resume_session=resume_session, data_dir=data_dir
    )
    cmd += spec.effort_args(effort)
    stdin_bytes = spec.build_stdin(input_payload)

    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "harness_command.json").write_text(
        json.dumps(
            {
                "harness": spec.name,
                "argv": cmd,
                "shell_repr": " ".join(shlex.quote(c) for c in cmd),
                "stdin": "input.json (as text prompt wrapping the JSON payload)",
                "model": model,
                "effort": effort,
                "resume_session": resume_session,
            },
            indent=2,
        )
    )
    (data_dir / "input.json").write_text(json.dumps(input_payload, indent=2))
    (data_dir / "prompt.txt").write_bytes(stdin_bytes)

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    log.info("harness.process.spawning", argv=cmd, data_dir=str(data_dir))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        return HarnessResult(
            command=cmd,
            exit_code=127,
            stdout="",
            stderr="",
            raw_output=None,
            parse_error=f"harness binary not found: {e}",
        )

    async def _send_input() -> None:
        assert proc.stdin is not None
        try:
            proc.stdin.write(stdin_bytes)
            await proc.stdin.drain()
        finally:
            proc.stdin.close()

    try:
        await asyncio.wait_for(
            asyncio.gather(
                _send_input(),
                _stream_reader(proc.stdout, "stdout", stdout_lines, on_line),
                _stream_reader(proc.stderr, "stderr", stderr_lines, on_line),
                proc.wait(),
            ),
            timeout=timeout,
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        stderr_lines.append(f"[runner] killed after {timeout}s timeout")

    stdout_text = "\n".join(stdout_lines)
    stderr_text = "\n".join(stderr_lines)
    (data_dir / "stdout.log").write_text(stdout_text)
    (data_dir / "stderr.log").write_text(stderr_text)

    raw_output, parse_error = spec.extract_output(
        stdout=stdout_text,
        stderr=stderr_text,
        exit_code=proc.returncode if proc.returncode is not None else -1,
        data_dir=data_dir,
    )

    if raw_output is not None:
        (data_dir / "output.json").write_text(json.dumps(raw_output, indent=2))
    else:
        (data_dir / "output.json").write_text("")

    return HarnessResult(
        command=cmd,
        exit_code=proc.returncode if proc.returncode is not None else -1,
        stdout=stdout_text,
        stderr=stderr_text,
        raw_output=raw_output,
        parse_error=parse_error,
    )


# ── small helpers used by tests and tools ──────────────────────────────────
def build_command(spec: HarnessSpec, *, model: str, resume_session: str | None) -> list[str]:
    """Convenience for unit tests; does not pre-create data_dir."""
    from tempfile import gettempdir

    return spec.build_argv(
        binary=resolve_binary(spec),
        model=model,
        resume_session=resume_session,
        data_dir=Path(gettempdir()),
    )
