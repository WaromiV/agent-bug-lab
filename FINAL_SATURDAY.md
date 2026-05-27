# Saturday Night Research Summary — 2026-05-24

## Targets Worked

### 1. Optimism ($2M bounty) — 31 bugs, 0 bountiable
- 16 searcher runs across 4 batches
- All findings terminated at dispute game bond mechanics (carved out by scope), admin trust boundaries, or undeployed features
- Severity tiers are brutally narrow: Critical = direct fund loss (not bonds), High = network shutdown or hardfork freeze, Medium = fee vault theft only
- Best finding: bug_000197 (ETHLockbox no per-portal balance tracking, $450M at risk) but requires multi-portal authorization which hasn't happened yet
- Deployed a 24h Telegram monitor on remote server — will alert when multi-portal goes live

### 2. Stacks ($250K bounty) — PROMISING, ongoing
- 10 searcher runs (5 sBTC-focused, 5 stacks-core-focused)
- Much wider attack surface: Rust node + Clarity VM + sBTC Bitcoin bridge + boot contracts

---

## Top Findings (Stacks)

### bug_000224 [HIGH → potentially CRITICAL] — Multisig Script Encoding Mismatch
**Target**: sBTC signer + sbtc-bootstrap-signers.clar
**Impact**: Permanent freezing of ALL sBTC funds when signer set exceeds 16 members

**Mechanism**: The Clarity contract encodes multisig m-of-n parameters as `uint-to-byte(u80 + value)`, producing bytes 0x51-0x60 (Bitcoin OP_1 through OP_16). For n>16, it produces arbitrary non-number-push opcodes (e.g., n=17 → 0x61 = OP_NOP). The Rust signer uses `Builder::push_int()` which correctly switches to PUSHDATA encoding for n>16 (e.g., 17 → [0x01, 0x11]).

Different scripts → different hash160 → different addresses. After a key rotation to >16 signers, the on-chain `current-signer-principal` won't match the Rust wallet's `tx-sender`. All deposit completions, withdrawal processing, and key rotations permanently fail.

**Source verified**:
- Clarity: `sbtc-bootstrap-signers.clar:85` — `uint-to-byte(u80 + m)`
- Rust: `stacks-common/src/deps_common/bitcoin/blockdata/script.rs:549-564` — `push_int` switches encoding at 17
- MAX_KEYS = 128 (signer/src/lib.rs:46), tests verify 90-of-128

**Convergence**: Independently found by 2 of 5 sBTC searchers (bug_000224 + bug_000227)

**Severity mapping**: sBTC Critical — "Permanent freezing of funds" ($250K)

**Open precondition**: Current production signer set size. If <16, bug is latent but activates on next expansion. No cap at 16 exists in code.

---

### bug_000235 [MEDIUM → potentially CRITICAL] — Broken Signature Ordering in Nakamoto Consensus
**Target**: stackslib/src/chainstate/nakamoto/mod.rs
**Impact**: Signer signature order not enforced after first signature → block malleability → potential consensus divergence

**Mechanism**: `verify_signer_signatures()` at line 900-909 tracks `last_index` to enforce ascending signer order, but `last_index` is only assigned inside an `else` branch that executes only on the first iteration. After that, it's never updated — so all subsequent signatures are accepted in any order.

**Severity mapping**: Blockchain Medium ("transient consensus failures") at minimum. If different nodes process reordered signatures differently → "chain split" (Critical, $250K).

**Convergence**: Found by 2 searchers independently (bug_000235 + bug_000238)

---

### bug_000222 [MEDIUM] — Emily API Zero Authentication
**Target**: sbtc/emily/handler
**Impact**: All state-mutation endpoints (POST /new_block, deposit/withdrawal updates) have no application-level auth

**Mechanism**: Security model relies entirely on AWS API Gateway. The application code has zero auth middleware, API key validation, or signature verification. If API Gateway is misconfigured or bypassed, an attacker can inject fake block events, manipulate deposit states, and poison the signer's view of sBTC state.

**Severity mapping**: sBTC Medium — "API crash preventing correct processing of sBTC deposits/withdrawals"

---

## System Improvements Built Today

1. **Static-facts plugin** (slither + forge inspect) — deterministic Solidity ground truth injected into all agents
2. **Monorepo sub-project discovery** — find_solidity_root() auto-detects foundry projects in monorepos
3. **Prepare dossier v2** — severity_tiers, out_of_scope, program_rules extracted verbatim from bounty pages, injected into pro/con/judge
4. **Secondary harness support** — per-side CLI in debates (claude_code pro/judge vs codex con)
5. **Resume disabled** — `use_resume_when_available=false` prevents stale context contamination
6. **Mandatory RPC checks** — agents must verify deployment status + funds at risk before claiming severity
7. **ETHLockbox Telegram monitor** — 24h polling on remote server, alerts on multi-portal activation

## Infrastructure Running

- ETHLockbox monitor: `root@109.123.255.162` tmux session `lockbox`, TG alerts to @bromine636
- Stacks searchers: 10 runs on project_000010, 7/10 complete at time of writing
- All services: postgres:5435, redis:6380, API:8001, vite:5173, arq worker

## Bonus Batch (5 targeted searchers) — additional findings

### bug_000250 [MEDIUM] — sBTC Signer UTXO Drain via saturating_sub
**Target**: signer/src/bitcoin/utxo.rs
**Impact**: `adjust_amounts` uses `saturating_sub` which silently clamps to zero instead of erroring. Crafted fee conditions can drain signer UTXOs to dust, preventing future Bitcoin transaction construction → sBTC operations freeze.
**Severity**: sBTC Medium — "Temporarily freezing sBTC transactions"

### bug_000253 [MEDIUM] — Clarity VM Cost Underpricing (filter/fold)
**Target**: clarity/src/vm/functions/sequences.rs
**Impact**: `special_filter` and `special_fold` cost functions scale incorrectly — cost is independent of sequence length. An attacker can execute O(n) VM operations while paying O(1) cost → block stuffing.
**Severity**: Smart Contract Medium — "block stuffing without fund transfers being blocked"

### bug_000254 [MEDIUM] — Clarity VM Cost Underpricing (map)
**Target**: clarity/src/vm/functions/sequences.rs
**Impact**: Same family as 253. `map` cost scales with number of sequence arguments, not sequence length.
**Severity**: Smart Contract Medium — "block stuffing"

---

## Final Tally

| Severity | Count | Key bugs |
|----------|-------|----------|
| HIGH | 1 | bug_000224 (multisig encoding mismatch) |
| MEDIUM | 6 | bug_000222 (Emily auth), bug_000227 (address derivation), bug_000235 (sig ordering), bug_000250 (UTXO drain), bug_000253 (filter/fold cost), bug_000254 (map cost) |
| LOW | 29 | Various defense-in-depth, DoS, and hardening gaps |
| Total | 36+ | From 15 searcher runs (14 succeeded, 1 scope_id error) |

## Convergence Signals (independently found by multiple searchers)
- **Multisig encoding mismatch**: 2 searchers (bug_000224 + bug_000227)
- **Signature ordering**: 4 searchers (bug_000235 + bug_000238 + bug_000240 + bug_000243)
- **Emily API auth**: 3 searchers (bug_000222 + bug_000228 + bug_000232)

## Next Steps

1. **Debate bug_000224** — the crown jewel. If debate confirms, file immediately as sBTC Critical ($250K)
2. **Verify signer set size** — check Stacks mainnet for current number of active signers (if >16, bug is ALREADY LIVE)
3. **Debate bug_000235** — Nakamoto signature ordering could be Critical if it causes chain splits
4. **File bug_000253/254** — Clarity VM cost underpricing is a clean Medium, easy to PoC
5. **File bug_000250** — UTXO drain is a clean sBTC Medium
