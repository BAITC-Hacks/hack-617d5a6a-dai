"""Единственное место с порогами ролей и параметрами приоритета (v1; ключи v0 оставлены для стоп-крана).

Квантили в комментариях посчитаны 23.09.2026 по 2 248 узлам task/data (все узлы, включая изоляты
и 444 граничных узла глубины 4). Пороги стартовые: при уточнении менять только здесь.
Таблица для README: python3 -c "from pipeline.rules import print_thresholds; print_thresholds()"
"""

from __future__ import annotations

THRESHOLDS: dict[str, float] = {
    # --- роли v1 (и v0: пороги совпадают с заглушкой backend/app/data.py::_mock_role)
    "coordinator_min_in_deg": 3,          # in_deg: P90/P95/P99 = 2/3/6; 91,1 % узлов ниже 3
    "coordinator_min_out_deg": 5,         # out_deg: P90/P95/P99 = 3/5/23,5; 94,2 % узлов ниже 5
    "coordinator_min_seed_upstream": 2,   # n_seed_upstream: P25 = 1, P50 = 7; 27,3 % узлов ниже 2
    "coordinator_betweenness_q": 0.99,    # альтернативная ветка: betweenness ≥ P99 среди узлов
                                          # с in_deg ≥ 2 и out_deg ≥ 2 (196 узлов, P99 ≈ 0,0061)
    "coordinator_betweenness_min_deg": 2,
    "distributor_min_out_deg": 10,        # out_deg ≈ P97 (97,2 % узлов ниже 10)
    "consolidator_min_in_deg": 3,         # in_deg P95
    "transit_ratio_low": 0.8,             # out_kzt/in_kzt ∈ [0,8; 1,2] (72 узла) или быстрый транзит
    "transit_ratio_high": 1.2,
    "terminal_min_in_deg": 1,             # in_deg P5 < 1: 1,9 % узлов без входов
    "terminal_max_depth_exclusive": 4,    # глубина 4 — граница выгрузки, исходящие не собирались
    "peripheral_score": 0.3,              # role_score периферии фиксирован
    # --- только v0 (нормировки role_score заглушки)
    "coordinator_in_norm": 6,
    "coordinator_out_norm": 10,
    "distributor_out_norm": 25,
    "consolidator_in_norm": 8,
    "terminal_score": 0.5,
    # --- priority v0 = 0.5*pct(pagerank) + 0.4*pct(in_deg+out_deg) + 0.1*is_seed
    "priority_w_pagerank": 0.5,
    "priority_w_degree": 0.4,
    "priority_w_seed": 0.1,
}

# Порядок проверки ролей: первая сработавшая побеждает.
ROLE_ORDER: list[str] = ["coordinator", "distributor", "consolidator", "transit", "terminal", "peripheral"]

ROLES = ["consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral"]

ROLE_RU: dict[str, str] = {
    "consolidator": "консолидатор",
    "transit": "транзит",
    "distributor": "распределитель",
    "terminal": "конечный получатель",
    "coordinator": "координатор",
    "peripheral": "периферия",
}
ROLE_TYPOLOGY: dict[str, str] = {
    "consolidator": "fan-in",
    "transit": "pass-through",
    "distributor": "fan-out",
    "terminal": "sink",
    "coordinator": "gather-scatter",
    "peripheral": "без типовой схемы",
}

TOP_N = 50

# --- приоритет v1 (ECOD-подобный): c_j = -ln P(X_j ≥ x), priority_raw = Σ c_j + вес · fast_transit_flag
SCORE_TERMS: list[str] = ["in_kzt", "out_kzt", "in_deg", "out_deg", "betweenness", "pass_kzt", "n_seed_upstream"]
SCORE_WEIGHTS: dict[str, float] = dict.fromkeys(SCORE_TERMS, 1.0)
# у граничных узлов глубины 4 исходящие не наблюдаемы: эти вклады обнуляются
BOUNDARY_ZERO_TERMS: list[str] = ["out_kzt", "out_deg", "pass_kzt"]
PRIORITY_THRESHOLD_RAW = 6.0   # «два признака выше P95»: 2 · (−ln 0,05) = 5,99
FAST_TRANSIT_WEIGHT = 1.0

# --- быстрый транзит (контракт pipeline/temporal.py; здесь — для run_meta и текстов)
FAST_TRANSIT = {"ratio_low": 0.8, "ratio_high": 1.2, "lag_min_days": 0, "lag_max_days": 2, "min_pairs": 2}


def thresholds_table() -> str:
    """Таблица порогов в Markdown (для README) с квантилем из комментария к ключу."""
    notes = _threshold_notes()
    lines = ["| порог | значение | где на распределении |", "|---|---|---|"]
    v0_only = {"coordinator_in_norm", "coordinator_out_norm", "distributor_out_norm", "consolidator_in_norm",
               "terminal_score", "priority_w_pagerank", "priority_w_degree", "priority_w_seed"}
    lines += [f"| `{k}` | {v:g} | {'только v0 (запасной метод)' if k in v0_only else notes.get(k, '')} |"
              for k, v in THRESHOLDS.items()]
    lines.append(f"| `ROLE_ORDER` | {' > '.join(ROLE_ORDER)} | первая сработавшая роль |")
    lines.append(f"| `PRIORITY_THRESHOLD_RAW` | {PRIORITY_THRESHOLD_RAW:g} | два признака выше P95 |")
    lines.append(f"| `FAST_TRANSIT_WEIGHT` | {FAST_TRANSIT_WEIGHT:g} | добавка к priority_raw при флаге |")
    return "\n".join(lines)


def _threshold_notes() -> dict[str, str]:
    """Комментарии после ключей THRESHOLDS из исходника (один источник — сам файл)."""
    import re
    from pathlib import Path

    notes: dict[str, str] = {}
    for line in Path(__file__).read_text(encoding="utf-8").splitlines():
        m = re.match(r'\s*"(\w+)":\s*[\d.]+,\s*#\s*(.+)$', line)
        if m:
            notes[m.group(1)] = m.group(2).replace("|", "/")
    return notes


def print_thresholds() -> None:
    print(thresholds_table())
