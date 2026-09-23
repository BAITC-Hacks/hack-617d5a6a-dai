"""Гейт выгрузок по ТЗ §5, §7 (инварианты — docs/execution_plan_2026-09-23.md §3.3).

    python -m pipeline.check --data task/data --out outputs [--require-method v1]

Ожидаемые числа (узлы, seed, оборот) берутся из parquet, не из констант.
Печатает таблицу проверок; код возврата 1, если хоть одна провалена.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

ROLES = {"consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral"}
FILES = ("nodes_roles.csv", "clusters.csv", "top_nodes.csv")
NODE_COLS = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]
CLUSTER_COLS = ["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"]
TOP_COLS = ["rank", "gid", "role", "priority_score", "why"]
MIN_TOP = 20
EVIDENCE_MAX = 200
ROLE_SCORE_MIN_UNIQUE = 5      # role_score «не константа» внутри роли: столько разных значений
ROLE_SCORE_MIN_ROLES = 3       # ... хотя бы у стольких ролей


class _Report:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, name: str, ok: bool, value="", expected="", note: str = "") -> bool:
        self.rows.append({"name": name, "ok": bool(ok), "value": value,
                          "expected": expected, "note": note})
        return bool(ok)


def _examples(values, k: int = 3) -> str:
    vals = list(values)
    if not vals:
        return ""
    return "напр. " + ", ".join(str(v) for v in vals[:k])


def _parse_gids(s) -> list[int]:
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return []
    return [int(x.strip()) for x in str(s).replace(";", ",").split(",") if x.strip()]


def _has_digit(s: pd.Series) -> pd.Series:
    return s.str.contains(r"\d", regex=True)


def _text(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str)


def _check_nodes(rep: _Report, roles: pd.DataFrame, nodes: pd.DataFrame, edges: pd.DataFrame) -> bool:
    missing = [c for c in NODE_COLS if c not in roles.columns]
    if not rep.add("nodes_roles: колонки", not missing, ",".join(missing) or "все",
                   ",".join(NODE_COLS), "обязательные колонки ТЗ"):
        return False
    rep.add("nodes_roles: порядок колонок", list(roles.columns[:len(NODE_COLS)]) == NODE_COLS,
            ",".join(roles.columns[:len(NODE_COLS)]), ",".join(NODE_COLS), "обязательные идут первыми")

    n_exp = len(nodes)
    rep.add("nodes_roles: число строк", len(roles) == n_exp, len(roles), n_exp)

    dup = roles.gid[roles.gid.duplicated()]
    rep.add("nodes_roles: gid уникальны", dup.empty, int(dup.size), 0, _examples(dup))
    got, exp = set(roles.gid.tolist()), set(nodes.gid.tolist())
    extra, lost = sorted(got - exp), sorted(exp - got)
    rep.add("nodes_roles: gid = nodes.parquet", not extra and not lost,
            f"лишних {len(extra)}, нет {len(lost)}", "0 / 0",
            _examples(extra + lost))

    bad_role = roles.role[~roles.role.isin(ROLES)]
    rep.add("nodes_roles: role из словаря", bad_role.empty, int(bad_role.size), 0,
            _examples(sorted(set(bad_role.astype(str)))))

    for col in ("role_score", "priority_score"):
        v = pd.to_numeric(roles[col], errors="coerce")
        bad = roles.gid[v.isna() | (v < 0) | (v > 1)]
        rng = f"[{v.min():.4f}; {v.max():.4f}]" if v.notna().any() else "нет чисел"
        rep.add(f"nodes_roles: {col} в [0;1] без NaN", bad.empty,
                f"{int(bad.size)} вне, {rng}", "0", _examples(bad))

    cid = pd.to_numeric(roles.cluster_id, errors="coerce")
    bad_c = roles.gid[cid.isna() | (cid.fillna(0) % 1 != 0)]
    rep.add("nodes_roles: cluster_id целый без NaN", bad_c.empty, int(bad_c.size), 0, _examples(bad_c))

    ev = _text(roles.evidence)
    checks = [
        ("непустой", ev.str.strip().str.len() > 0),
        (f"≤{EVIDENCE_MAX} символов", ev.str.len() <= EVIDENCE_MAX),
        ("содержит цифру", _has_digit(ev)),
        ("без перевода строки", ~ev.str.contains(r"[\r\n]", regex=True)),
        ("без «mock»", ~ev.str.contains("mock", case=False, regex=False)),
    ]
    for label, mask in checks:
        bad = roles.gid[~mask]
        rep.add(f"nodes_roles: evidence {label}", bad.empty, int(bad.size), 0, _examples(bad))

    # артефакт обхода: у узлов глубины 4 исходящие не выгружены — terminal им ставить нельзя
    out_deg = edges.groupby("src").size()
    boundary = nodes[(nodes.depth == 4) & (nodes.gid.map(out_deg).fillna(0) == 0)].gid
    term = roles[roles.role == "terminal"].gid
    bad_t = sorted(set(boundary) & set(term))
    rep.add("nodes_roles: depth=4 без исходящих не terminal", not bad_t, len(bad_t), 0,
            f"граничных узлов {len(boundary)}; " + _examples(bad_t))
    return True


def _check_clusters(rep: _Report, clusters: pd.DataFrame, roles: pd.DataFrame,
                    nodes: pd.DataFrame, edges: pd.DataFrame) -> None:
    missing = [c for c in CLUSTER_COLS if c not in clusters.columns]
    if not rep.add("clusters: колонки", not missing, ",".join(missing) or "все", ",".join(CLUSTER_COLS)):
        return
    dup = clusters.cluster_id[clusters.cluster_id.duplicated()]
    rep.add("clusters: cluster_id уникальны", dup.empty, int(dup.size), 0, _examples(dup))

    c_nodes = set(pd.to_numeric(roles.cluster_id, errors="coerce").dropna().astype("int64"))
    c_file = set(pd.to_numeric(clusters.cluster_id, errors="coerce").dropna().astype("int64"))
    only_n, only_c = sorted(c_nodes - c_file), sorted(c_file - c_nodes)
    rep.add("clusters: cluster_id = nodes_roles", not only_n and not only_c,
            f"нет в clusters {len(only_n)}, пустых {len(only_c)}", "0 / 0", _examples(only_n + only_c))

    n_exp, s_exp = len(nodes), int(nodes.is_seed.sum())
    rep.add("clusters: sum(n_nodes)", int(clusters.n_nodes.sum()) == n_exp, int(clusters.n_nodes.sum()), n_exp)
    rep.add("clusters: sum(n_seed)", int(clusters.n_seed.sum()) == s_exp, int(clusters.n_seed.sum()), s_exp)

    # пересчёт по nodes_roles + parquet
    j = roles[["gid", "cluster_id"]].merge(nodes[["gid", "is_seed"]], on="gid", how="left")
    j["cluster_id"] = pd.to_numeric(j.cluster_id, errors="coerce")
    j = j.dropna(subset=["cluster_id"])
    j["cluster_id"] = j.cluster_id.astype("int64")
    calc = j.groupby("cluster_id").agg(n_nodes=("gid", "size"), n_seed=("is_seed", "sum"))
    cf = clusters.assign(cluster_id=pd.to_numeric(clusters.cluster_id, errors="coerce")) \
                 .dropna(subset=["cluster_id"]).astype({"cluster_id": "int64"}).set_index("cluster_id")
    common = cf.index.intersection(calc.index)
    for col in ("n_nodes", "n_seed"):
        diff = [c for c in common if int(cf.at[c, col]) != int(calc.at[c, col])]
        rep.add(f"clusters: {col} = подсчёт по узлам", not diff, len(diff), 0, _examples(diff))

    turnover = float(edges.sum_kzt.sum())
    vol = pd.to_numeric(clusters.sum_kzt_internal, errors="coerce")
    bad_v = clusters.cluster_id[vol.isna() | (vol < 0) | (vol > turnover + 0.01)]
    rep.add("clusters: 0 ≤ sum_kzt_internal ≤ оборот", bad_v.empty, int(bad_v.size), 0,
            f"оборот {turnover:,.0f} KZT; Σ internal {vol.sum():,.0f}; " + _examples(bad_v))

    members = j.groupby("cluster_id").gid.agg(set).to_dict()
    bad_top, bad_parse, empty_top = [], [], []
    for r in clusters.itertuples(index=False):
        try:
            gids = _parse_gids(r.top_gids)
        except (ValueError, TypeError):
            bad_parse.append(r.cluster_id)
            continue
        if not gids:
            empty_top.append(r.cluster_id)
        try:
            key = int(r.cluster_id)
        except (ValueError, TypeError):
            key = None
        if not set(gids) <= members.get(key, set()):
            bad_top.append(r.cluster_id)
    rep.add("clusters: top_gids парсится (int64 через запятую)", not bad_parse, len(bad_parse), 0,
            _examples(bad_parse))
    rep.add("clusters: top_gids ⊂ узлов кластера", not bad_top, len(bad_top), 0, _examples(bad_top))
    rep.add("clusters: top_gids непустой", not empty_top, len(empty_top), 0, _examples(empty_top))

    hyp = _text(clusters.hypothesis)
    bad_h = clusters.cluster_id[hyp.str.strip().str.len() == 0]
    rep.add("clusters: hypothesis непустой", bad_h.empty, int(bad_h.size), 0, _examples(bad_h))
    bad_m = clusters.cluster_id[hyp.str.contains("mock", case=False, regex=False)]
    rep.add("clusters: hypothesis без «mock»", bad_m.empty, int(bad_m.size), 0, _examples(bad_m))


def _check_top(rep: _Report, top: pd.DataFrame, roles: pd.DataFrame) -> None:
    missing = [c for c in TOP_COLS if c not in top.columns]
    if not rep.add("top_nodes: колонки", not missing, ",".join(missing) or "все", ",".join(TOP_COLS)):
        return
    rep.add("top_nodes: строк ≥20", len(top) >= MIN_TOP, len(top), f"≥{MIN_TOP}")
    rank = pd.to_numeric(top["rank"], errors="coerce")
    exp_rank = list(range(1, len(top) + 1))
    rep.add("top_nodes: rank = 1..N", rank.tolist() == exp_rank,
            f"{rank.min():.0f}..{rank.max():.0f}" if len(top) else "пусто", f"1..{len(top)}")
    ps = pd.to_numeric(top.priority_score, errors="coerce")
    rises = int((ps.diff() > 0).sum())
    rep.add("top_nodes: priority_score не возрастает", rises == 0 and ps.notna().all(), rises, 0,
            "NaN в priority_score" if ps.isna().any() else "")
    role_of = roles.set_index("gid").role
    role_of = role_of[~role_of.index.duplicated()]
    absent = top.gid[~top.gid.isin(role_of.index)]
    rep.add("top_nodes: gid ⊂ nodes_roles", absent.empty, int(absent.size), 0, _examples(absent))
    present = top[top.gid.isin(role_of.index)]
    mism = present.gid[present.role.values != role_of.loc[present.gid].values]
    rep.add("top_nodes: role = nodes_roles", mism.empty, int(mism.size), 0, _examples(mism))
    ps_nodes = pd.to_numeric(roles.set_index("gid").priority_score, errors="coerce")
    ps_nodes = ps_nodes[~ps_nodes.index.duplicated()]
    delta = pd.to_numeric(present.priority_score, errors="coerce").to_numpy() - ps_nodes.loc[present.gid].to_numpy()
    ps_diff = present.gid[~(abs(delta) <= 1e-9)]
    rep.add("top_nodes: priority_score = nodes_roles", ps_diff.empty, int(ps_diff.size), 0, _examples(ps_diff))
    why = _text(top.why)
    bad_w = top.gid[(why.str.strip().str.len() == 0) | ~_has_digit(why)]
    rep.add("top_nodes: why непустой с цифрой", bad_w.empty, int(bad_w.size), 0, _examples(bad_w))
    bad_m = top.gid[why.str.contains("mock", case=False, regex=False)]
    rep.add("top_nodes: why без «mock»", bad_m.empty, int(bad_m.size), 0, _examples(bad_m))


def _check_method(rep: _Report, roles: pd.DataFrame, out_dir: Path, method: str) -> None:
    meta = out_dir / "run_meta.json"
    if meta.exists():
        try:
            got = json.loads(meta.read_text()).get("method")
        except (OSError, ValueError) as exc:
            rep.add("run_meta.json: method", False, f"не читается: {exc}", method)
            got = None
        else:
            rep.add("run_meta.json: method", got == method, got, method)
    if method != "v0":
        v0 = roles.gid[_text(roles.evidence).str.startswith("v0:")]
        rep.add(f"evidence без префикса v0: (метод {method})", v0.empty, int(v0.size), 0, _examples(v0))


def _read_meta(out_dir: Path) -> dict:
    try:
        return json.loads((out_dir / "run_meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _check_v1(rep: _Report, roles: pd.DataFrame, top: pd.DataFrame, out_dir: Path) -> None:
    """Проверки v1: role_score различает узлы внутри ролей, очередь in_queue сходится с run_meta."""
    rs = pd.to_numeric(roles.role_score, errors="coerce")
    nun = rs.groupby(roles.role).nunique().sort_index()
    varied = [r for r, n in nun.items() if n >= ROLE_SCORE_MIN_UNIQUE]
    rep.add(f"nodes_roles: role_score не константа (≥{ROLE_SCORE_MIN_UNIQUE} значений) в ≥{ROLE_SCORE_MIN_ROLES} ролях",
            len(varied) >= ROLE_SCORE_MIN_ROLES, len(varied), f"≥{ROLE_SCORE_MIN_ROLES}",
            "уникальных: " + ", ".join(f"{r} {n}" for r, n in nun.items()))

    for name, df in (("nodes_roles", roles), ("top_nodes", top)):
        if "in_queue" not in df.columns:
            rep.add(f"{name}: in_queue ∈ {{0,1}}", False, "нет колонки", "0/1")
            continue
        q = pd.to_numeric(df.in_queue, errors="coerce")
        bad = df.gid[~q.isin([0, 1])]
        rep.add(f"{name}: in_queue ∈ {{0,1}}", bad.empty, int(bad.size), 0, _examples(bad))

    meta = _read_meta(out_dir)
    if "in_queue" in roles.columns and "n_terms_above_p95" in roles.columns:
        k = int(meta.get("queue_min_terms_above_p95", 2))
        nt = pd.to_numeric(roles.n_terms_above_p95, errors="coerce")
        q = pd.to_numeric(roles.in_queue, errors="coerce")
        bad = roles.gid[q != (nt >= k).astype(int)]
        rep.add(f"nodes_roles: in_queue = (n_terms_above_p95 ≥ {k})", bad.empty, int(bad.size), 0, _examples(bad))
    if "in_queue" in roles.columns and "in_queue" in top.columns:
        q_of = roles.set_index("gid").in_queue
        present = top[top.gid.isin(q_of.index)]
        mism = present.gid[pd.to_numeric(present.in_queue, errors="coerce").to_numpy()
                           != pd.to_numeric(q_of.loc[present.gid], errors="coerce").to_numpy()]
        rep.add("top_nodes: in_queue = nodes_roles", mism.empty, int(mism.size), 0, _examples(mism))

    n_meta = meta.get("n_in_queue")
    n_csv = int(pd.to_numeric(roles.in_queue, errors="coerce").fillna(0).sum()) if "in_queue" in roles.columns else None
    rep.add("run_meta.json: n_in_queue = Σ in_queue", n_meta is not None and n_meta == n_csv,
            n_meta, n_csv, "queue_rule: " + str(meta.get("queue_rule", "нет"))[:60])


def check_outputs(data_dir, out_dir, require_method: str | None = None) -> list[dict]:
    """Проверяет три CSV в out_dir против parquet в data_dir. Возвращает список проверок."""
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    rep = _Report()

    present = {f: (out_dir / f).exists() for f in FILES}
    for f, ok in present.items():
        rep.add(f"файл {f} существует", ok, "есть" if ok else "нет", "есть", str(out_dir / f))
    if not all(present.values()):
        return rep.rows

    nodes = pd.read_parquet(data_dir / "nodes.parquet", columns=["gid", "depth", "is_seed"])
    nodes["gid"] = nodes.gid.astype("int64")
    edges = pd.read_parquet(data_dir / "edges.parquet", columns=["src", "dst", "sum_kzt"])
    edges["src"] = edges.src.astype("int64")

    try:
        roles = pd.read_csv(out_dir / "nodes_roles.csv", dtype={"gid": "int64"})
        clusters = pd.read_csv(out_dir / "clusters.csv", dtype={"top_gids": str, "hypothesis": str})
        top = pd.read_csv(out_dir / "top_nodes.csv", dtype={"gid": "int64"})
    except (ValueError, KeyError, pd.errors.ParserError) as exc:
        # gid не читается как int64 (float/NaN/1.0e+17) или колонки нет
        rep.add("CSV читаются (gid как int64)", False, f"{type(exc).__name__}: {exc}"[:160], "int64")
        return rep.rows
    rep.add("CSV читаются (gid как int64)", True, "ok", "int64")
    # pandas молча читает 1.0000000000114521e+17 как int64 с потерей младших цифр — сверяем сырой текст
    for f in ("nodes_roles.csv", "top_nodes.csv"):
        raw = pd.read_csv(out_dir / f, usecols=["gid"], dtype=str).gid.fillna("")
        bad = raw[~raw.str.fullmatch(r"\d+")]
        rep.add(f"{f}: gid записан целым числом", bad.empty, int(bad.size), 0, _examples(bad))

    if _check_nodes(rep, roles, nodes, edges):
        _check_clusters(rep, clusters, roles, nodes, edges)
        _check_top(rep, top, roles)
        if require_method:
            _check_method(rep, roles, out_dir, require_method)
        # v1-проверки: по --require-method v1 или по run_meta.json.method (прогон из pipeline.run)
        if (require_method or _read_meta(out_dir).get("method")) == "v1":
            _check_v1(rep, roles, top, out_dir)
    return rep.rows


def _print_table(rows: list[dict]) -> None:
    w = max(len(r["name"]) for r in rows)
    for r in rows:
        mark = "OK  " if r["ok"] else "FAIL"
        line = f"{mark}  {r['name']:<{w}}  {r['value']!s:<24}  ожид. {r['expected']!s}"
        if r["note"]:
            line += f"  | {r['note']}"
        print(line)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.check", description=__doc__.split("\n")[0])
    ap.add_argument("--data", default="task/data", help="каталог с nodes/edges/transactions.parquet")
    ap.add_argument("--out", default="outputs", help="каталог с тремя CSV")
    ap.add_argument("--require-method", default=None, choices=["v0", "v1"],
                    help="сверить run_meta.json.method и запретить evidence с префиксом v0:")
    args = ap.parse_args(argv)

    rows = check_outputs(args.data, args.out, require_method=args.require_method)
    _print_table(rows)
    failed = [r for r in rows if not r["ok"]]
    print(f"\nпроверок {len(rows)}, провалено {len(failed)}")

    out = Path(args.out)
    if not failed and (out / "nodes_roles.csv").exists():
        roles = pd.read_csv(out / "nodes_roles.csv", usecols=["role", "cluster_id"])
        counts = roles.role.value_counts().sort_index()
        print("роли: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        print(f"кластеров: {roles.cluster_id.nunique()}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
