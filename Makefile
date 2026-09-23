# Обёртки для команды; те же команды есть в README. GNU Make 3.81: рецепты с табуляцией.
PY   ?= .venv/bin/python
DATA ?= task/data
OUT  ?= outputs

.PHONY: setup pipeline check metrics baselines api contract web

# venv и зависимости пайплайна и API
setup:
	python3 -c 'import sys; v=sys.version_info; assert (3,11) <= (v.major, v.minor) < (3,14), f"нужен Python 3.11–3.13, найден {v.major}.{v.minor}: см. раздел Требования в README"'
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# три CSV в outputs/
pipeline:
	$(PY) -m pipeline.run --data $(DATA) --out $(OUT)

# гейт схемы выгрузок по ТЗ; код 1 при нарушении
check:
	$(PY) -m pipeline.check --data $(DATA) --out $(OUT)

# проверки качества выгрузок без разметки → outputs/metrics.json; код 1 при провале обязательной
metrics:
	$(PY) -m pipeline.metrics --data $(DATA) --out $(OUT) --report $(OUT)/metrics.json --perm 1000

# сравнение с dummy-моделями на прокси-исходах → outputs/baselines.json
baselines:
	$(PY) -m pipeline.baselines --data $(DATA) --out $(OUT) --report $(OUT)/baselines.json

# API на :8000; после make pipeline — POST /reload
api:
	.venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

# openapi.json → клиент фронта → проверка типов
contract:
	$(PY) backend/export_openapi.py && cd dai-front && npm run gen && npm run typecheck

# dev-сервер интерфейса
web:  ## интерфейс: .env.development из примера (если нет), npm ci, dev-сервер на 5173
	cd dai-front && ([ -f .env.development ] || cp .env.example .env.development) && npm ci && npm run dev
