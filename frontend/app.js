'use strict';

const byId = (id) => document.getElementById(id);
const scenarioSelect = byId('scenario');
const canvas = byId('network');
const context = canvas.getContext('2d');
const dialog = byId('upload-dialog');
const displayNumber = new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 2});
const pageSize = 6;
const palette = {500: '#f4b66e', 220: '#c5f474', 110: '#72cbd3'};
const tables = {
  nodes: [['number', 'Узел'], ['nominal', 'Номинал, кВ'], ['voltage', 'Напряжение, кВ'], ['angle', 'Фазовый угол, °']],
  lines: [['number', 'Ветвь'], ['from', 'Начальный узел'], ['to', 'Конечный узел'], ['current', 'Макс. ток, А'], ['load', 'Загрузка, %']],
};
const state = {scenarios: demoScenarios, demo: true, view: 'nodes', page: 0, selected: null, zoom: 1, positions: []};

function format(value) {
  return Number.isFinite(value) ? displayNumber.format(value) : '—';
}

function currentScenario() {
  return state.scenarios[Number(scenarioSelect.value)];
}

function loadScenarios(scenarios, demo) {
  state.scenarios = scenarios;
  state.demo = demo;
  scenarioSelect.replaceChildren(...scenarios.map((scenario, index) => new Option(scenario.id, index)));
  byId('data-source').textContent = demo ? 'Демо-данные' : 'Загруженные данные';
  showScenario();
}

function showScenario() {
  const scenario = currentScenario();
  const {id, valid, probability, nodes, lines} = scenario;
  if (!Number.isFinite(nodes[0]?.x)) layoutNetwork(scenario);
  state.page = 0;
  state.selected = null;
  state.zoom = 1;
  byId('search').value = '';
  byId('network-count').textContent = nodes.length + ' узлов · ' + lines.length + ' ветвей';
  byId('status-card').classList.toggle('invalid', !valid);
  byId('status-title').textContent = valid ? 'Режим сходится' : 'Режим не сходится';
  byId('status-symbol').textContent = valid ? '✓' : '!';
  byId('probability').textContent = format(probability * 100) + ' %';
  byId('probability-fill').style.width = 100 * probability + '%';
  const values = [
    ['min-voltage', nodes, 'voltage', Math.min, 'кВ'],
    ['max-current', lines, 'current', Math.max, 'А'],
    ['max-load', lines, 'load', Math.max, '%'],
  ];
  for (const [element, rows, key, aggregate, unit] of values) {
    const numbers = rows.map((row) => row[key]).filter(Number.isFinite);
    const label = document.createElement('small');
    label.textContent = ' ' + unit;
    byId(element).replaceChildren(format(numbers.length ? aggregate(...numbers) : null), label);
  }
  byId('results-subtitle').textContent = 'Сценарий ' + id + (
    valid ? ' · прогноз по узлам и ветвям' : ' · значения для режима с низкой вероятностью сходимости');
  byId('node-caption').textContent = 'Выберите узел на схеме';
  renderTable();
  drawNetwork();
}

function renderTable() {
  const scenario = currentScenario();
  const columns = tables[state.view];
  const query = byId('search').value.trim().replace(/^№\s*/, '');
  const filtered = scenario[state.view].filter((row) => String(row.number).includes(query));
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  state.page = Math.min(state.page, pages - 1);
  const start = state.page * pageSize;

  for (const button of document.querySelectorAll('[data-view]')) {
    button.setAttribute('aria-pressed', String(button.dataset.view === state.view));
    button.querySelector('span').textContent = scenario[button.dataset.view].length;
  }
  const headings = document.createElement('tr');
  for (const [, title] of columns) {
    const th = document.createElement('th');
    th.scope = 'col';
    th.textContent = title;
    headings.append(th);
  }
  byId('table-head').replaceChildren(headings);

  const rows = [];
  for (const entry of filtered.slice(start, start + pageSize)) {
    const row = document.createElement('tr');
    row.classList.toggle('selected', state.view === 'nodes' && state.selected === entry.number);
    for (const [key] of columns) {
      const cell = document.createElement('td');
      cell.textContent = key === 'number' ? '№ ' + entry.number : format(entry[key]);
      row.append(cell);
    }
    rows.push(row);
  }
  if (!rows.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = columns.length;
    cell.className = 'empty-cell';
    cell.textContent = 'Совпадений нет';
    row.append(cell);
    rows.push(row);
  }
  byId('table-body').replaceChildren(...rows);
  byId('row-count').textContent = filtered.length ? (start + 1) + '–' + Math.min(start + pageSize, filtered.length) + ' из ' + filtered.length : '0 строк';
  byId('page-count').textContent = (state.page + 1) + ' / ' + pages;
  byId('prev').disabled = state.page === 0;
  byId('next').disabled = state.page === pages - 1;
}

function layoutNetwork(scenario) {
  const positions = scenario.nodes.map((node, index) => {
    const angle = index * Math.PI * (3 - Math.sqrt(5));
    const radius = .4 * Math.sqrt((index + .5) / scenario.nodes.length);
    return {number: node.number, x: .5 + Math.cos(angle) * radius, y: .5 + Math.sin(angle) * radius};
  });
  const lookup = new Map(positions.map((position) => [position.number, position]));
  const links = scenario.lines
    .map((line) => [lookup.get(line.from), lookup.get(line.to)])
    .filter(([from, to]) => from && to && from !== to);
  for (let iteration = 0; iteration < 145; iteration += 1) {
    const step = .16 * (1 - iteration / 150);
    for (let i = 0; i < positions.length; i += 1) {
      const a = positions[i];
      for (const b of positions.slice(i + 1)) {
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const force = step * .002 / Math.max(.001, dx * dx + dy * dy);
        a.x += dx * force;
        a.y += dy * force;
        b.x -= dx * force;
        b.y -= dy * force;
      }
    }
    for (const [a, b] of links) {
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const distance = Math.max(.01, Math.hypot(dx, dy));
      const force = step * .37 * (distance - .12) / distance;
      a.x -= dx * force;
      a.y -= dy * force;
      b.x += dx * force;
      b.y += dy * force;
    }
    for (const position of positions) {
      position.x = Math.max(.02, Math.min(.98, position.x + (.5 - position.x) * step * .3));
      position.y = Math.max(.03, Math.min(.97, position.y + (.5 - position.y) * step * .3));
    }
  }
  for (const [i, node] of scenario.nodes.entries()) {
    node.x = positions[i].x * 100;
    node.y = positions[i].y * 82 + 12;
  }
}

function drawNetwork() {
  const scenario = currentScenario();
  if (!context || !scenario) return;
  const {width, height} = canvas.getBoundingClientRect();
  if (!width || !height) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  const side = width < 480 ? 12 : 30;
  const points = new Map(scenario.nodes.map((node) => [node.number, {
    ...node,
    px: width / 2 + (side + node.x / 100 * (width - 2 * side) - width / 2) * state.zoom,
    py: height / 2 + (14 + (node.y - 12) / 82 * (height - 32) - height / 2) * state.zoom,
  }]));
  state.positions = [...points.values()];
  const groups = new Map();
  let missingConnections = 0;
  for (const line of scenario.lines) {
    const from = points.get(line.from);
    const to = points.get(line.to);
    if (!from || !to) {
      missingConnections += 1;
      continue;
    }
    const key = [from.number, to.number].sort((a, b) => a - b).join('/');
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push({line, from, to});
  }
  for (const paths of groups.values()) {
    for (const [index, {line, from, to}] of paths.entries()) {
      const selected = state.selected === from.number || state.selected === to.number;
      const color = palette[from.nominal] || '#aac7b7';
      const distance = Math.hypot(to.px - from.px, to.py - from.py) || 1;
      const direction = from.number < to.number ? 1 : -1;
      const offset = (index - (paths.length - 1) / 2) * 11 * direction;
      context.beginPath();
      context.moveTo(from.px, from.py);
      if (from.number === to.number) {
        context.bezierCurveTo(from.px + 20, from.py - 27, from.px - 20, from.py - 27, from.px, from.py);
      } else {
        context.quadraticCurveTo(
          (from.px + to.px) / 2 - (to.py - from.py) / distance * offset,
          (from.py + to.py) / 2 + (to.px - from.px) / distance * offset,
          to.px, to.py,
        );
      }
      context.strokeStyle = (line.load >= 100 ? '#f2a477' : color) + (selected ? 'de' : '55');
      context.lineWidth = selected ? 2.25 : 1.05;
      context.stroke();
    }
  }
  const compact = width < 480;
  context.textAlign = 'center';
  context.textBaseline = 'bottom';
  context.font = (compact ? '9' : '10') + 'px Segoe UI, sans-serif';
  for (const node of state.positions) {
    const color = palette[node.nominal] || '#aac7b7';
    const selected = node.number === state.selected;
    const size = compact ? 3.2 : 4.2;
    context.beginPath();
    context.arc(node.px, node.py, selected ? 10 : size + 3, 0, Math.PI * 2);
    context.fillStyle = color + (selected ? '60' : '27');
    context.fill();
    context.beginPath();
    context.arc(node.px, node.py, size, 0, Math.PI * 2);
    context.fillStyle = color;
    context.fill();
    context.lineWidth = 2.5;
    context.strokeStyle = '#102824';
    context.strokeText(String(node.number), node.px, node.py - size - 4);
    context.fillStyle = selected ? '#fff' : '#c5d8cb';
    context.fillText(String(node.number), node.px, node.py - size - 4);
  }
  byId('zoom-out').disabled = state.zoom <= 1;
  byId('zoom-in').disabled = state.zoom >= 1.9;
  byId('zoom-reset').disabled = state.zoom === 1;
  byId('map-note').hidden = !missingConnections;
  byId('map-note').textContent = missingConnections ? 'Ветви с неизвестным узлом: ' + missingConnections : '';
}

function nearestNode(event) {
  const {left, top} = canvas.getBoundingClientRect();
  const matches = state.positions.map((node) => ({
    node, distance: Math.hypot(node.px - event.clientX + left, node.py - event.clientY + top),
  }));
  return matches.sort((a, b) => a.distance - b.distance).find((match) => match.distance < 16)?.node;
}

function csvCell(value) {
  const text = String(value ?? '');
  return /[",\r\n]/.test(text) ? '"' + text.replaceAll('"', '""') + '"' : text;
}

function downloadResults() {
  const scenario = currentScenario();
  const isNodes = state.view === 'nodes';
  const header = isNodes ? ['ID_опыта', 'Номер', 'V', 'Delta', 'Regime_valid'] : ['ID_опыта', 'Номер', 'Imax, A', 'Izarg, %'];
  const ordered = [...scenario[state.view]].sort((a, b) => (a.sourceOrder ?? a.number) - (b.sourceOrder ?? b.number));
  const entries = ordered.map((row) => isNodes
    ? [scenario.id, row.number, row.voltage, row.angle, Number(scenario.valid)]
    : [scenario.id, row.number, row.current, row.load]);
  const csv = [header, ...entries].map((row) => row.map(csvCell).join(',')).join('\r\n') + '\r\n';
  const url = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'pred_' + state.view + '.csv';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function showUploadFeedback(message, error = false) {
  const feedback = byId('upload-feedback');
  feedback.hidden = !message;
  feedback.textContent = message;
  feedback.classList.toggle('error', error);
}

async function upload(event) {
  event.preventDefault();
  const button = byId('submit-upload');
  if (button.disabled) return;
  if (location.protocol === 'file:') {
    showUploadFeedback('Для расчёта запустите python serve.py из папки проекта и откройте адрес, показанный в терминале.', true);
    return;
  }
  button.disabled = true;
  byId('close-upload').disabled = true;
  showUploadFeedback('Проверяем файлы и выполняем прогноз…');
  try {
    const response = await fetch('/api/predict', {method: 'POST', body: new FormData(event.currentTarget)});
    const result = await response.json().catch(() => null);
    if (!response.ok || !result?.scenarios?.length) {
      throw new Error(result?.error || 'Сервис прогноза недоступен. Проверьте запуск python serve.py.');
    }
    loadScenarios(result.scenarios, false);
    byId('upload-form').reset();
    dialog.close();
  } catch (error) {
    showUploadFeedback(error.message, true);
  } finally {
    button.disabled = false;
    byId('close-upload').disabled = false;
  }
}

scenarioSelect.addEventListener('change', showScenario);
for (const button of document.querySelectorAll('[data-view]')) {
  button.addEventListener('click', () => {
    state.view = button.dataset.view;
    state.page = 0;
    byId('search').value = '';
    renderTable();
  });
}
byId('search').addEventListener('input', () => { state.page = 0; renderTable(); });
byId('prev').addEventListener('click', () => { state.page -= 1; renderTable(); });
byId('next').addEventListener('click', () => { state.page += 1; renderTable(); });
byId('download').addEventListener('click', downloadResults);
for (const [name, delta] of [['out', -.3], ['reset', 0], ['in', .3]]) {
  byId('zoom-' + name).addEventListener('click', () => {
    state.zoom = delta ? Math.max(1, Math.min(1.9, Math.round((state.zoom + delta) * 10) / 10)) : 1;
    drawNetwork();
  });
}
canvas.addEventListener('pointermove', (event) => { canvas.style.cursor = nearestNode(event) ? 'pointer' : ''; });
canvas.addEventListener('click', (event) => {
  const node = nearestNode(event);
  if (!node) return;
  state.selected = node.number;
  state.view = 'nodes';
  byId('search').value = '';
  state.page = Math.floor(currentScenario().nodes.findIndex((entry) => entry.number === node.number) / pageSize);
  byId('node-caption').textContent = 'Узел № ' + node.number + ' · ' + format(node.voltage) + ' кВ';
  drawNetwork();
  renderTable();
});
byId('open-upload').addEventListener('click', () => { showUploadFeedback(''); dialog.showModal(); });
byId('close-upload').addEventListener('click', () => dialog.close());
dialog.addEventListener('cancel', (event) => { if (byId('submit-upload').disabled) event.preventDefault(); });
byId('upload-form').addEventListener('submit', upload);
new ResizeObserver(drawNetwork).observe(canvas);
loadScenarios(demoScenarios, true);
