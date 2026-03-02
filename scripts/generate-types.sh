#!/bin/bash
set -e
echo "Starting FastAPI server for OpenAPI spec..."
cd backend
uvicorn main:app --host 127.0.0.1 --port 18765 &
SERVER_PID=$!
sleep 2

echo "Generating TypeScript types..."
npx openapi-typescript http://127.0.0.1:18765/openapi.json \
    --output ../frontend/js/types.d.ts

kill $SERVER_PID
echo "Done: frontend/js/types.d.ts"
