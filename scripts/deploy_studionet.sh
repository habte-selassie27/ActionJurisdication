#!/usr/bin/env bash
set -euo pipefail

CONTRACT="contracts/actionjurisdication.py"
RPC="https://studio.genlayer.com/api"
EXPECTED_CHAIN_ID="61999"

if ! command -v genlayer >/dev/null 2>&1; then
  echo "GenLayer CLI is not installed. Install with: npm install -g genlayer" >&2
  exit 1
fi

if [[ ! -f "$CONTRACT" ]]; then
  echo "Run this script from the repository root." >&2
  exit 1
fi

python scripts/preflight.py

echo "Selecting stable Studionet. Expected chain ID: ${EXPECTED_CHAIN_ID}."
genlayer network set studionet
genlayer network info

echo "Verify the network info above reports chain ID ${EXPECTED_CHAIN_ID}."
echo "Using RPC ${RPC}."
echo "Using the currently selected GenLayer account; no private key is stored in this repository."
genlayer account

genlayer deploy --contract "$CONTRACT" --rpc "$RPC"
