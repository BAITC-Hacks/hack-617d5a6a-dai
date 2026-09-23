#!/usr/bin/env python3
"""Записывает схему API в dai-front/openapi.json. Запуск из backend/: python export_openapi.py"""

import json
from pathlib import Path

from app.main import app

target = Path(__file__).resolve().parents[1] / "dai-front" / "openapi.json"
target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"openapi.json → {target}")
