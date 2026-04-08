#!/bin/bash
set -e

# Determine repo root relative to this script so it works from any directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

CONTRACT_FILE="$REPO_ROOT/contracts/api-contract.yaml"
TYPES_OUT="$REPO_ROOT/frontend/js/types.d.ts"

# Temp file cleaned up on exit regardless of success/failure
TMP_JSON=""
trap 'rm -f "$TMP_JSON"' EXIT

if [ -f "$CONTRACT_FILE" ]; then
    echo "Verwende contracts/api-contract.yaml (kein Server erforderlich)..."

    # Convert YAML → temp JSON file, then pass to openapi-typescript
    TMP_JSON=$(mktemp /tmp/api-contract-XXXXXX.json)
    python3 -c "import yaml, json, sys; print(json.dumps(yaml.safe_load(sys.stdin)))" \
        < "$CONTRACT_FILE" > "$TMP_JSON"

    npx openapi-typescript "$TMP_JSON" --output "$TYPES_OUT"
else
    echo "Starte lokalen Server (contracts/api-contract.yaml nicht gefunden)..."
    cd "$REPO_ROOT/backend"
    uvicorn main:app --host 127.0.0.1 --port 18765 &
    SERVER_PID=$!
    sleep 2

    npx openapi-typescript http://127.0.0.1:18765/openapi.json \
        --output "$TYPES_OUT"

    kill $SERVER_PID
fi

echo "Done: frontend/js/types.d.ts"
