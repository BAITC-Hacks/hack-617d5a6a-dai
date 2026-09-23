"""API «Граф денег»: отдаёт интерфейсу роли, кластеры, приоритеты и связи узлов.

Запуск из корня репозитория:  uvicorn backend.app.main:app --reload --port 8000
(из backend/ тоже работает:    uvicorn app.main:app --reload --port 8000)
Схема:                        http://localhost:8000/openapi.json
Экспорт схемы во фронт:       python backend/export_openapi.py

Имена функций-обработчиков становятся operationId (generate_unique_id_function), а из них —
имена в сгенерированном клиенте фронта: get_graph → getGraphOptions / handleGetGraph.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

import networkx as nx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import schemas as s
from .data import ROLE_INFO, Store, load_store

app = FastAPI(
    title="DAI — Граф денег API",
    version="0.1.0",
    description="Роли, кластеры и приоритеты проверки по графу переводов. gid всегда строкой.",
    generate_unique_id_function=lambda r: r.name,
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@lru_cache(maxsize=1)
def get_store() -> Store:
    return load_store()


def _node_out(store: Store, gid: str) -> s.NodeOut:
    r = store.nodes.loc[gid]
    return s.NodeOut(**{k: (r[k].item() if hasattr(r[k], "item") else r[k]) for k in s.NodeOut.model_fields})


def _nodes_out(store: Store, gids: list[str]) -> list[s.NodeOut]:
    return [_node_out(store, g) for g in gids]


def _edges_out(store: Store, edges) -> list[s.EdgeOut]:
    return [s.EdgeOut(src=r.src, dst=r.dst, sum_kzt=float(r.sum_kzt), n_tx=int(r.n_tx), depth=int(r.depth))
            for r in edges.itertuples(index=False)]


def _graph_response(store: Store, gids: list[str], truncated: bool = False) -> s.GraphResponse:
    keep = set(gids)
    e = store.edges[store.edges.src.isin(keep) & store.edges.dst.isin(keep)]
    return s.GraphResponse(
        nodes=_nodes_out(store, gids), edges=_edges_out(store, e),
        meta=s.GraphMeta(mock=store.mock, n_nodes=len(gids), n_edges=len(e), truncated=truncated),
    )


def _cluster_out(row) -> s.ClusterOut:
    return s.ClusterOut(
        cluster_id=int(row.cluster_id), n_nodes=int(row.n_nodes), n_seed=int(row.n_seed),
        sum_kzt_internal=float(row.sum_kzt_internal), top_gids=[str(x) for x in row.top_gids],
        hypothesis=str(row.hypothesis),
    )


# ------------------------------------------------------------------ служебное

@app.get("/health", response_model=s.HealthResponse, tags=["meta"])
def get_health() -> s.HealthResponse:
    return s.HealthResponse(status="ok", mock=get_store().mock)


@app.get("/meta", response_model=s.MetaResponse, tags=["meta"])
def get_meta() -> s.MetaResponse:
    """Сводка по выгрузке, источник ролей и словарь ролей для легенды."""
    st = get_store()
    return s.MetaResponse(
        mock=st.mock, source=st.source, n_nodes=len(st.nodes), n_edges=len(st.edges),
        n_transactions=len(st.tx), n_seed=st.n_seed, n_clusters=len(st.clusters),
        period_start=st.period_start, period_end=st.period_end, total_kzt=st.total_kzt,
        roles=[s.RoleInfo(role=r, title=t, description=d) for r, t, d in ROLE_INFO],
    )


@app.post("/reload", response_model=s.ReloadResponse, tags=["meta"])
def reload_data() -> s.ReloadResponse:
    """Перечитать outputs/ после прогона пайплайна, без перезапуска сервера."""
    get_store.cache_clear()
    st = get_store()
    return s.ReloadResponse(source=st.source, n_nodes=len(st.nodes))


# ------------------------------------------------------------------ граф

@app.get("/graph", response_model=s.GraphResponse, tags=["graph"])
def get_graph(
    cluster_id: int | None = Query(default=None, description="Только узлы этого кластера"),
    role: s.Role | None = Query(default=None, description="Только узлы этой роли"),
    min_priority: float = Query(default=0.0, ge=0, le=1, description="Порог priority_score"),
    limit: int = Query(default=2500, ge=1, le=5000, description="Максимум узлов, по убыванию priority_score"),
) -> s.GraphResponse:
    """Весь граф или его срез. Рёбра — только между возвращёнными узлами."""
    st = get_store()
    df = st.nodes
    if cluster_id is not None:
        df = df[df.cluster_id == cluster_id]
    if role is not None:
        df = df[df.role == role]
    if min_priority > 0:
        df = df[df.priority_score >= min_priority]
    df = df.sort_values(["priority_score", "gid"], ascending=[False, True])
    truncated = len(df) > limit
    return _graph_response(st, df.gid.head(limit).tolist(), truncated=truncated)


@app.get("/search", response_model=s.SearchResponse, tags=["graph"])
def search_nodes(
    q: str = Query(min_length=1, description="Начало строки gid"),
    limit: int = Query(default=20, ge=1, le=200),
) -> s.SearchResponse:
    """Поиск по началу gid; точное совпадение идёт первым."""
    st = get_store()
    df = st.nodes[st.nodes.gid.str.startswith(q.strip())]
    df = df.assign(_exact=(df.gid == q.strip())).sort_values(
        ["_exact", "priority_score", "gid"], ascending=[False, False, True])
    return s.SearchResponse(items=_nodes_out(st, df.gid.head(limit).tolist()), total=len(df))


@app.get("/nodes/{gid}", response_model=s.NodeCard, tags=["nodes"])
def get_node(gid: str) -> s.NodeCard:
    """Карточка узла: роль с основанием, входящие и исходящие рёбра, отдельные переводы."""
    st = get_store()
    if gid not in st.nodes.index:
        raise HTTPException(status_code=404, detail=f"gid {gid} не найден")
    tx = st.tx[(st.tx.src == gid) | (st.tx.dst == gid)]
    return s.NodeCard(
        node=_node_out(st, gid),
        in_edges=_edges_out(st, st.edges[st.edges.dst == gid]),
        out_edges=_edges_out(st, st.edges[st.edges.src == gid]),
        transfers=[s.TransferOut(src=r.src, dst=r.dst, date=r.date, sum_kzt=float(r.sum_kzt))
                   for r in tx.itertuples(index=False)],
    )


@app.get("/nodes/{gid}/subgraph", response_model=s.GraphResponse, tags=["nodes"])
def get_node_subgraph(
    gid: str,
    radius: int = Query(default=1, ge=1, le=3, description="Сколько шагов от узла в любую сторону"),
) -> s.GraphResponse:
    """Окрестность узла для экрана: узлы в radius шагов (без учёта направления), рёбра — исходные направленные."""
    st = get_store()
    if gid not in st.nodes.index:
        raise HTTPException(status_code=404, detail=f"gid {gid} не найден")
    ego = nx.ego_graph(st.graph.to_undirected(as_view=True), gid, radius=radius)
    gids = sorted(ego.nodes, key=lambda x: (x != gid, x))
    return _graph_response(st, gids)


# ------------------------------------------------------------------ приоритеты и кластеры

@app.get("/top", response_model=s.TopResponse, tags=["priority"])
def get_top_nodes(limit: int = Query(default=20, ge=1, le=2248)) -> s.TopResponse:
    """Ранжированный список приоритетов (top_nodes.csv)."""
    st = get_store()
    rows = st.top.head(limit)
    return s.TopResponse(items=[
        s.TopNode(rank=int(r.rank), gid=str(r.gid), role=str(r.role),
                  priority_score=float(r.priority_score), why=str(r.why))
        for r in rows.itertuples(index=False)
    ])


@app.get("/clusters", response_model=s.ClustersResponse, tags=["clusters"])
def list_clusters() -> s.ClustersResponse:
    st = get_store()
    return s.ClustersResponse(items=[_cluster_out(r) for r in st.clusters.itertuples(index=False)])


@app.get("/clusters/{cluster_id}", response_model=s.ClusterDetail, tags=["clusters"])
def get_cluster(cluster_id: int) -> s.ClusterDetail:
    """Паспорт кластера и его подграф."""
    st = get_store()
    row = st.clusters[st.clusters.cluster_id == cluster_id]
    if row.empty:
        raise HTTPException(status_code=404, detail=f"cluster_id {cluster_id} не найден")
    gids = st.nodes[st.nodes.cluster_id == cluster_id].sort_values(
        ["priority_score", "gid"], ascending=[False, True]).gid.tolist()
    return s.ClusterDetail(cluster=_cluster_out(next(row.itertuples(index=False))), graph=_graph_response(st, gids))
