# Polygon Heimdall v2 placeholder vote-extension suppression PoC

## Summary

A malicious Heimdall v2 block proposer can replace an honest validator's signed
vote extension with a commit-flagged empty placeholder. Honest validators accept
the proposal because `ValidateVoteExtensionsCompleteness` only checks that each
committing validator is present with `BlockIDFlagCommit`; it does not verify that
the extension payload is present or matches the locally observed extended commit.

The placeholder is then skipped by both `ValidateVoteExtensions` and
`aggregateVotes`, so the validator's side-tx vote disappears from the tally. If a
side-tx has just over two-thirds YES support, suppressing less than one-third of
voting power flips the side-tx from approved to skipped while the proposal still
has enough non-placeholder signed vote-extension power to pass validation.

## Affected Code

Local target checkout used for the executable PoC:

`apps/api/data/project_project_000008/static_facts/scratch/heimdall-v2`

Important: this local scratch directory is not authoritative for release
metadata; its `.git` remote points at the lab repository. The vulnerable code
shape was therefore cross-checked against upstream GitHub:

- `0xPolygon/heimdall-v2@v0.7.1`
- `0xPolygon/heimdall-v2@develop`

Both contain the same relevant placeholder/completeness/ProcessProposal logic.
Older sampled releases (`v0.6.0`, `v0.5.6`, `v0.4.5`, `v0.3.1`) do not contain
the Phuket placeholder/completeness path in this form.

Relevant code paths:

- `app/abci.go:152-174`: `ProcessProposal` trusts the proposer-supplied
  `ExtendedCommitInfo` from `req.Txs[0]`.
- `app/vote_ext_utils.go:209-245`: `ValidateVoteExtensionsCompleteness` checks
  only validator presence and `BlockIDFlagCommit`.
- `app/vote_ext_utils.go:81-86`: `ValidateVoteExtensions` skips filtered
  placeholders before signature and payload validation.
- `app/vote_ext_utils.go:200-204`: proposal validation requires only remaining
  non-placeholder signed voting power to be greater than two-thirds.
- `app/vote_ext_utils.go:617-634`: side-tx approval requires YES voting power to
  be greater than two-thirds.
- `app/vote_ext_utils.go:652-656`: `aggregateVotes` also skips placeholders, so
  their side-tx votes are not counted.
- `app/vote_ext_utils.go:802-808`: a placeholder is exactly
  `BlockIDFlagCommit` plus all four extension/signature byte fields empty.

## Mainnet Applicability Check

Release `v0.7.1` is the public Phuket hardfork release and its GitHub release
notes state:

- Mainnet `phuketHardforkHeight = 44070000`
- Amoy `phuketHardforkHeight = 32276400`

The same constants are present in upstream `helper/config.go`.

The public Heimdall mainnet API reported:

```text
chain_id: heimdallv2-137
latest_block_height: 45838187
latest_block_time: 2026-05-25T21:21:24.785242397Z
application_version.name: heimdall
application_version.version: v0.2.9-polygon
```

So mainnet is already past `44070000`. The public node reports
`application_version.version = v0.2.9-polygon`, but that is also the
`github.com/0xPolygon/cosmos-sdk v0.2.9-polygon` replacement used by
`heimdall-v2@v0.7.1`. The live node's dependency fingerprint matches
`v0.7.1`-era Heimdall:

- live CometBFT: `v0.38.19`
- live Cosmos SDK: `v0.50.14`, replaced by `github.com/0xPolygon/cosmos-sdk
  v0.2.9-polygon`
- live go-ethereum: `v1.15.0`
- live Go version: `go1.26.2`

Those match the public `v0.7.1` `go.mod` values. The public `v0.2.9` Heimdall
tag uses older dependencies (`go1.24.4`, CometBFT `v0.38.17`, Cosmos SDK
`v0.50.13`) and does not match the live node fingerprint.

Mainnet consensus params also report:

```text
vote_extensions_enable_height = 24404501
```

The latest mainnet height checked was `45838487`, so vote extensions are active.

A live block decode was performed with:

```bash
go run poc/polygon-heimdall-placeholder-suppression/tools/decode_live_extended_commit.go
```

Result:

```text
chain_id=heimdallv2-137
height=45838487
block_txs=1
tx0_decodes_as=abci.ExtendedCommitInfo
extended_commit_votes=104
commit_flag_votes=104
filtered_placeholder_votes=0
first_vote_extension_bytes=160
first_extension_signature_bytes=65
first_non_rp_vote_extension_bytes=55
first_non_rp_extension_signature_bytes=65
```

This confirms the live chain is carrying proposer-supplied
`ExtendedCommitInfo` as tx index 0, with real vote extension payloads and
signatures, which is the exact proposal surface exercised by the PoC.

Mainnet contract/system-address checks performed directly via RPC:

- Heimdall `/chainmanager/params` reports Ethereum addresses for POL token,
  staking manager, slash manager, root chain, staking info, and state sender.
  `eth_getCode` on Ethereum mainnet returned non-empty code for all of them.
- Heimdall `/chainmanager/params` reports Polygon system addresses
  `0x0000000000000000000000000000000000001000` and
  `0x0000000000000000000000000000000000001001`; `eth_getCode` on Polygon RPC
  returned non-empty code for both.
- Ethereum `StakingManager.validatorThreshold()` returned `105`.
- Ethereum `StakingManager.currentValidatorSetSize()` returned `104`.
  Heimdall `/stake/validators-set` also returned `104` active validators.

## PoC

Two PoC tests were added. The first is the minimal mechanism proof:

`apps/api/data/project_project_000008/static_facts/scratch/heimdall-v2/app/poc_placeholder_suppression_test.go`

Run:

```bash
cd apps/api/data/project_project_000008/static_facts/scratch/heimdall-v2
go test -vet=off ./app -run TestPoCPlaceholderSuppressionFlipsApprovedSideTxToSkipped -count=1 -v
```

Expected result:

```text
--- PASS: TestPoCPlaceholderSuppressionFlipsApprovedSideTxToSkipped
PASS
ok  	github.com/0xPolygon/heimdall-v2/app
```

The test constructs four validators with total voting power 100:

- validator 0: 34 power, YES
- validator 1: 32 power, YES
- validator 2: 4 power, YES
- validator 3: 30 power, NO

Baseline tally: YES power is 70, so the side-tx is approved because
`70 > floor(100 * 2 / 3)`.

Attack tally: the proposer blanks validator 2's vote extension and both
signatures while keeping `BlockIDFlagCommit`. The forged entry satisfies
`isFilteredPlaceholder`. `ValidateVoteExtensionsCompleteness` accepts it because
the validator is still present with a commit flag. `ValidateVoteExtensions`
accepts the proposal because remaining signed non-placeholder power is 96, which
is still greater than two-thirds. `tallyVotes` then sees only 66 YES power and
30 NO power for the side-tx, so the side-tx is skipped.

The second is a multi-node ABCI E2E proof:

`apps/api/data/project_project_000008/static_facts/scratch/heimdall-v2/app/e2e_placeholder_suppression_test.go`

Run:

```bash
cd apps/api/data/project_project_000008/static_facts/scratch/heimdall-v2
go test -vet=off ./app -run TestE2EMultiNodePlaceholderSuppressionAcceptedByHonestNodes -count=1 -v
```

What it proves:

- Creates four independent `HeimdallApp` instances, representing four honest
  validators/nodes with the same genesis validator set.
- Uses real signed vote extensions and non-RP vote extensions from the shared
  validator private keys.
- Creates an honest baseline where the side-tx is approved with 70/100 YES
  voting power.
- Replaces one 4-power YES vote extension with a commit-flagged empty
  placeholder.
- Sends the forged `ExtendedCommitInfo` through each node's real
  `NewProcessProposalHandler`.
- All honest nodes return `ResponseProcessProposal_ACCEPT`.
- Running the same commit through each node's validator-set tally flips the
  side-tx from approved to skipped.

Expected high-signal output:

```text
honest baseline: side-tx ...0001dead approved with 70/100 voting power
honest-node-1 accepted forged proposal with validator 3 replaced by a filtered placeholder
honest-node-2 accepted forged proposal with validator 3 replaced by a filtered placeholder
honest-node-3 accepted forged proposal with validator 3 replaced by a filtered placeholder
honest-node-4 accepted forged proposal with validator 3 replaced by a filtered placeholder
forged proposal: side-tx ...0001dead skipped after YES power drops from 70 to 66 while signed non-placeholder power remains 96/100
--- PASS: TestE2EMultiNodePlaceholderSuppressionAcceptedByHonestNodes
```

## Verification Performed

Targeted PoC:

```bash
go test -vet=off ./app -run TestPoCPlaceholderSuppressionFlipsApprovedSideTxToSkipped -count=1 -v
```

Result: passed.

Multi-node ABCI E2E PoC:

```bash
go test -vet=off ./app -run TestE2EMultiNodePlaceholderSuppressionAcceptedByHonestNodes -count=1 -v
```

Result: passed.

Combined local verification:

```bash
go test -vet=off ./app -run 'Test(PoCPlaceholderSuppressionFlipsApprovedSideTxToSkipped|E2EMultiNodePlaceholderSuppressionAcceptedByHonestNodes)$' -count=1 -v
```

Result: passed.

Adjacent vote-extension tests:

```bash
go test -vet=off ./app -run 'Test(PoCPlaceholderSuppressionFlipsApprovedSideTxToSkipped|ValidateVoteExtensionsCompleteness|IsFilteredPlaceholder|TallyVotes)$' -count=1 -v
```

Result: passed.

GitHub duplicate checks:

```bash
gh issue list --repo 0xPolygon/heimdall-v2 --search "placeholder vote extension ExtendedCommitInfo" --state all --limit 20
gh pr list --repo 0xPolygon/heimdall-v2 --search "placeholder vote extension ExtendedCommitInfo" --state all --limit 20
gh issue list --repo 0xPolygon/heimdall-v2 --search "ValidateVoteExtensionsCompleteness" --state all --limit 20
gh pr list --repo 0xPolygon/heimdall-v2 --search "ValidateVoteExtensionsCompleteness" --state all --limit 20
```

Result: no matching issues or PRs returned.

## Impact

During blocks it proposes, a validator can suppress selected honest side-tx YES
votes without forging signatures and without omitting validators from the
extended commit. This can flip checkpoint, state-sync, stake/signer update,
validator join/exit, or topup side-txs from approved to skipped when support is
near the two-thirds threshold. It does not flip every side-tx with broad support:
the side-tx must have enough YES voting power above two-thirds that it is
approved honestly, but not so much above two-thirds that it remains approved
after the attacker's suppressible voting power is removed.

A single proposer gets intermittent censorship power; a large-stake or
colluding proposer set can repeatedly delay specific cross-chain state updates.

This is best framed as censorship/liveness degradation, not direct fund theft or
a permanent chain halt.

## Suggested Fix

Do not treat unsigned empty placeholders as indistinguishable from legitimate
validator output unless their legitimacy is bound to a local or consensus
verifiable source.

Concrete options:

- In `ProcessProposal`, compare the proposer-supplied `ExtendedCommitInfo`
  payloads against the node's locally observed extended commit when available.
- Make `ValidateVoteExtensionsCompleteness` reject commit-flag entries with empty
  extension/signature fields unless there is a signed, verifiable reason that the
  entry was filtered.
- Include the filtering decision in a signature- or hash-bound artifact so a
  proposer cannot manufacture placeholders for arbitrary validators.
