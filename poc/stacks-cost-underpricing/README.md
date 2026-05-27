# PoC: Clarity VM Cost Underpricing — filter/fold/map

## Bug Summary

The Clarity VM cost functions for `filter`, `fold`, and `map` do not scale
with input size, enabling block stuffing at artificially low cost.

- `cost_filter(n)` returns constant 1000 regardless of n (costs.clar:161)
- `cost_fold(n)` returns constant 1000 regardless of n (costs.clar:173)  
- `cost_map(n)` scales with n but receives `args.len()` (2-3) instead of
  sequence length (sequences.rs:198)

## Severity

Smart Contract Medium — "Any block stuffing without fund transfers being
blocked" / "Any block stuffing such that smart contract calls can be blocked
but without paying any requisite higher transaction fees"

## Reproduction

```bash
cd poc/stacks-cost-underpricing
clarinet console
```

Then in the REPL:

```clarity
;; Call filter on a 2-element list
(contract-call? .cost-stuffing filter-small)
;; Note the runtime cost in the receipt

;; Call filter on a 128-element list (64x more work)
(contract-call? .cost-stuffing filter-large)
;; Note the runtime cost — filter line item is IDENTICAL (1000 both times)

;; Demonstrate block stuffing: fill a block cheaply
(contract-call? .cost-stuffing stuff-block)
;; This executes 10 nested filter-large calls for ~10,000 filter cost
;; but performs ~1,280 actual VM iterations
```

## Root Cause

File: `clarity/src/vm/functions/sequences.rs`

```rust
// Line 75 — passes 0 instead of sequence length
runtime_cost(ClarityCostFunction::Filter, exec_state, 0)?;

// Line 146 — same for fold
runtime_cost(ClarityCostFunction::Fold, exec_state, 0)?;

// Line 198 — passes arg count instead of sequence length
runtime_cost(ClarityCostFunction::Map, exec_state, args.len())?;
```

File: `stackslib/src/chainstate/stacks/boot/costs.clar`

```clarity
;; Line 161 — cost function ignores n entirely
(define-read-only (cost_filter (n uint))
    (runtime u1000))

;; Line 173 — same
(define-read-only (cost_fold (n uint))
    (runtime u1000))
```

## Mainnet Verification

```
Node: stacks-node 3.4.0.0.0 (b041055)
cost_filter(0) on mainnet boot contract: runtime = 1000 (0x03e8)
cost_filter(1000) on mainnet boot contract: runtime = 1000 (constant)
```

## Impact

An attacker can deploy contracts that execute expensive filter/fold/map
operations while paying only the base cost. This enables:
1. Block stuffing — filling blocks with cheap but computationally heavy txs
2. Crowding out legitimate transactions
3. Compounding via nested calls: fold(filter(map(...)))

No funds at direct risk. Network usability is degraded.
