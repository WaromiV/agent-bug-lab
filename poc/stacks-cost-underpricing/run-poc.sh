#!/usr/bin/env bash
#
# Run the cost underpricing PoC
#
# Prerequisites:
#   - clarinet installed (cargo install clarinet-cli OR download from
#     https://github.com/hirosystems/clarinet/releases)
#
# Usage:
#   cd poc/stacks-cost-underpricing
#   bash run-poc.sh
#
set -euo pipefail

echo "============================================"
echo "  Clarity VM Cost Underpricing PoC"
echo "  filter / fold / map"
echo "============================================"
echo ""

if ! command -v clarinet &>/dev/null; then
  echo "ERROR: clarinet not found. Install:"
  echo "  cargo install clarinet-cli"
  echo "  OR download from https://github.com/hirosystems/clarinet/releases"
  exit 1
fi

echo "clarinet version: $(clarinet --version)"
echo ""

# Check the contract compiles
echo "--- Checking contract ---"
clarinet check 2>&1
echo ""

echo "--- Running cost comparison in console ---"
echo "Calling filter-small (2 elements) and filter-large (128 elements)..."
echo ""

# Run automated console commands and capture cost receipts
clarinet console <<'EOF'
::set_tx_sender ST1PQHQKV0RJXZFY1DGX8MNSNYVE3VGZJSRTPGZGM
(contract-call? .cost-stuffing filter-small)
(contract-call? .cost-stuffing filter-large)
(contract-call? .cost-stuffing fold-small)
(contract-call? .cost-stuffing fold-large)
(contract-call? .cost-stuffing map-small)
(contract-call? .cost-stuffing map-large)
(contract-call? .cost-stuffing compound-stuffing)
(contract-call? .cost-stuffing stuff-demo)
EOF

echo ""
echo "============================================"
echo "  EXPECTED RESULT:"
echo ""
echo "  filter-small and filter-large should show"
echo "  the SAME filter cost line item (1000)"
echo "  despite 64x difference in work."
echo ""
echo "  fold-small and fold-large: same fold cost."
echo "  map-small and map-large: map cost ~2000 vs"
echo "  correct ~129000."
echo ""
echo "  This proves block stuffing is possible at"
echo "  artificially low cost."
echo "============================================"
