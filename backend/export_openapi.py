#!/usr/bin/env python3
"""Записывает схему API в dai-front/openapi.json.

Запуск из корня репозитория:  python backend/export_openapi.py
или из backend/:              python export_openapi.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.main import app  # noqa: E402

target = ROOT / "dai-front" / "openapi.json"
target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"openapi.json → {target}")
