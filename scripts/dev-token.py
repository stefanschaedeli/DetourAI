#!/usr/bin/env python3
"""Generiert ein JWT für lokales API-Debugging. Kein laufender Server nötig.

Usage:  TOKEN=$(python3 scripts/dev-token.py)
        curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/travels
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

from utils.auth import create_access_token

print(create_access_token(1, "admin", True))
