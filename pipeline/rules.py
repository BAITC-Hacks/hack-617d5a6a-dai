"""Единственное место с порогами ролей и параметрами приоритета v0."""

from __future__ import annotations

# Пороги v0 = стартовые пороги заглушки backend/app/data.py::_mock_role.
THRESHOLDS: dict[str, float] = {
    "coordinator_min_in_deg": 3,
    "coordinator_min_out_deg": 5,
    "distributor_min_out_deg": 10,
    "consolidator_min_in_deg": 3,
    "transit_ratio_low": 0.8,
    "transit_ratio_high": 1.2,
    "terminal_max_depth_exclusive": 4,
    # role_score v0 (нормировки, как в заглушке)
    "coordinator_in_norm": 6,
    "coordinator_out_norm": 10,
    "distributor_out_norm": 25,
    "consolidator_in_norm": 8,
    "terminal_score": 0.5,
    "peripheral_score": 0.3,
    # priority v0 = 0.5*pct(pagerank) + 0.4*pct(in_deg+out_deg) + 0.1*is_seed
    "priority_w_pagerank": 0.5,
    "priority_w_degree": 0.4,
    "priority_w_seed": 0.1,
}

# Порядок проверки ролей: первая сработавшая побеждает.
ROLE_ORDER: list[str] = ["coordinator", "distributor", "consolidator", "transit", "terminal", "peripheral"]

ROLES = ["consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral"]

TOP_N = 50


def thresholds_table() -> str:
    w = max(len(k) for k in THRESHOLDS)
    lines = [f"{'порог'.ljust(w)}  значение", f"{'-' * w}  --------"]
    lines += [f"{k.ljust(w)}  {v:g}" for k, v in THRESHOLDS.items()]
    lines.append(f"{'ROLE_ORDER'.ljust(w)}  {' > '.join(ROLE_ORDER)}")
    return "\n".join(lines)


def print_thresholds() -> None:
    print(thresholds_table())
