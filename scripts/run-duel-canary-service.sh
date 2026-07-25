#!/usr/bin/env bash
set -euo pipefail

case "${LOOP_TON_NETWORK_ID:-}" in
  -3)
    network=testnet
    first_wallet=loop-canary-a
    second_wallet=loop-canary-b
    ;;
  -239)
    network=mainnet
    first_wallet=loop-mainnet-canary-a
    second_wallet=loop-mainnet-canary-b
    ;;
  *)
    echo "Unsupported LOOP_TON_NETWORK_ID for DUEL canary" >&2
    exit 2
    ;;
esac

exec /usr/bin/python3 scripts/run-duel-canary.py \
  --network "$network" \
  --contract "${LOOP_DUEL_CONTRACT_ADDRESS:?set LOOP_DUEL_CONTRACT_ADDRESS}" \
  --first-wallet "$first_wallet" \
  --second-wallet "$second_wallet"
