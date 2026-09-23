/* Standalone viewer for the supplied design fixtures. All IDs remain strings. */
(async function () {
  const $ = (id) => document.getElementById(id);
  const status = $('status');
  const names = ['Граф денег', 'Рабочее место', 'Обзор сети', 'Схема потока D3', 'Карточка узла', 'Кластеры', 'Перечень на проверку', 'Компоненты и состояния', 'Запуск и устойчивость'];
  for (const name of names) { const a = document.createElement('a'); a.href = name + '.dc.html'; a.textContent = name; $('exports').append(a); }
  try {
    if (!window.d3) throw new Error('Не удалось загрузить D3. Проверьте подключение к интернету и обновите страницу.');
    const data = await DAI.load();
    const nodes = [...DAI.nodes.values()].sort((a, b) => (b.priority_score || 0) - (a.priority_score || 0));
    let selected = null, mode = 'overview';
    const hidden = new Set();
    const graph = DAIGraph.create($('graph'), { onSelect: select });
    graph.setData({ nodes, edges: [...DAI.edges.values()], clusters: data.clusters.items || [], top: data.top.items.slice(0, 5).map(n => n.gid), transfers: DAI.transfers() });
    function update(fit = false) {
      graph.setView({ mode, focus: selected, layout: $('layout').value, depth: +$('depth').value, colorBy: $('clusters').checked ? 'cluster' : 'role', flow: $('motion').checked ? 'dash' : 'arrows', roles: DAI.ROLE_ORDER.filter(r => !hidden.has(r)), charge: +$('charge').value, linkDist: +$('distance').value }, { fit });
      const count = graph.counts(); $('counts').textContent = count.n + ' узлов / ' + count.e + ' связей';
      $('overview').setAttribute('aria-pressed', mode === 'overview'); $('local').setAttribute('aria-pressed', mode === 'local');
      $('layout').disabled = mode === 'overview'; $('depth').disabled = mode === 'overview';
    }
    function list() {
      const q = $('search').value.trim(); $('node-list').replaceChildren();
      const matches = nodes.filter(n => n.gid.includes(q)); $('total').textContent = matches.length;
      for (const n of matches) {
        const b = document.createElement('button'); b.className = 'node-row' + (selected === n.gid ? ' active' : ''); b.setAttribute('aria-pressed', selected === n.gid);
        const dot = document.createElement('span'); dot.className = 'dot'; dot.style.background = DAI.role(n.role).dark || '#777';
        const label = document.createElement('span'); label.textContent = DAI.gidParts(n.gid).mid;
        const sub = document.createElement('small'); sub.textContent = DAI.role(n.role).title; label.append(sub);
        const score = document.createElement('span'); score.className = 'score'; score.textContent = DAI.score(n.priority_score);
        b.append(dot, label, score); b.onclick = () => { select(n.gid); graph.flyTo(n.gid); }; $('node-list').append(b);
      }
      if (!matches.length) $('node-list').textContent = 'Узлы не найдены';
    }
    function select(id) {
      selected = id; update(); list();
      const n = DAI.nodes.get(id) || { gid: id }; $('selection-state').textContent = 'Выбран в графе';
      const card = $('card'); card.replaceChildren();
      const title = document.createElement('div'); title.className = 'gid'; title.textContent = id;
      const role = document.createElement('div'); role.className = 'role-pill'; role.textContent = DAI.role(n.role).title;
      const metrics = document.createElement('div'); metrics.className = 'metrics';
      for (const [label, value] of [['Приоритет', DAI.score(n.priority_score)], ['Кластер', n.cluster_id ?? '—'], ['Входящие', n.in_kzt == null ? '—' : DAI.kztShort(n.in_kzt)], ['Исходящие', n.out_kzt == null ? '—' : DAI.kztShort(n.out_kzt)]]) {
        const cell = document.createElement('div'), small = document.createElement('small'), strong = document.createElement('strong'); small.textContent = label; strong.textContent = value; cell.append(small, strong); metrics.append(cell);
      }
      const evidence = document.createElement('p'); evidence.className = 'muted'; evidence.textContent = typeof n.evidence === 'string' ? n.evidence : n.evidence ? JSON.stringify(n.evidence) : 'Для этого узла подробное обоснование в демонстрационном пакете отсутствует.';
      const actions = document.createElement('div'); actions.className = 'card-actions';
      for (const [label, action] of [['Окрестность', () => { mode = 'local'; update(true); }], ['Найти на графе', () => graph.flyTo(id)]]) { const b = document.createElement('button'); b.textContent = label; b.onclick = action; actions.append(b); }
      card.append(title, role, metrics, evidence);
      if (n.is_seed || n.truncated_by_depth) { const note = document.createElement('p'); note.className = 'muted'; note.textContent = n.truncated_by_depth ? 'Граница выгрузки: исходящие связи могут отсутствовать.' : 'Seed: входящие переводы извне выборки не представлены.'; card.append(note); }
      card.append(actions);
    }
    for (const r of DAI.ROLE_ORDER) {
      const b = document.createElement('button'), dot = document.createElement('span'); dot.className = 'dot'; dot.style.background = DAI.role(r).dark;
      b.append(dot, document.createTextNode(DAI.role(r).title)); b.setAttribute('aria-pressed', 'true');
      b.onclick = () => { hidden.has(r) ? hidden.delete(r) : hidden.add(r); b.setAttribute('aria-pressed', !hidden.has(r)); update(); }; $('legend').append(b);
    }
    $('overview').onclick = () => { mode = 'overview'; update(true); };
    $('local').onclick = () => { if (!selected) select(nodes[0].gid); mode = 'local'; update(true); };
    for (const id of ['layout', 'depth', 'clusters', 'motion']) $(id).onchange = () => update(id === 'layout' || id === 'depth');
    for (const id of ['charge', 'distance']) $(id).oninput = () => update();
    $('search').oninput = list; $('fit').onclick = () => graph.fit(); $('zoom-in').onclick = () => graph.zoomBy(1.35); $('zoom-out').onclick = () => graph.zoomBy(1 / 1.35);
    $('motion').checked = !matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.addEventListener('pagehide', () => graph.destroy(), { once: true });
    update(true); list(); status.textContent = '';
  } catch (error) { status.textContent = error.message || 'Не удалось загрузить данные. Запустите страницу через HTTP-сервер.'; }
})();
