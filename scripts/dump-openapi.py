#!/usr/bin/env python3
"""
dump-openapi.py — Dump the FastAPI OpenAPI schema to contracts/api-contract.yaml
without starting a server. Run from repo root:

    python3 scripts/dump-openapi.py
"""

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure repo root and backend/ are on sys.path so `from main import app` works
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Switch cwd to backend so relative paths inside main.py resolve correctly
import os
os.chdir(BACKEND_DIR)

# ---------------------------------------------------------------------------
# Import the FastAPI app (side effects: load_dotenv, _make_redis_client — safe)
# ---------------------------------------------------------------------------
from main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Generate OpenAPI schema
# ---------------------------------------------------------------------------
schema = app.openapi()
path_count = len(schema.get("paths", {}))

# ---------------------------------------------------------------------------
# Write contracts/api-contract.yaml (prefer yaml, fall back to json)
# ---------------------------------------------------------------------------
contracts_dir = REPO_ROOT / "contracts"
contracts_dir.mkdir(exist_ok=True)

try:
    import yaml  # type: ignore

    out_path = contracts_dir / "api-contract.yaml"
    with out_path.open("w", encoding="utf-8") as fh:
        yaml.dump(schema, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)
    print(f"OK: {out_path.relative_to(REPO_ROOT)} written ({path_count} endpoint paths)")

except ImportError:
    out_path = contracts_dir / "api-contract.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(schema, fh, indent=2, ensure_ascii=False)
    print(f"OK: {out_path.relative_to(REPO_ROOT)} written ({path_count} endpoint paths)")
    print("Note: install pyyaml for YAML output: pip3 install pyyaml")
