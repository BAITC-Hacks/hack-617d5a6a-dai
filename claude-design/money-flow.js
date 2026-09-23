// <money-flow> — послойная схема потока денег (D3 v7 + SVG).
// API: el.focusNode(gid) → bool, el.select(gid|null), el.fit(), el.setAnimate(bool), el.nodes
// Событие: 'nodeselect' (detail = сводка по узлу или null), всплывает до document.
(function () {
  const ROLES = {
    coordinator: ['Координатор', '#b392ff', 'К'],
    consolidator: ['Консолидация', '#ff6b6b', 'С'],
    distributor: ['Распределитель', '#ff9f43', 'Р'],
    transit: ['Транзит', '#f5c542', 'Т'],
    terminal: ['Конечный получатель', '#5aa9ff', 'П'],
    peripheral: ['Периферия', '#8a909b', '·'],
  };
  const COLS = ['Seed', 'Колено 1', 'Колено 2', 'Колено 3', 'Колено 4'];
  // gid, depth, role, priority, seed
  const RAW_N = [
    ['100017', 0, 'transit', .56, 1], ['100035', 0, 'peripheral', .34, 1], ['100121', 0, 'transit', .38, 1], ['100204', 0, 'transit', .36, 1],
    ['100266', 0, 'peripheral', .30, 1], ['100318', 0, 'transit', .33, 1], ['100377', 0, 'peripheral', .29, 1], ['100093', 0, 'peripheral', .27, 1],
    ['150903', 1, 'transit', .71], ['150211', 1, 'transit', .52], ['151477', 1, 'transit', .46], ['152038', 1, 'transit', .41],
    ['153690', 1, 'transit', .37], ['154112', 1, 'transit', .35], ['155806', 1, 'transit', .31],
    ['160344', 1, 'transit', .33], ['161902', 1, 'peripheral', .27], ['162517', 1, 'peripheral', .24], ['163081', 1, 'transit', .30],
    ['100482', 2, 'consolidator', .94], ['203117', 3, 'distributor', .88],
    ['311540', 4, 'peripheral', .18], ['311602', 4, 'peripheral', .17], ['311877', 4, 'peripheral', .16], ['+83', 4, 'peripheral', .2],
  ];
  // source, target, sum ₸, tx count
  const RAW_E = [
    ['100017', '150903', 630000, 5], ['100035', '150211', 556000, 4], ['100121', '151477', 512000, 4], ['100204', '152038', 470000, 4],
    ['100266', '153690', 425000, 3], ['100318', '154112', 401000, 3], ['100377', '155806', 371000, 3],
    ['150903', '100482', 612000, 4], ['150211', '100482', 540000, 4], ['151477', '100482', 498500, 3], ['152038', '100482', 455000, 3],
    ['153690', '100482', 410000, 3], ['154112', '100482', 388000, 3], ['155806', '100482', 362500, 2],
    ['160344', '100482', 301000, 2], ['161902', '100482', 262000, 2], ['162517', '100482', 214000, 2], ['163081', '100482', 172000, 1],
    ['100482', '203117', 126450, 1], ['203117', '311540', 34200, 1], ['203117', '311602', 41500, 1], ['203117', '311877', 29800, 1],
    ['203117', '+83', 2764000, 94],
  ];
  const fmtFull = v => Math.round(v).toLocaleString('ru-RU').replace(/[\u00a0,]/g, ' ') + ' ₸';
  const fmt = v => v >= 1e6 ? (v / 1e6).toFixed(1).replace('.', ',') + ' млн ₸' : v >= 1e4 ? Math.round(v / 1e3) + ' тыс ₸' : fmtFull(v);

  function loadD3() {
    if (window.d3) return Promise.resolve(window.d3);
    if (!window.__d3p) window.__d3p = new Promise((res, rej) => {
      const s = document.createElement('script');
      s.src = 'https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js';
      s.onload = () => res(window.d3); s.onerror = rej;
      document.head.appendChild(s);
    });
    return window.__d3p;
  }

  function buildData() {
    const N = RAW_N.map(a => ({ gid: a[0], d: a[1], role: a[2], p: a[3], seed: !!a[4], cut: a[1] === 4, agg: a[0][0] === '+', in: 0, out: 0, cin: 0, cout: 0 }));
    const by = new Map(N.map(n => [n.gid, n]));
    const E = RAW_E.map(a => ({ s: by.get(a[0]), t: by.get(a[1]), v: a[2], n: a[3] }));
    E.forEach(e => { e.s.out += e.v; e.s.cout += e.n; e.t.in += e.v; e.t.cin += e.n; });
    N.forEach(n => { n.r = 6 + n.p * 14; n.inE = E.filter(e => e.t === n); n.outE = E.filter(e => e.s === n); });
    return { N, E, by };
  }

  const walk = (n, dir) => {
    const seen = new Set([n]), q = [n];
    while (q.length) { const c = q.shift(); (dir > 0 ? c.outE : c.inE).forEach(e => { const b = dir > 0 ? e.t : e.s; if (!seen.has(b)) { seen.add(b); q.push(b); } }); }
    return seen;
  };

  function summary(n) {
    const up = walk(n, -1);
    const seeds = [...up].filter(x => x.seed && x !== n).length;
    const flags = [];
    if (n.seed) flags.push({ k: 'seed', t: 'Seed: входящие занижены — поступления извне выборки в данных отсутствуют, баланс некорректен.' });
    if (n.seed && !n.cout) flags.push({ k: 'noout', t: 'Seed без исходящих переводов: в цепочки не попадает, но остаётся в списке дела.' });
    if (n.cut) flags.push({ k: 'cut', t: 'Обрыв выборки: исходящие за 4-м коленом не прослеживались. Это не конечный получатель.' });
    if (!n.seed && n.out > n.in) flags.push({ k: 'bal', t: 'Неполный баланс: отдал больше, чем получил по данным (' + fmt(n.out) + ' > ' + fmt(n.in) + ').' });
    const top = (arr, key) => arr.slice().sort((a, b) => b.v - a.v).slice(0, 5).map(e => ({ gid: e[key].gid, role: e[key].role, v: e.v, vs: fmt(e.v), n: e.n }));
    return {
      gid: n.gid, role: n.role, roleLabel: ROLES[n.role][0], color: ROLES[n.role][1], glyph: ROLES[n.role][2],
      depth: n.d, depthLabel: COLS[n.d], p: n.p, seed: n.seed, cut: n.cut, agg: n.agg,
      in: n.in, out: n.out, inS: n.in ? fmt(n.in) : '—', outS: n.out ? fmt(n.out) : '—', cin: n.cin, cout: n.cout,
      payers: n.inE.length, receivers: n.agg ? 0 : n.outE.reduce((s, e) => s + (e.t.agg ? 83 : 1), 0),
      ratio: n.in && !n.seed ? (n.out / n.in).toFixed(2).replace('.', ',') : '—',
      seeds, flags, topIn: top(n.inE, 's'), topOut: top(n.outE, 't'),
    };
  }

  class MoneyFlow extends HTMLElement {
    connectedCallback() {
      if (this._init) return; this._init = true;
      this.style.display = 'block'; this.style.position = 'relative'; this.style.width = this.style.width || '100%'; this.style.height = this.style.height || '100%';
      this.style.overflow = 'hidden';
      const st = document.createElement('style');
      st.textContent = '@keyframes mfmove{to{stroke-dashoffset:-24}} money-flow .fl{stroke-dasharray:3 9;opacity:0} money-flow .hl .fl{opacity:1} ' +
        '@media (prefers-reduced-motion:no-preference){money-flow.anim .hl .fl{animation:mfmove 1s linear infinite}} money-flow .el{opacity:0;transition:opacity .15s} money-flow g.eg:hover .el, money-flow.zoomed .hl .el{opacity:1}';
      this.appendChild(st);
      this.classList.add('anim');
      this.data = buildData(); this.nodes = this.data.N.filter(n => !n.agg).map(n => ({ gid: n.gid, role: n.role, roleLabel: ROLES[n.role][0], color: ROLES[n.role][1], p: n.p, depth: n.d }));
      this.sel = this.getAttribute('selected') || '100482';
      loadD3().then(d3 => { this.d3 = d3; this.render(); this.select(this.sel); });
      this._ro = new ResizeObserver(() => { if (this.d3) { clearTimeout(this._rt); this._rt = setTimeout(() => { this.render(); this.select(this.sel, true); }, 60); } });
      this._ro.observe(this);
    }
    disconnectedCallback() { this._ro && this._ro.disconnect(); }

    layout(W, H) {
      const { N } = this.data, top = 70, bot = 36, padX = Math.max(70, W * 0.07);
      const byD = [0, 1, 2, 3, 4].map(d => N.filter(n => n.d === d));
      const place = () => byD.forEach(col => { const h = (H - top - bot) / col.length; col.forEach((n, i) => { n.y = top + (i + .5) * h; }); });
      N.forEach(n => { n.x = padX + n.d * (W - padX * 2) / 4; });
      place();
      const bary = (n, dir) => { const es = dir < 0 ? n.inE : n.outE; return es.length ? es.reduce((s, e) => s + (dir < 0 ? e.s : e.t).y * e.v, 0) / es.reduce((s, e) => s + e.v, 0) : n.y; };
      for (let it = 0; it < 4; it++) {
        for (let d = 1; d <= 4; d++) byD[d].sort((a, b) => bary(a, -1) - bary(b, -1));
        place();
        for (let d = 3; d >= 0; d--) byD[d].sort((a, b) => bary(a, 1) - bary(b, 1));
        place();
      }
      // узлы без исходящих (seed без переводов) — в конец колонки
      byD[0].sort((a, b) => (a.outE.length ? 0 : 1) - (b.outE.length ? 0 : 1)); place();
    }

    render() {
      const d3 = this.d3, cw = Math.max(1, this.clientWidth), ch = Math.max(1, this.clientHeight), W = Math.max(860, cw), H = Math.max(560, ch * W / cw);
      this.W = W; this.H = H;
      this.layout(W, H);
      const { N, E } = this.data;
      d3.select(this).selectAll('svg,.mf-tip').remove();
      const svg = d3.select(this).append('svg').attr('width', cw).attr('height', ch).attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet').style('display', 'block').style('font-family', "'IBM Plex Sans',sans-serif");
      this.svg = svg;
      const defs = svg.append('defs');
      defs.append('pattern').attr('id', 'mfhatch').attr('width', 8).attr('height', 8).attr('patternUnits', 'userSpaceOnUse').attr('patternTransform', 'rotate(45)')
        .append('line').attr('x1', 0).attr('y1', 0).attr('x2', 0).attr('y2', 8).attr('stroke', '#2a2e36').attr('stroke-width', 2);
      defs.append('marker').attr('id', 'mfarrow').attr('viewBox', '0 0 10 10').attr('refX', 8).attr('refY', 5).attr('markerWidth', 9).attr('markerHeight', 9).attr('markerUnits', 'userSpaceOnUse').attr('orient', 'auto')
        .append('path').attr('d', 'M1 1L9 5L1 9z').attr('fill', '#6b717c');
      const root = svg.append('g'); this.root = root;
      const colW = (W - Math.max(70, W * 0.07) * 2) / 4, x4 = N.find(n => n.d === 4).x;
      root.append('rect').attr('x', x4 - colW * .42).attr('y', 30).attr('width', colW * .84).attr('height', H - 44).attr('rx', 10).attr('fill', 'url(#mfhatch)').attr('stroke', '#30353e').attr('stroke-dasharray', '4 4');
      root.selectAll('.ch').data(COLS).join('text').attr('x', (d, i) => N.find(n => n.d === i).x).attr('y', 22).attr('text-anchor', 'middle')
        .style('font', "600 12px 'IBM Plex Mono'").style('letter-spacing', '.06em').style('fill', (d, i) => i === 4 ? '#c9b37a' : '#8a909b')
        .text((d, i) => d.toUpperCase() + '  ' + N.filter(n => n.d === i && !n.agg).length);
      root.append('text').attr('x', x4).attr('y', 48).attr('text-anchor', 'middle').style('font', "500 11px 'IBM Plex Sans'").style('fill', '#c9b37a').text('обрыв выборки');
      const w = d3.scaleSqrt().domain([0, d3.max(E, e => e.v)]).range([1, 11]);
      const path = e => { const x1 = e.s.x + e.s.r + 2, x2 = e.t.x - e.t.r - 6, m = (x1 + x2) / 2; return `M${x1},${e.s.y}C${m},${e.s.y} ${m},${e.t.y} ${x2},${e.t.y}`; };
      const tip = d3.select(this).append('div').attr('class', 'mf-tip').style('position', 'absolute').style('pointer-events', 'none').style('display', 'none')
        .style('background', '#1b1e24').style('border', '1px solid #363b45').style('border-radius', '8px').style('padding', '9px 11px').style('box-shadow', '0 10px 30px rgba(0,0,0,.5)')
        .style('font', "13px/1.45 'IBM Plex Sans'").style('color', '#d3d7dd').style('max-width', '260px').style('z-index', 5);
      const showTip = (ev, html) => { const b = this.getBoundingClientRect(); tip.style('display', 'block').html(html).style('left', (ev.clientX - b.left + 14) + 'px').style('top', (ev.clientY - b.top + 14) + 'px'); };
      const hideTip = () => tip.style('display', 'none');
      const mono = s => `<span style="font:600 13px 'IBM Plex Mono';color:#fff">${s}</span>`;

      this.eg = root.append('g').selectAll('g').data(E).join('g').attr('class', 'eg').style('cursor', 'default')
        .on('mousemove', (ev, e) => showTip(ev, `${mono(e.s.gid + ' → ' + e.t.gid)}<div style="font:600 15px 'IBM Plex Mono';color:#fff;margin:3px 0">${fmtFull(e.v)}</div>${e.n} тр.`))
        .on('mouseleave', hideTip);
      this.eg.append('path').attr('d', path).attr('fill', 'none').attr('stroke', '#4a505b').attr('stroke-opacity', .7).attr('stroke-width', e => w(e.v)).attr('marker-end', 'url(#mfarrow)');
      this.eg.append('path').attr('d', path).attr('fill', 'none').attr('stroke', 'transparent').attr('stroke-width', e => Math.max(10, w(e.v) + 6));
      this.eg.append('path').attr('class', 'fl').attr('d', path).attr('fill', 'none').attr('stroke', e => ROLES[e.s.role][1]).attr('stroke-linecap', 'round')
        .attr('stroke-width', e => Math.max(2, w(e.v) * .55)).style('pointer-events', 'none');
      const lab = this.eg.append('g').attr('class', 'el').style('pointer-events', 'none')
        .attr('transform', e => { const x1 = e.s.x + e.s.r + 2, x2 = e.t.x - e.t.r - 6, t = .3, u = 1 - t, m = (x1 + x2) / 2; const x = u*u*u*x1 + 3*u*u*t*m + 3*u*t*t*m + t*t*t*x2, y = u*u*u*e.s.y + 3*u*u*t*e.s.y + 3*u*t*t*e.t.y + t*t*t*e.t.y; return `translate(${x},${y})`; });
      lab.append('rect').attr('x', -34).attr('y', -9).attr('width', 68).attr('height', 18).attr('rx', 4).attr('fill', '#0e1014').attr('stroke', '#2c3038');
      lab.append('text').attr('text-anchor', 'middle').attr('y', 4).style('font', "500 11px 'IBM Plex Mono'").style('fill', '#e3e6eb').text(e => fmt(e.v));

      this.ng = root.append('g').selectAll('g').data(N).join('g').attr('transform', n => `translate(${n.x},${n.y})`).style('cursor', 'pointer')
        .on('click', (ev, n) => { ev.stopPropagation(); this.select(n.gid); })
        .on('mousemove', (ev, n) => showTip(ev, `${mono(n.agg ? 'ещё 83 получателя 203117' : n.gid)} <span style="color:${ROLES[n.role][1]};font-weight:600">${n.agg ? '' : ROLES[n.role][0]}</span>
          <div>${COLS[n.d]}${n.agg ? '' : ' · приоритет ' + n.p.toFixed(2)}</div><div>Вход ${n.in ? fmt(n.in) : '—'} · выход ${n.out ? fmt(n.out) : '—'}</div>
          ${n.cut ? '<div style="color:#e6c46a">обрыв выборки — исходящие не прослежены</div>' : ''}${n.seed && !n.cout ? '<div style="color:#e6c46a">seed без исходящих переводов</div>' : ''}`))
        .on('mouseleave', hideTip);
      this.ng.append('circle').attr('class', 'ring').attr('r', n => n.r + 6).attr('fill', 'none').attr('stroke', '#fff').attr('stroke-width', 1.5).attr('opacity', 0);
      this.ng.filter(n => !n.agg).append('circle').attr('r', n => n.r).attr('fill', n => ROLES[n.role][1]).attr('fill-opacity', n => n.cut ? .45 : 1)
        .attr('stroke', n => n.seed ? '#fff' : n.cut ? '#b5bac3' : '#0e1014').attr('stroke-width', n => n.seed ? 2.5 : 1.5).attr('stroke-dasharray', n => n.cut ? '3 2.5' : null);
      this.ng.filter(n => !n.agg).append('text').attr('text-anchor', 'middle').attr('dy', '.35em').style('font', n => `700 ${Math.round(n.r * .95)}px 'IBM Plex Sans'`)
        .style('fill', n => n.cut ? '#e3e6eb' : '#0e1014').style('pointer-events', 'none').text(n => ROLES[n.role][2]);
      const agg = this.ng.filter(n => n.agg);
      agg.append('rect').attr('x', -30).attr('y', -13).attr('width', 60).attr('height', 26).attr('rx', 13).attr('fill', 'rgba(138,144,155,.2)').attr('stroke', '#b5bac3').attr('stroke-dasharray', '3 2.5');
      agg.append('text').attr('text-anchor', 'middle').attr('dy', '.35em').style('font', "600 12px 'IBM Plex Mono'").style('fill', '#e3e6eb').text('+83');
      this.ng.append('text').attr('class', 'gl').attr('text-anchor', n => n.d === 0 ? 'end' : 'middle').attr('x', n => n.d === 0 ? -n.r - 8 : 0).attr('y', n => n.d === 0 ? 4 : n.agg ? 28 : n.r + 14)
        .style('font', "500 11.5px 'IBM Plex Mono'").style('fill', '#aab0ba').style('pointer-events', 'none')
        .text(n => n.agg ? 'получателей' : n.gid);
      this.ng.filter(n => n.seed && !n.outE.length).append('text').attr('x', n => n.r + 8).attr('y', 4).style('font', "500 11px 'IBM Plex Sans'").style('fill', '#e6c46a').text('нет исходящих');
      this.ng.filter(n => n.cut && !n.agg).append('text').attr('x', n => n.r + 8).attr('y', 4).style('font', "500 10.5px 'IBM Plex Sans'").style('fill', '#c9b37a').text('обрыв');

      svg.on('click', () => this.select(null));
      this.zoom = d3.zoom().scaleExtent([.5, 4]).on('zoom', ev => { root.attr('transform', ev.transform); this.classList.toggle('zoomed', ev.transform.k > 1.5); });
      svg.call(this.zoom).on('dblclick.zoom', null);
    }

    select(gid, silent) {
      this.sel = gid;
      if (!this.ng) return;
      const n = gid && this.data.by.get(String(gid));
      if (!n) {
        this.ng.style('opacity', 1).select('.ring').attr('opacity', 0); this.eg.style('opacity', 1).classed('hl', false).classed('eg', true);
        if (!silent) this.emit(null); return;
      }
      const up = walk(n, -1), dn = walk(n, 1), on = new Set([...up, ...dn]);
      this.ng.style('opacity', x => on.has(x) ? 1 : .15).select('.ring').attr('opacity', x => x === n ? .9 : 0);
      this.eg.each(function (e) { this.__on = (up.has(e.s) && up.has(e.t)) || (dn.has(e.s) && dn.has(e.t)); })
        .style('opacity', function () { return this.__on ? 1 : .08; }).classed('hl', function () { return this.__on; }).classed('eg', true);
      this.emit(summary(n));
    }
    emit(detail) { this.dispatchEvent(new CustomEvent('nodeselect', { detail, bubbles: true, composed: true })); }

    focusNode(gid) {
      const n = this.data && this.data.by.get(String(gid).trim());
      if (!n || !this.svg) return false;
      this.select(n.gid);
      this.svg.transition().duration(600).call(this.zoom.transform, this.d3.zoomIdentity.translate(this.W / 2, this.H / 2).scale(1.8).translate(-n.x, -n.y));
      return true;
    }
    fit() { this.svg && this.svg.transition().duration(400).call(this.zoom.transform, this.d3.zoomIdentity); }
    setAnimate(on) { this.classList.toggle('anim', !!on); }
  }
  if (!customElements.get('money-flow')) customElements.define('money-flow', MoneyFlow);
})();
