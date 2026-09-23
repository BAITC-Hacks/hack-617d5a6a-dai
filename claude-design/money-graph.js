// DAIGraph — схема сети в духе graph view: тёмный фон, мелкие узлы, тонкие связи, кластеры-острова.
// D3 v7 (force, zoom, drag) + SVG. API: DAIGraph.create(el, {onSelect}) → {setData, setView, flyTo, hover, fit}
(function () {
  const MONO = "'Geist Mono', ui-monospace, monospace";
  const BG = '#161618';
  const CL = ['#8ec5ff', '#ffb86b', '#b8e986', '#f5a3c7', '#c9b6ff', '#7fe0d4', '#ffd86b', '#ff9e9e'];
  const dayOf = (d) => +d.slice(8, 10);

  function create(el, cb) {
    cb = cb || {};
    const root = d3.select(el).style('position', 'absolute').style('inset', '0').style('background', BG).style('overflow', 'hidden');
    const svg = root.append('svg').attr('width', '100%').attr('height', '100%').style('display', 'block').style('cursor', 'grab');
    svg.append('style').text(
      '@keyframes daiDash{to{stroke-dashoffset:-20}}' +
      '.dai-flow{stroke-dasharray:6 4;animation:daiDash .7s linear 4}' +
      '@keyframes daiSeed{0%,100%{stroke-opacity:1}50%{stroke-opacity:.35}}' +
      '.dai-seed{animation:daiSeed 1.8s ease-in-out 1}'
    );
    const defs = svg.append('defs');
    defs.append('marker').attr('id', 'dai-arr').attr('viewBox', '0 -4 8 8').attr('refX', 7).attr('refY', 0).attr('markerWidth', 7).attr('markerHeight', 7).attr('markerUnits', 'userSpaceOnUse').attr('orient', 'auto')
      .append('path').attr('d', 'M0,-3.5L8,0L0,3.5').attr('fill', '#9a9aa0');
    const g = svg.append('g');
    const gH = g.append('g'), gL = g.append('g'), gN = g.append('g'), gT = g.append('g'), gR = g.append('g');
    let k = 1;
    const zoom = d3.zoom().scaleExtent([0.15, 6]).on('zoom', (e) => { g.attr('transform', e.transform); const nk = e.transform.k; if ((nk >= V.labelZoom) !== (k >= V.labelZoom)) { k = nk; labels(150); } k = nk; });
    svg.call(zoom).on('dblclick.zoom', null);
    const tip = root.append('div').style('position', 'absolute').style('pointer-events', 'none').style('display', 'none').style('z-index', 5)
      .style('background', 'rgba(24,24,27,.96)').style('border', '1px solid #3a3a40').style('border-radius', '8px').style('padding', '8px 10px').style('color', '#ececf0').style('font', '13px/1.4 Geist, sans-serif').style('min-width', '220px').style('box-shadow', '0 8px 28px rgba(0,0,0,.45)');

    let N = new Map(), E = [], passports = new Map(), top = new Set();
    let V = { mode: 'local', focus: null, depth: 1, dirIn: true, dirOut: true, between: true, layout: 'layers', colorBy: 'role', roles: null, clusters: null, showIsolated: true, hideTrunc: false, flow: 'dash', labelZoom: 1.6, nodeScale: 1, edgeScale: 1, charge: 60, linkDist: 40, clusterPull: 0.12, range: null, play: null };
    let vis = { nodes: [], edges: [] }, hoverId = null, first = true;
    let pendingFit = false;
    const sim = d3.forceSimulation().alphaMin(0.02).stop().on('tick', draw).on('end', () => { if (pendingFit) { pendingFit = false; fit(500); } });

    function setData(d) {
      N = new Map(); E = [];
      top = new Set(d.top || []);
      passports = new Map((d.clusters || []).map((c) => [c.cluster_id, c]));
      d.nodes.forEach((n) => N.set(n.gid, { id: n.gid, n, x: NaN, y: NaN }));
      const firstDay = new Map(), days = new Map();
      (d.transfers || []).forEach((t) => { const key = t.src + '|' + t.dst, dd = dayOf(t.date); firstDay.set(key, Math.min(firstDay.get(key) || 99, dd)); (days.get(key) || days.set(key, []).get(key)).push(dd); });
      const keys = new Set();
      d.edges.forEach((e) => {
        [e.src, e.dst].forEach((g) => { if (!N.has(g)) N.set(g, { id: g, n: { gid: g, role: null, stub: true }, x: NaN, y: NaN }); });
        const key = e.src + '|' + e.dst; keys.add(key);
        E.push({ id: key, source: N.get(e.src), target: N.get(e.dst), e, first: firstDay.get(key) || null, days: days.get(key) || null });
      });
      E.forEach((l) => (l.recip = keys.has(l.e.dst + '|' + l.e.src)));
      N.forEach((o) => { o.deg = 0; });
      E.forEach((l) => { l.source.deg++; l.target.deg++; });
      first = true;
    }

    const R = (o) => (o.n.priority_score == null ? 2.5 : 2.5 + 8 * o.n.priority_score) * V.nodeScale;
    const color = (o) => {
      if (o.n.stub || !o.n.role) return '#5a5a60';
      if (V.colorBy === 'cluster') return CL[(o.n.cluster_id || 0) % CL.length];
      return DAI.role(o.n.role).dark;
    };
    const ew = (l) => (0.5 + 2.2 * (DAI.edgeWidth(l.e.sum_kzt) - 1) / 7) * V.edgeScale;

    // ---------- видимость ----------
    function compute() {
      let ids;
      if (V.mode === 'local' && V.focus && N.has(V.focus)) {
        ids = new Map([[V.focus, 0]]);
        const walk = (dir) => {
          let front = [V.focus];
          for (let d = 1; d <= V.depth; d++) {
            const nx = [];
            E.forEach((l) => {
              const a = dir < 0 ? l.target.id : l.source.id, b = dir < 0 ? l.source.id : l.target.id;
              if (front.includes(a) && !ids.has(b)) { ids.set(b, dir * d); nx.push(b); }
            });
            front = nx;
          }
        };
        if (V.dirIn) walk(-1);
        if (V.dirOut) walk(1);
      } else if (V.mode === 'local') {
        ids = new Map();
      } else {
        ids = new Map(); N.forEach((o) => ids.set(o.id, 0));
      }
      const pass = (o) => {
        if (o.id === V.focus) return true;
        if (V.roles && o.n.role && !V.roles.includes(o.n.role)) return false;
        if (V.clusters && o.n.cluster_id != null && !V.clusters.includes(o.n.cluster_id)) return false;
        if (V.hideTrunc && o.n.truncated_by_depth) return false;
        if (!V.showIsolated && o.n.is_seed && o.deg === 0) return false;
        return true;
      };
      const nodes = [...ids.keys()].map((id) => N.get(id)).filter(pass);
      nodes.forEach((o) => (o.layer = ids.get(o.id)));
      const S = new Set(nodes.map((o) => o.id));
      let edges = E.filter((l) => S.has(l.source.id) && S.has(l.target.id));
      if (V.mode === 'local') {
        edges = edges.filter((l) => {
          const a = l.source.layer, b = l.target.layer;
          const tree = (b === a + 1 && (a >= 0 || b <= 0));
          return V.between ? true : tree;
        });
      }
      // даты: диапазон и таймлапс
      edges.forEach((l) => {
        let on = true;
        if (V.range && l.days) on = l.days.some((d) => d >= V.range[0] && d <= V.range[1]);
        if (V.play != null && l.first) on = on && l.first <= V.play;
        l.ghost = !on || ((V.play != null || V.range) && !l.days);
      });
      const grown = new Set();
      edges.forEach((l) => { if (!l.ghost) { grown.add(l.source.id); grown.add(l.target.id); } });
      nodes.forEach((o) => (o.ghost = (V.play != null || V.range) && !grown.has(o.id) && !o.n.is_seed && o.id !== V.focus));
      vis = { nodes, edges };
    }

    // ---------- раскладки ----------
    function clusterCenters(nodes) {
      const by = d3.rollup(nodes, (v) => v.length, (o) => o.n.cluster_id ?? -1);
      const ids = [...by.keys()].sort((a, b) => by.get(b) - by.get(a));
      const C = new Map();
      ids.forEach((id, i) => {
        if (i === 0) return C.set(id, { x: 0, y: 0 });
        const a = i * 2.4, r = 150 + 34 * Math.sqrt(i) * 3;
        C.set(id, { x: r * Math.cos(a), y: r * Math.sin(a) });
      });
      return C;
    }
    function layers(nodes, edges) {
      const T = new Map();
      const byL = d3.group(nodes, (o) => o.layer);
      const sumTo = new Map();
      edges.forEach((l) => { sumTo.set(l.source.id, (sumTo.get(l.source.id) || 0) + l.e.sum_kzt); sumTo.set(l.target.id, (sumTo.get(l.target.id) || 0) + l.e.sum_kzt); });
      byL.forEach((list, L) => {
        list.sort((a, b) => (sumTo.get(b.id) || 0) - (sumTo.get(a.id) || 0));
        const per = list.length > 30 ? 22 : 12;
        list.forEach((o, i) => {
          const c = Math.floor(i / per), row = i % per, inCol = Math.min(per, list.length - c * per);
          const dir = L < 0 ? -1 : 1;
          T.set(o.id, { x: L * 210 + dir * c * 58 * (L === 0 ? 0 : 1), y: (row - (inCol - 1) / 2) * 30 });
        });
      });
      return T;
    }

    function place(animate) {
      const { nodes, edges } = vis;
      const W = el.clientWidth || 600, H = el.clientHeight || 500;
      sim.stop();
      if (V.mode === 'local' && V.layout === 'layers') {
        const T = layers(nodes, edges);
        nodes.forEach((o) => { o.fx = null; o.fy = null; const t = T.get(o.id); o.tx = t.x; o.ty = t.y; if (isNaN(o.x)) { o.x = 0; o.y = 0; } o.sx = o.x; o.sy = o.y; });
        if (!animate) { nodes.forEach((o) => { o.x = o.tx; o.y = o.ty; }); draw(); return; }
        const t0 = performance.now(), D = 700;
        const tm = d3.timer(() => {
          const p = Math.min(1, (performance.now() - t0) / D), e = d3.easeCubicInOut(p);
          nodes.forEach((o) => { o.x = o.sx + (o.tx - o.sx) * e; o.y = o.sy + (o.ty - o.sy) * e; });
          draw(); if (p >= 1) tm.stop();
        });
        return;
      }
      const C = V.mode === 'overview' ? clusterCenters(nodes) : null;
      const fresh = nodes.filter((o) => isNaN(o.x));
      fresh.forEach((o) => {
        const c = C ? C.get(o.n.cluster_id ?? -1) : { x: 0, y: 0 };
        o.x = c.x + (Math.random() - 0.5) * 60; o.y = c.y + (Math.random() - 0.5) * 60;
      });
      nodes.forEach((o) => { o.fx = V.mode === 'local' && o.id === V.focus ? 0 : null; o.fy = o.fx; });
      sim.nodes(nodes)
        .force('charge', d3.forceManyBody().strength(-V.charge).distanceMax(400))
        .force('link', d3.forceLink(edges).id((o) => o.id).distance(V.linkDist).strength(0.6))
        .force('collide', d3.forceCollide((o) => R(o) + 2))
        .force('cx', d3.forceX((o) => (C ? C.get(o.n.cluster_id ?? -1).x : 0)).strength(C ? V.clusterPull : 0.04))
        .force('cy', d3.forceY((o) => (C ? C.get(o.n.cluster_id ?? -1).y : 0)).strength(C ? V.clusterPull : 0.04));
      if (fresh.length > nodes.length * 0.5) { sim.alpha(1); for (let i = 0; i < 320; i++) sim.tick(); draw(); sim.alpha(0.02).restart(); }
      else sim.alpha(animate ? 0.5 : 0.3).restart();
    }

    // ---------- отрисовка ----------
    let linkSel = gL.selectAll('path'), nodeSel = gN.selectAll('g'), textSel = gT.selectAll('text'), hullSel = gH.selectAll('g');
    function render(animate) {
      const dur = animate ? 350 : 0;
      linkSel = gL.selectAll('path').data(vis.edges, (l) => l.id).join(
        (en) => en.append('path').attr('fill', 'none').attr('stroke-opacity', 0),
        (up) => up,
        (ex) => ex.transition().duration(dur).attr('stroke-opacity', 0).remove()
      ).attr('stroke', '#8a8a90').attr('stroke-width', ew).attr('marker-end', V.flow === 'arrows' ? 'url(#dai-arr)' : null);
      nodeSel = gN.selectAll('g.n').data(vis.nodes, (o) => o.id).join(
        (en) => { const s = en.append('g').attr('class', 'n').style('cursor', 'pointer').attr('opacity', 0); s.append('circle').attr('class', 'c'); return s; },
        (up) => up,
        (ex) => ex.transition().duration(dur).attr('opacity', 0).remove()
      );
      nodeSel.select('circle.c').attr('r', R).attr('fill', color)
        .attr('stroke', (o) => (o.n.is_seed ? '#ffffff' : o.n.truncated_by_depth ? '#d4d4d8' : BG))
        .attr('stroke-width', (o) => (o.n.is_seed ? 2 : o.n.truncated_by_depth ? 1.4 : 0.8))
        .attr('stroke-dasharray', (o) => (o.n.truncated_by_depth ? '2.5 2' : null))
        .attr('class', (o) => 'c' + (o.n.is_seed ? ' dai-seed' : ''));
      nodeSel.selectAll('circle.f').remove();
      nodeSel.filter((o) => o.id === V.focus).insert('circle', 'circle.c').attr('class', 'f').attr('r', (o) => R(o) + 6).attr('fill', 'none').attr('stroke', '#ffffff').attr('stroke-opacity', 0.55).attr('stroke-width', 1.5);
      nodeSel.on('mouseenter', (e, o) => hover(o.id, e)).on('mousemove', (e) => moveTip(e)).on('mouseleave', () => hover(null)).on('click', (e, o) => { e.stopPropagation(); cb.onSelect && cb.onSelect(o.id); });
      nodeSel.call(d3.drag()
        .on('start', (e, o) => { svg.style('cursor', 'grabbing'); if (usesSim()) sim.alphaTarget(0.25).restart(); o.fx = o.x; o.fy = o.y; })
        .on('drag', (e, o) => { o.fx = e.x; o.fy = e.y; if (!usesSim()) { o.x = e.x; o.y = e.y; draw(); } })
        .on('end', (e, o) => { svg.style('cursor', 'grab'); if (usesSim()) sim.alphaTarget(0); if (!(V.mode === 'local' && o.id === V.focus && usesSim())) { o.fx = null; o.fy = null; } }));
      textSel = gT.selectAll('text').data(vis.nodes, (o) => o.id).join(
        (en) => en.append('text').attr('opacity', 0).attr('text-anchor', 'middle').attr('font-family', MONO).attr('font-weight', 500).style('pointer-events', 'none').style('paint-order', 'stroke').attr('stroke', BG).attr('stroke-width', 3),
        (up) => up,
        (ex) => ex.remove()
      ).text((o) => DAI.gidParts(o.id).mid).attr('font-size', (o) => (o.id === V.focus ? 12 : 10)).attr('fill', (o) => (o.id === V.focus ? '#ffffff' : '#b4b4bc'));
      hulls(animate);
      opac(animate ? 400 : 0);
      labels(animate ? 300 : 0);
      flows();
      draw();
    }
    const usesSim = () => !(V.mode === 'local' && V.layout === 'layers');

    function hulls(animate) {
      const groups = V.mode === 'overview' ? [...d3.group(vis.nodes.filter((o) => !o.ghost && o.n.cluster_id != null), (o) => o.n.cluster_id)] : [];
      hullSel = gH.selectAll('g.h').data(groups, (d) => d[0]).join(
        (en) => { const s = en.append('g').attr('class', 'h').attr('opacity', 0); s.append('path'); s.append('text').attr('text-anchor', 'middle').attr('font-family', 'Geist, sans-serif').attr('font-size', 12).attr('font-weight', 500).attr('fill', '#a1a1aa'); return s; },
        (up) => up,
        (ex) => ex.transition().duration(300).attr('opacity', 0).remove()
      );
      hullSel.transition().duration(animate ? 400 : 0).attr('opacity', 1);
      hullSel.select('path').attr('fill', (d) => (V.colorBy === 'cluster' ? CL[d[0] % CL.length] : '#ffffff')).attr('fill-opacity', 0.07).attr('stroke', (d) => (V.colorBy === 'cluster' ? CL[d[0] % CL.length] : '#ffffff')).attr('stroke-opacity', 0.14);
      hullSel.select('text').text((d) => { const p = passports.get(d[0]); return p ? 'Кластер ' + d[0] + ' · ' + DAI.groups(p.n_nodes) + ' ' + DAI.plural(p.n_nodes, 'узел', 'узла', 'узлов') + ' · ' + p.n_seed + ' seed' : 'Кластер ' + d[0]; });
    }
    const hullLine = d3.line().curve(d3.curveCatmullRomClosed.alpha(0.6));
    function drawHulls() {
      hullSel.each(function (d) {
        const pts = [];
        d[1].forEach((o) => { const r = R(o) + 14; for (let a = 0; a < 8; a++) pts.push([o.x + r * Math.cos((a * Math.PI) / 4), o.y + r * Math.sin((a * Math.PI) / 4)]); });
        const h = d3.polygonHull(pts); if (!h) return;
        const s = d3.select(this); s.select('path').attr('d', hullLine(h));
        const top = d3.min(h, (p) => p[1]), cx = d3.mean(d[1], (o) => o.x);
        s.select('text').attr('x', cx).attr('y', top - 8);
      });
    }

    function path(l) {
      const s = l.source, t = l.target, dx = t.x - s.x, dy = t.y - s.y, len = Math.hypot(dx, dy) || 1;
      const rt = R(t) + (V.flow === 'arrows' ? 2 : 0), ux = dx / len, uy = dy / len;
      const ex = t.x - ux * rt, ey = t.y - uy * rt;
      if (!l.recip) return 'M' + s.x + ',' + s.y + 'L' + ex + ',' + ey;
      const off = Math.min(28, len * 0.18), mx = (s.x + t.x) / 2 - uy * off, my = (s.y + t.y) / 2 + ux * off;
      return 'M' + s.x + ',' + s.y + 'Q' + mx + ',' + my + ' ' + ex + ',' + ey;
    }
    function draw() {
      linkSel.attr('d', path);
      nodeSel.attr('transform', (o) => 'translate(' + o.x + ',' + o.y + ')');
      textSel.attr('x', (o) => o.x).attr('y', (o) => o.y + R(o) + 12);
      drawHulls();
    }

    // ---------- состояние подсветки ----------
    function nb(id) { const s = new Set([id]); vis.edges.forEach((l) => { if (l.source.id === id) s.add(l.target.id); if (l.target.id === id) s.add(l.source.id); }); return s; }
    function opac(dur) {
      const H = hoverId ? nb(hoverId) : null;
      nodeSel.transition().duration(dur).attr('opacity', (o) => (o.ghost ? 0.07 : 1) * (H ? (H.has(o.id) ? 1 : 0.12) : 1));
      linkSel.transition().duration(dur).attr('stroke-opacity', (l) => {
        if (l.ghost) return 0.03;
        if (H) return l.source.id === hoverId || l.target.id === hoverId ? 0.95 : 0.04;
        if (V.focus && (l.source.id === V.focus || l.target.id === V.focus)) return 0.7;
        return 0.32;
      }).attr('stroke', (l) => (H && (l.source.id === hoverId || l.target.id === hoverId) ? '#e4e4e7' : '#8a8a90'));
      hullSel.transition().duration(dur).attr('opacity', H ? 0.35 : 1);
    }
    function labels(dur) {
      const H = hoverId ? nb(hoverId) : null;
      textSel.transition().duration(dur).attr('opacity', (o) => {
        if (o.ghost) return 0;
        if (H) return H.has(o.id) ? 1 : 0.06;
        return o.id === V.focus || top.has(o.id) || k >= V.labelZoom || (V.mode === 'local' && vis.nodes.length <= 30) ? 1 : 0;
      });
    }
    function flows() {
      linkSel.classed('dai-flow', false); void el.getBoundingClientRect();
      linkSel.classed('dai-flow', (l) => {
        if (V.flow !== 'dash' || l.ghost) return false;
        if (hoverId) return l.source.id === hoverId || l.target.id === hoverId;
        if (V.mode === 'local') return true;
        return !!V.focus && (l.source.id === V.focus || l.target.id === V.focus);
      });
    }
    function hover(id, ev) {
      hoverId = id; opac(150); labels(150); flows();
      if (!id) { tip.style('display', 'none'); return; }
      const o = N.get(id), n = o.n, r = n.role ? DAI.role(n.role) : DAI.UNKNOWN;
      const m = DAI.data() && DAI.data().meta.roles.find((x) => x.role === n.role);
      const row = (a, b) => '<div style="display:flex;gap:14px;justify-content:space-between;white-space:nowrap"><span style="color:#a1a1aa">' + a + '</span><span style="font-family:' + MONO + '">' + b + '</span></div>';
      tip.html('<div style="font:600 13px ' + MONO + ';margin-bottom:4px">' + id + '</div>' +
        '<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px"><span style="width:9px;height:9px;border-radius:50%;background:' + (n.role ? r.dark : '#5a5a60') + '"></span>' + (m ? m.title : r.title) + (n.is_seed ? ' · seed' : '') + (n.truncated_by_depth ? ' · граница выгрузки' : '') + '</div>' +
        (n.priority_score != null ? row('приоритет', DAI.score(n.priority_score)) : '') +
        (n.in_kzt != null ? row('вход', DAI.kztShort(n.in_kzt) + ' · ' + n.in_deg + ' отпр.') : '') +
        (n.out_kzt != null ? row('выход', n.truncated_by_depth ? 'не выгружены' : DAI.kztShort(n.out_kzt) + ' · ' + n.out_deg + ' получ.') : ''));
      tip.style('display', 'block');
      if (ev) moveTip(ev); else { const t = d3.zoomTransform(svg.node()); placeTip(t.applyX(o.x), t.applyY(o.y)); }
    }
    function moveTip(e) { const [x, y] = d3.pointer(e, el); placeTip(x, y); }
    function placeTip(x, y) { const w = el.clientWidth; tip.style('left', Math.min(x + 14, w - 250) + 'px').style('top', y + 14 + 'px'); }

    // ---------- камера ----------
    function fit(dur) {
      const lay = V.mode === 'local' && V.layout === 'layers';
      const px = (o) => (lay && o.tx != null ? o.tx : o.x), py = (o) => (lay && o.ty != null ? o.ty : o.y);
      const ns = vis.nodes.filter((o) => !isNaN(px(o))); if (!ns.length) return;
      const W = el.clientWidth || 600, H = el.clientHeight || 500;
      const x0 = d3.min(ns, px) - 40, x1 = d3.max(ns, px) + 40, y0 = d3.min(ns, py) - 50, y1 = d3.max(ns, py) + 40;
      const Hh = H - 70, s = Math.min(2.2, 0.94 * Math.min(W / (x1 - x0), Hh / (y1 - y0)));
      const t = d3.zoomIdentity.translate(W / 2 - s * (x0 + x1) / 2, Hh / 2 - s * (y0 + y1) / 2).scale(s);
      cam(t, dur == null ? 600 : dur);
    }
    let camT = null;
    function cam(t1, dur, done) {
      if (camT) camT.stop();
      if (!dur) { svg.call(zoom.transform, t1); done && done(); return; }
      const t0 = d3.zoomTransform(svg.node()), ip = d3.interpolate([t0.x, t0.y, t0.k], [t1.x, t1.y, t1.k]), st = performance.now();
      camT = d3.timer(() => {
        const p = Math.min(1, (performance.now() - st) / dur), v = ip(d3.easeCubicInOut(p));
        svg.call(zoom.transform, d3.zoomIdentity.translate(v[0], v[1]).scale(v[2]));
        if (p >= 1) { camT.stop(); camT = null; done && done(); }
      });
    }
    function flyTo(id) {
      const o = N.get(id); if (!o || isNaN(o.x)) return;
      const W = el.clientWidth || 600, H = el.clientHeight || 500, s = Math.max(k, 1.8);
      cam(d3.zoomIdentity.translate(W / 2 - s * o.x, H / 2 - s * o.y).scale(s), 750, () => pulse(o));
    }
    function pulse(o) {
      const c = gR.append('circle').attr('cx', o.x).attr('cy', o.y).attr('r', R(o)).attr('fill', 'none').attr('stroke', '#ffffff').attr('stroke-width', 2);
      const rep = (i) => c.attr('r', R(o)).attr('stroke-opacity', 0.9).transition().duration(900).ease(d3.easeCubicOut).attr('r', R(o) + 34).attr('stroke-opacity', 0).on('end', () => (i < 2 ? rep(i + 1) : c.remove()));
      rep(0);
    }

    function setView(nv, opts) {
      const prev = V; V = Object.assign({}, V, nv);
      const layoutKey = (v) => [v.mode, v.focus, v.depth, v.dirIn, v.dirOut, v.between, v.layout, v.roles, v.clusters, v.showIsolated, v.hideTrunc].join('|');
      const forceKey = (v) => [v.charge, v.linkDist, v.clusterPull, v.nodeScale].join('|');
      compute();
      const relayout = first || layoutKey(prev) !== layoutKey(V) || forceKey(prev) !== forceKey(V);
      render(!first);
      if (relayout) {
        const doFit = first || (opts && opts.fit);
        place(!first);
        if (doFit) { fit(first ? 0 : 600); if (usesSim()) pendingFit = true; }
      }
      if (first) { nodeSel.attr('opacity', 0); opac(700); first = false; }
    }

    svg.on('click', () => cb.onBackground && cb.onBackground());
    return { setData, setView, flyTo, hover: (id) => hover(id), fit: () => fit(600), counts: () => ({ n: vis.nodes.filter((o) => !o.ghost).length, e: vis.edges.filter((l) => !l.ghost).length }), destroy: () => { sim.stop(); root.selectAll('*').remove(); } };
  }
  window.DAIGraph = { create };
})();
