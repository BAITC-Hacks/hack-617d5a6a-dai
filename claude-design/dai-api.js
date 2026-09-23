// DAI «Граф денег»: загрузка ответов API из демо-пакета, эмуляция запросов, форматтеры, токены ролей, граф (Cytoscape.js)
window.DAI = window.DAI || (function () {
  const BASE = 'uploads/dai-design-pack/data/';
  const FILES = { meta: '01_meta', top: '02_top20', clusters: '03_clusters', search: '04_search_prefix', c05: '05_coordinator_card', s06: '06_coordinator_subgraph_r1', c07: '07_transit_card', s08: '08_transit_subgraph_r1', c09: '09_truncated_depth4_card', c10: '10_isolated_seed_card', cl2: '11_cluster_small', err: '12_errors' };

  // Цвета ролей: Okabe–Ito в oklch. Редкие роли — насыщенные, массовые (terminal, peripheral) — приглушённые.
  const ROLES = {
    coordinator:  { title: 'Координатор',         light: 'oklch(0.60 0.19 38)',  dark: 'oklch(0.72 0.17 40)',  ink: 'oklch(0.48 0.16 38)',  inkDark: 'oklch(0.80 0.13 40)',  tint: 'oklch(0.95 0.035 45)', tintDark: 'oklch(0.30 0.07 40)' },
    distributor:  { title: 'Распределитель',      light: 'oklch(0.62 0.13 345)', dark: 'oklch(0.74 0.12 345)', ink: 'oklch(0.48 0.13 345)', inkDark: 'oklch(0.82 0.09 345)', tint: 'oklch(0.95 0.025 345)', tintDark: 'oklch(0.30 0.05 345)' },
    consolidator: { title: 'Консолидатор',        light: 'oklch(0.52 0.13 250)', dark: 'oklch(0.70 0.12 245)', ink: 'oklch(0.45 0.13 250)', inkDark: 'oklch(0.80 0.09 245)', tint: 'oklch(0.95 0.025 250)', tintDark: 'oklch(0.29 0.05 250)' },
    transit:      { title: 'Транзит',             light: 'oklch(0.76 0.15 78)',  dark: 'oklch(0.80 0.14 80)',  ink: 'oklch(0.48 0.10 70)',  inkDark: 'oklch(0.85 0.11 80)',  tint: 'oklch(0.96 0.04 85)',  tintDark: 'oklch(0.31 0.05 80)' },
    terminal:     { title: 'Конечный получатель', light: 'oklch(0.72 0.035 220)', dark: 'oklch(0.55 0.03 220)', ink: 'oklch(0.45 0.03 220)', inkDark: 'oklch(0.78 0.025 220)', tint: 'oklch(0.96 0.008 220)', tintDark: 'oklch(0.27 0.012 220)' },
    peripheral:   { title: 'Периферия',           light: 'oklch(0.86 0.004 260)', dark: 'oklch(0.42 0.004 260)', ink: 'oklch(0.50 0.005 260)', inkDark: 'oklch(0.72 0.005 260)', tint: 'oklch(0.97 0 0)',     tintDark: 'oklch(0.26 0 0)' },
  };
  const ROLE_ORDER = ['coordinator', 'distributor', 'consolidator', 'transit', 'terminal', 'peripheral'];
  const UNKNOWN = { title: 'роль не загружена', light: 'oklch(0.97 0 0)', ink: 'oklch(0.556 0 0)', tint: 'oklch(0.97 0 0)' };
  const role = (r) => ROLES[r] || UNKNOWN;

  // ---------- форматтеры ----------
  const NB = '\u202F';
  const groups = (n) => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, NB);
  const kzt = (n) => groups(n) + '\u00A0₸';
  const kztShort = (n) => {
    if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace('.', ',').replace(',0', '') + '\u00A0млн\u00A0₸';
    if (n >= 1e3) return Math.round(n / 1e3) + '\u00A0тыс\u00A0₸';
    return Math.round(n) + '\u00A0₸';
  };
  const score = (s) => (s == null ? '—' : s.toFixed(2).replace('.', ','));
  const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  const dateLong = (d) => { const [y, m, dd] = d.split('-'); return +dd + ' ' + MONTHS[+m - 1]; };
  const dateShort = (d) => { const [y, m, dd] = d.split('-'); return dd + '.' + m; };
  const gidParts = (g) => (/^\d{18}$/.test(g) ? { pre: g.slice(0, 8), mid: g.slice(8, 15), suf: g.slice(15) } : { pre: '', mid: String(g), suf: '' });
  const plural = (n, a, b, c) => { const m10 = n % 10, m100 = n % 100; return m10 === 1 && m100 !== 11 ? a : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? b : c; };
  const edgeWidth = (s) => { const t = (Math.log(Math.max(s, 5000)) - Math.log(5000)) / (Math.log(4.4e6) - Math.log(5000)); return +(1 + 7 * Math.min(1, Math.max(0, t))).toFixed(2); };
  const nodeSize = (p) => Math.round(18 + 38 * Math.max(0, Math.min(1, p == null ? 0.2 : p)));

  // ---------- данные ----------
  let P = null, D = null;
  const nodes = new Map(), edges = new Map(), cards = new Map(), subs = new Map(), clusterGraphs = new Map(), transfers = [];
  function addNode(n) { if (n && n.gid && (!nodes.has(n.gid) || n.evidence)) nodes.set(n.gid, n); }
  function addEdge(e) { edges.set(e.src + '|' + e.dst, e); }
  function index(d) {
    [d.c05, d.c07, d.c09, d.c10].forEach((c) => { addNode(c.node); cards.set(c.node.gid, c); c.in_edges.forEach(addEdge); c.out_edges.forEach(addEdge); c.transfers.forEach((t) => transfers.push(t)); });
    subs.set(d.c05.node.gid, d.s06); subs.set(d.c07.node.gid, d.s08);
    [d.s06, d.s08, d.cl2.graph].forEach((g) => { g.nodes.forEach(addNode); g.edges.forEach(addEdge); });
    d.search.response.items.forEach(addNode);
    clusterGraphs.set(d.cl2.cluster.cluster_id, d.cl2);
  }
  function load() {
    if (P) return P;
    P = Promise.all(Object.entries(FILES).map(([k, f]) => fetch(BASE + f + '.json').then((r) => { if (!r.ok) throw new Error(f); return r.json(); }).then((j) => [k, j])))
      .then((es) => { D = Object.fromEntries(es); index(D); return D; });
    return P;
  }

  // ---------- эмуляция API ----------
  const api = { mode: 'ok', latency: 260 };
  const delay = (v) => new Promise((res, rej) => {
    if (api.mode === 'hang') return;
    setTimeout(() => (api.mode === 'down' ? rej({ network: true }) : res(v)), api.latency);
  });
  function synthCard(gid) {
    const n = nodes.get(gid); if (!n) return null;
    const ie = [], oe = []; edges.forEach((e) => { if (e.dst === gid) ie.push(e); if (e.src === gid) oe.push(e); });
    const tr = transfers.filter((t) => t.src === gid || t.dst === gid).sort((a, b) => a.date.localeCompare(b.date));
    const seen = new Set(); const trU = tr.filter((t) => { const k = t.src + t.dst + t.date + t.sum_kzt; if (seen.has(k)) return false; seen.add(k); return true; });
    return { node: n, in_edges: ie, out_edges: oe, transfers: trU, partial: true };
  }
  function nodeReq(gid) {
    if (cards.has(gid)) return delay({ status: 200, body: cards.get(gid) });
    const s = synthCard(gid); if (s) return delay({ status: 200, body: s });
    const t = D && D.top.items.find((i) => i.gid === gid);
    if (t) return delay({ status: 200, body: { node: { gid, role: t.role, priority_score: t.priority_score, evidence: t.why }, in_edges: [], out_edges: [], transfers: [], nodata: true } });
    return delay({ status: 404, body: { detail: 'gid ' + gid + ' не найден' } });
  }
  function subgraphReq(gid) {
    if (subs.has(gid)) return delay({ status: 200, body: subs.get(gid) });
    const nb = new Set([gid]); const es = [];
    edges.forEach((e) => { if (e.src === gid || e.dst === gid) { nb.add(e.src); nb.add(e.dst); } });
    edges.forEach((e) => { if (nb.has(e.src) && nb.has(e.dst)) es.push(e); });
    const ns = [...nb].map((g) => nodes.get(g) || { gid: g, role: null, priority_score: null, stub: true });
    return delay({ status: 200, body: { nodes: ns, edges: es, meta: { mock: true, n_nodes: ns.length, n_edges: es.length, truncated: false } } });
  }
  function searchReq(q, limit) {
    limit = limit || 5;
    if (!q) return delay({ status: 422, body: D.err.bad_params.body });
    if (D && q === '1000000003') return delay({ status: 200, body: D.search.response });
    const pool = new Map(); nodes.forEach((n) => pool.set(n.gid, n));
    D.top.items.forEach((t) => { if (!pool.has(t.gid)) pool.set(t.gid, { gid: t.gid, role: t.role, priority_score: t.priority_score, is_seed: /seed=1/.test(t.why), depth: 0 }); });
    const all = [...pool.values()].filter((n) => n.gid.startsWith(q)).sort((a, b) => (b.gid === q) - (a.gid === q) || (b.priority_score || 0) - (a.priority_score || 0));
    return delay({ status: 200, body: { items: all.slice(0, limit), total: all.length } });
  }
  api.node = nodeReq; api.subgraph = subgraphReq; api.search = searchReq;
  api.cluster = (id) => delay(clusterGraphs.has(id) ? { status: 200, body: clusterGraphs.get(id) } : { status: 200, body: null });

  return { load, api, ROLES, ROLE_ORDER, UNKNOWN, role, kzt, kztShort, score, dateLong, dateShort, gidParts, plural, edgeWidth, nodeSize, groups, data: () => D, nodes, edges, transfers: () => { const seen = new Set(); return transfers.filter((t) => { const k = t.src + t.dst + t.date + t.sum_kzt; if (seen.has(k)) return false; seen.add(k); return true; }); } };
})();
