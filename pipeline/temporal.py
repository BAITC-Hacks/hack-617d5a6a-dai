"""Временной слой: пары «вход в B, выход из B» и быстрый транзит 1-к-1.

Пара у узла B: входящий перевод A→B и исходящий B→C, A ≠ C.
lag_days = день выхода − день входа (даты с точностью до дня, порядок внутри дня неизвестен).

- pairs_for_node(tx_df, gid): пары узла для карточки (отношение out/in в [0,8; 1,2], |лаг| ≤ 3 дня).
- fast_transit(tx_df, nodes=None): жадное сопоставление 1-к-1 внутри узла, лаг 0–2 дня,
  отношение 0,8–1,2; флаг = пар ≥ 2.
- all_pairs(tx_df): все пары (A ≠ C) без фильтров, для проверок.

Модуль не зависит от остальных файлов pipeline/ и от backend. Сопоставление векторизовано
(используется и в temporal_check.py на 1 000 перестановок дат).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RATIO_LO = 0.8
RATIO_HI = 1.2
CARD_MAX_ABS_LAG = 3          # окно пар в карточке узла
FAST_LAG_MIN = 0              # быстрый транзит: лаг 0–2 дня
FAST_LAG_MAX = 2
FAST_MIN_PAIRS = 2            # fast_transit_flag = pairs ≥ 2
_EPS = 1e-9

STATUS_FORWARD = "вход раньше выхода"
STATUS_SAME_DAY = "тот же день, порядок неизвестен"
STATUS_REVERSED = "выход раньше входа"


def chronology_status(lag_days):
    """Статус пары по лагу (скаляр или массив)."""
    lag = np.asarray(lag_days)
    out = np.where(lag > 0, STATUS_FORWARD, np.where(lag == 0, STATUS_SAME_DAY, STATUS_REVERSED))
    return out.item() if out.ndim == 0 else out


def prep_tx(tx_df: pd.DataFrame) -> pd.DataFrame:
    """Нормализует переводы: src/dst int64, day = номер дня от 1970-01-01, tx_id = 0..n-1.

    Порядок строк фиксируется сортировкой (date, src, dst, sum_kzt), как в load.py,
    поэтому результат не зависит от порядка строк на входе.
    """
    t = pd.DataFrame({
        "src": tx_df["src"].astype("int64").to_numpy(),
        "dst": tx_df["dst"].astype("int64").to_numpy(),
        "date": pd.to_datetime(tx_df["date"]).dt.normalize().to_numpy(),
        "sum_kzt": tx_df["sum_kzt"].astype(float).to_numpy(),
    })
    t = t.sort_values(["date", "src", "dst", "sum_kzt"], kind="mergesort").reset_index(drop=True)
    t["day"] = (t["date"].to_numpy().astype("datetime64[D]").astype("int64")).astype("int64")
    t["tx_id"] = np.arange(len(t), dtype=np.int64)
    return t


def _pairs_frame(t: pd.DataFrame, exclude_return: bool = True) -> pd.DataFrame:
    """Все пары (вход в B, выход из B) по подготовленным переводам t (без фильтра сумм и лага)."""
    ins = t[["tx_id", "src", "dst", "day", "sum_kzt"]].rename(columns={
        "tx_id": "in_id", "src": "in_src", "dst": "gid", "day": "in_day", "sum_kzt": "in_sum"})
    outs = t[["tx_id", "src", "dst", "day", "sum_kzt"]].rename(columns={
        "tx_id": "out_id", "src": "gid", "dst": "out_dst", "day": "out_day", "sum_kzt": "out_sum"})
    p = ins.merge(outs, on="gid", how="inner", sort=False)
    if exclude_return:
        p = p[p.in_src.to_numpy() != p.out_dst.to_numpy()]
    p = p.sort_values(["gid", "in_id", "out_id"], kind="mergesort").reset_index(drop=True)
    p["ratio"] = p.out_sum / p.in_sum
    p["lag_days"] = (p.out_day - p.in_day).astype("int64")
    return p


def _ratio_ok(ratio) -> np.ndarray:
    r = np.asarray(ratio, dtype=float)
    return (r >= RATIO_LO - _EPS) & (r <= RATIO_HI + _EPS)


def greedy_match(key_in: np.ndarray, key_out: np.ndarray, *order_keys: np.ndarray) -> np.ndarray:
    """Жадное сопоставление 1-к-1: кандидаты по порядку order_keys (lexsort: последний ключ старший),
    кандидат принимается, если ни его вход key_in, ни выход key_out ещё не заняты.

    Векторизовано раундами: принимается кандидат, первый по порядку среди живых и по входу, и по
    выходу; конфликтующие с принятыми удаляются. Результат совпадает с последовательной жадностью
    (кандидат, первый среди соседей, последовательная жадность тоже принимает — по индукции).
    Возвращает булеву маску принятых кандидатов в исходном порядке.
    """
    n = len(key_in)
    accepted = np.zeros(n, dtype=bool)
    if n == 0:
        return accepted
    order = np.lexsort(order_keys) if order_keys else np.arange(n)
    ki = np.asarray(key_in, dtype=np.int64)[order]
    ko = np.asarray(key_out, dtype=np.int64)[order]
    # сжать ключи в плотные номера, чтобы рабочие массивы были небольшими
    ui, ki = np.unique(ki, return_inverse=True)
    uo, ko = np.unique(ko, return_inverse=True)
    best_i = np.empty(len(ui), dtype=np.int64)
    best_o = np.empty(len(uo), dtype=np.int64)
    idx = np.arange(n, dtype=np.int64)   # позиция в порядке жадности
    used_i = np.zeros(len(ui), dtype=bool)
    used_o = np.zeros(len(uo), dtype=bool)
    acc_sorted = np.zeros(n, dtype=bool)
    while len(idx):
        a_i, a_o = ki[idx], ko[idx]
        # первый по порядку на каждом ключе: запись в обратном порядке, выигрывает последняя запись
        best_i[a_i[::-1]] = idx[::-1]
        best_o[a_o[::-1]] = idx[::-1]
        take = (best_i[a_i] == idx) & (best_o[a_o] == idx)
        acc = idx[take]
        acc_sorted[acc] = True
        used_i[ki[acc]] = True
        used_o[ko[acc]] = True
        keep = ~take & ~used_i[a_i] & ~used_o[a_o]
        idx = idx[keep]
    accepted[order] = acc_sorted
    return accepted


def _fast_candidates(p: pd.DataFrame, lag: np.ndarray | None = None) -> np.ndarray:
    lag = p.lag_days.to_numpy() if lag is None else lag
    return _ratio_ok(p.ratio.to_numpy()) & (lag >= FAST_LAG_MIN) & (lag <= FAST_LAG_MAX)


def _match_pairs(p: pd.DataFrame) -> np.ndarray:
    """Маска пар p, вошедших в быстрый транзит (сопоставление внутри узла: вход и выход — разные ключи)."""
    cand = _fast_candidates(p)
    matched = np.zeros(len(p), dtype=bool)
    c = p[cand]
    if len(c):
        dev = np.round(np.abs(c.ratio.to_numpy() - 1.0), 9)
        m = greedy_match(c.in_id.to_numpy(), c.out_id.to_numpy(),
                         c.out_id.to_numpy(), c.in_id.to_numpy(), c.lag_days.to_numpy(), dev)
        matched[np.flatnonzero(cand)[m]] = True
    return matched


def all_pairs(tx_df: pd.DataFrame, exclude_return: bool = True) -> pd.DataFrame:
    """Все пары (вход A→B, выход B→C) по всем узлам без фильтров сумм и лага.

    Колонки: gid, in_id, out_id, in_src, out_dst, in_day, out_day, in_date, out_date, in_sum, out_sum,
    ratio, lag_days, ratio_ok, chronology_status, fast_candidate, matched_1to1.
    exclude_return=False оставляет возвраты A→B→A (на данных кейса 38 311 пар против 34 105).
    """
    t = prep_tx(tx_df)
    p = _pairs_frame(t, exclude_return=exclude_return)
    p["in_date"] = pd.to_datetime(p.in_day, unit="D").dt.strftime("%Y-%m-%d")
    p["out_date"] = pd.to_datetime(p.out_day, unit="D").dt.strftime("%Y-%m-%d")
    p["ratio_ok"] = _ratio_ok(p.ratio.to_numpy())
    p["chronology_status"] = chronology_status(p.lag_days.to_numpy())
    p["fast_candidate"] = _fast_candidates(p)
    p["matched_1to1"] = _match_pairs(p) if exclude_return else False
    return p


def fast_transit(tx_df: pd.DataFrame, nodes=None) -> pd.DataFrame:
    """DataFrame[gid, fast_transit_pairs, fast_transit_flag] по узлам.

    nodes — DataFrame с колонкой gid или последовательность gid: тогда в результате все эти узлы
    (0 пар и False у остальных) в их порядке. Без nodes — только узлы, встречающиеся в переводах.
    """
    t = prep_tx(tx_df)
    p = _pairs_frame(t)
    matched = _match_pairs(p)
    cnt = p.loc[matched].groupby("gid").size()
    if nodes is None:
        gids = pd.Index(np.unique(np.r_[t.src.to_numpy(), t.dst.to_numpy()]), dtype="int64")
    else:
        g = nodes["gid"] if isinstance(nodes, pd.DataFrame) else pd.Series(list(nodes))
        gids = pd.Index(g.astype("int64").to_numpy())
    pairs = cnt.reindex(gids, fill_value=0).astype(int).to_numpy()
    return pd.DataFrame({
        "gid": gids.to_numpy(),
        "fast_transit_pairs": pairs,
        "fast_transit_flag": pairs >= FAST_MIN_PAIRS,
    })


def pairs_for_node(tx_df: pd.DataFrame, gid) -> list[dict]:
    """Пары узла для карточки: A ≠ C, out/in ∈ [0,8; 1,2], |лаг| ≤ 3 дня.

    Поля: in_src, out_dst (gid строкой), in_date, out_date (YYYY-MM-DD), in_sum, out_sum, lag_days,
    chronology_status, matched_1to1 (пара вошла в быстрый транзит узла).
    Сопоставление 1-к-1 локально для узла, поэтому считается по его переводам и совпадает с fast_transit.
    Порядок: по дате входа, дате выхода, затем по суммам.
    """
    g = int(gid)
    src = tx_df["src"].astype("int64")
    dst = tx_df["dst"].astype("int64")
    sub = tx_df.loc[(src == g) | (dst == g)]
    if sub.empty:
        return []
    t = prep_tx(sub)
    p = _pairs_frame(t)
    p = p[p.gid == g]
    if p.empty:
        return []
    matched = _match_pairs(p)
    keep = _ratio_ok(p.ratio.to_numpy()) & (p.lag_days.abs().to_numpy() <= CARD_MAX_ABS_LAG)
    p = p.assign(matched_1to1=matched)[keep]
    p = p.sort_values(["in_day", "out_day", "in_sum", "out_sum", "in_src", "out_dst"], kind="mergesort")
    in_date = pd.to_datetime(p.in_day, unit="D").dt.strftime("%Y-%m-%d").to_numpy()
    out_date = pd.to_datetime(p.out_day, unit="D").dt.strftime("%Y-%m-%d").to_numpy()
    status = chronology_status(p.lag_days.to_numpy()) if len(p) else np.array([], dtype=object)
    return [
        {
            "in_src": str(int(r.in_src)),
            "out_dst": str(int(r.out_dst)),
            "in_date": str(in_date[i]),
            "out_date": str(out_date[i]),
            "in_sum": float(r.in_sum),
            "out_sum": float(r.out_sum),
            "lag_days": int(r.lag_days),
            "chronology_status": str(status[i]),
            "matched_1to1": bool(r.matched_1to1),
        }
        for i, r in enumerate(p.itertuples(index=False))
    ]
