const el = id => document.getElementById(id);
const colors = ['#176389', '#ac4f27', '#297556', '#764d99', '#91691d', '#4f6494'];
const near = (a, b) => Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b));
const label = t => 'S[' + t.port + ',' + t.drive + ']';
const number = v => v === '-inf' ? '−∞' : v == null ? '—' : Number(v.toPrecision(6)).toString();

function tickSpacing(range, count) {
  const rough = range / count;
  const unit = 10 ** Math.floor(Math.log10(rough));
  return [1, 2, 5, 10].find(n => n * unit >= rough) * unit;
}

function svgNode(type, attributes, text) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', type);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  if (text != null) node.textContent = text;
  return node;
}

export function resultsPanel(source, field, inspect) {
  const panel = el('results'), plot = el('plot'), body = el('results-body');
  const drive = el('plot-drive'), marker = el('plot-marker'), quantity = el('plot-quantity');
  const status = document.createTextNode('');
  el('plot-status').prepend(status);
  const node = el('results-node'), lifetime = new AbortController();
  let traces = [], active = [], samples = [], saved = new Map(), index = 0;
  let selection, inspecting = false, chartDomain;
  const hidden = new Set();
  panel.hidden = node.parentElement.hidden = true;
  const controls = [drive, marker, quantity, el('dock-toggle')];
  controls.forEach(control => { control.disabled = false; });
  quantity.value = '1';
  const frequency = () => samples[index];

  function properties() {
    if (!inspecting) return;
    const values = selection?.points.get(frequency());
    inspect(selection ? label(selection) : 'Port response', [
      ['Source', 'Palace · port-S.csv'], ['Drive', drive.value],
      ['Frequency', frequency() + ' GHz'],
      ...(selection ? [['Output port', selection.port], ['Magnitude (dB)', number(values?.[1])],
        ['Phase (°)', number(values?.[2])]] : [['Output traces', active.length]]),
      ['Volume field', saved.has(frequency()) ? 'Saved' : 'Unavailable'],
    ]);
  }

  function selectResult(trace) {
    inspecting = true;
    selection = trace;
    node.classList.add('selected');
    render();
  }

  function setOpen(open) {
    body.hidden = !open;
    el('dock-toggle').setAttribute('aria-expanded', open);
    if (open) draw();
  }
  el('dock-toggle').onclick = () => setOpen(body.hidden);
  node.onclick = () => { setOpen(true); selectResult(null); };

  function draw() {
    if (panel.hidden || body.hidden || !samples.length) return;
    const w = plot.clientWidth, h = plot.clientHeight;
    const left = 55, right = w - 15, top = 20, bottom = h - 30;
    if (right <= left || bottom <= top) return;
    const first = samples[0], last = samples.at(-1), q = Number(quantity.value);
    const x = f => first === last ? (left + right) / 2 :
      left + (f - first) / (last - first) * (right - left);
    chartDomain = { left, right, first, last };
    let low = Infinity, high = -Infinity;
    for (const trace of active) {
      if (hidden.has(trace)) continue;
      for (const point of trace.samples) {
        if (!Number.isFinite(point[q])) continue;
        low = Math.min(low, point[q]);
        high = Math.max(high, point[q]);
      }
    }
    if (!Number.isFinite(low)) { low = -1; high = 1; }
    const step = tickSpacing(high - low || 2, 4);
    low = Math.floor(low / step) * step;
    high = Math.ceil(high / step) * step;
    if (low === high) { low -= step; high += step; }
    const y = v => bottom - (v - low) / (high - low) * (bottom - top);
    const items = [];
    const line = (x1, y1, x2, y2, stroke, extra = {}) =>
      items.push(svgNode('line', { x1, x2, y1, y2, stroke, ...extra }));
    const text = (x, y, value, anchor = 'start') =>
      items.push(svgNode('text', { x, y, 'text-anchor': anchor }, value));
    text(left, 13, q === 1 ? 'Magnitude (dB)' : 'Phase (°)');
    text(right, h - 2, 'GHz', 'end');
    for (let k = 0; k <= Math.round((high - low) / step); k++) {
      const v = low + k * step, py = y(v);
      line(left, py, right, py, '#d8e1e6');
      text(left - 7, py + 3, number(v), 'end');
    }
    const ticks = Math.max(1, Math.min(10, Math.floor((right - left) / 70)));
    const dx = tickSpacing(last - first || 1, ticks);
    const tickStart = first === last ? first : Math.ceil(first / dx) * dx;
    for (let i = 0; tickStart + i * dx <= last; i++) {
      const v = tickStart + i * dx, px = x(v);
      line(px, top, px, bottom, '#e2e8ec');
      text(px, bottom + 16, String(Number(v.toPrecision(4))), 'middle');
    }
    for (const trace of active) {
      if (hidden.has(trace)) continue;
      let path = '', start = true, previous;
      for (const [f, db, angle] of trace.samples) {
        const value = q === 1 ? db : angle;
        if (!Number.isFinite(value)) { start = true; continue; }
        if (q === 2 && Math.abs(value - previous) > 180) start = true;
        previous = value;
        path += (start ? 'M' : 'L') + x(f) + ' ' + y(value);
        start = false;
        if (trace.samples.length <= 100 || f === frequency()) {
          items.push(svgNode('circle', { cx: x(f), cy: y(value), r: 2.2, fill: trace.color }));
        }
      }
      items.push(svgNode('path', { d: path, stroke: trace.color, fill: 'none',
        'stroke-width': trace === selection ? 2.5 : 1.5 }));
    }
    for (const f of saved.keys()) {
      items.push(svgNode('path', { d: 'M' + x(f) + ' ' + bottom + 'l3 3-3 3-3-3z',
        fill: '#4c677a' }));
    }
    line(x(frequency()), top, x(frequency()), bottom, '#283f50', { 'stroke-dasharray': '3 3' });
    plot.replaceChildren(...items);
  }

  function render() {
    marker.selectedIndex = index;
    status.textContent = saved.has(frequency()) ? '◆ Field saved ' : 'No saved field ';
    for (const trace of active) {
      const value = trace.points.get(frequency());
      trace.row.cells[1].textContent = number(value?.[1]);
      trace.row.cells[2].textContent = number(value?.[2]);
      trace.row.classList.toggle('selected', inspecting && trace === selection);
    }
    plot.setAttribute('aria-valuemin', samples[0]);
    plot.setAttribute('aria-valuemax', samples.at(-1));
    plot.setAttribute('aria-valuenow', frequency());
    plot.setAttribute('aria-valuetext', frequency() + ' GHz');
    properties();
    draw();
  }

  function choose(i) {
    index = Math.max(0, Math.min(samples.length - 1, i));
    field.selectSample(saved.get(frequency()), Number(drive.value), frequency());
    render();
  }

  function configureDrive(preferred) {
    active = traces.filter(t => t.drive === Number(drive.value));
    samples = [...new Set(active.flatMap(t => [...t.points.keys()]))].sort((a, b) => a - b);
    const frames = field.frames.filter(f => f.excitation === Number(drive.value) ||
      (f.excitation == null && drive.options.length === 1));
    saved = new Map();
    for (const frame of frames) {
      const f = samples.find(f => near(f, frame.ghz));
      if (f != null) saved.set(f, frame);
    }
    index = Math.max(0, samples.findIndex(f => near(f, preferred)));
    marker.replaceChildren(...samples.map(f => new Option(f + ' GHz', f)));
    el('trace-values').replaceChildren();
    selection = null;
    for (const [i, trace] of active.entries()) {
      trace.color = colors[i % colors.length];
      const row = el('trace-values').insertRow(), cell = row.insertCell();
      const check = document.createElement('input'), button = document.createElement('button');
      check.type = 'checkbox';
      check.checked = !hidden.has(trace);
      check.style.accentColor = trace.color;
      check.setAttribute('aria-label', 'Plot ' + label(trace));
      check.onchange = () => {
        if (check.checked) hidden.delete(trace);
        else hidden.add(trace);
        draw();
      };
      button.textContent = label(trace);
      button.title = 'Inspect ' + label(trace);
      button.onclick = () => selectResult(trace);
      cell.append(check, button);
      row.insertCell();
      row.insertCell();
      trace.row = row;
    }
    render();
  }

  drive.onchange = () => { configureDrive(frequency()); choose(index); };
  marker.onchange = () => choose(marker.selectedIndex);
  quantity.onchange = draw;
  plot.onclick = event => {
    if (!chartDomain) return;
    const { first, last, left, right } = chartDomain;
    const px = event.clientX - plot.getBoundingClientRect().left;
    const f = first + (px - left) * (last - first) / (right - left);
    choose(samples.reduce((best, v, i) =>
      Math.abs(v - f) < Math.abs(samples[best] - f) ? i : best, 0));
  };
  plot.onkeydown = event => {
    const keys = { ArrowLeft: index - 1, ArrowRight: index + 1, Home: 0, End: samples.length - 1 };
    if (Object.hasOwn(keys, event.key)) { event.preventDefault(); choose(keys[event.key]); }
  };
  const observer = new ResizeObserver(draw);
  observer.observe(plot);

  (async () => {
    try {
      const response = await fetch('/api/sweep?case=' + encodeURIComponent(source),
        { signal: lifetime.signal });
      const data = await response.json();
      await field.ready;
      if (lifetime.signal.aborted) return;
      if (!response.ok) throw Error(data.error || response.statusText);
      if (!data.length) return;
      traces = data;
      const drives = [...new Set(traces.map(t => t.drive))];
      drive.replaceChildren(...drives.map(d => new Option(d, d)));
      for (const t of traces) {
        t.points = new Map(t.samples.map(s => [s[0], s]));
      }
      panel.hidden = node.parentElement.hidden = false;
      setOpen(true);
      const initial = field.frames[0];
      if (drives.includes(initial?.excitation)) drive.value = initial.excitation;
      configureDrive(initial?.ghz);
    } catch (error) {
      if (lifetime.signal.aborted) return;
      panel.hidden = false;
      body.hidden = true;
      controls.forEach(control => { control.disabled = true; });
      status.textContent = error.message;
    }
  })();
  return {
    follow(frame) {
      if (!traces.length) return;
      const next = String(frame.excitation ?? (drive.options.length === 1 ? drive.value : ''));
      if (![...drive.options].some(o => o.value === next)) {
        status.textContent = 'Field drive has no matching port response ';
        return;
      }
      if (drive.value !== next) { drive.value = next; configureDrive(frame.ghz); }
      const i = samples.findIndex(f => near(f, frame.ghz));
      if (i >= 0) { index = i; render(); }
      else status.textContent = 'Field frequency has no matching port sample ';
    },
    deselect() {
      inspecting = false;
      selection = null;
      node.classList.remove('selected');
      if (active.length) render();
    },
    dispose() { observer.disconnect(); lifetime.abort(); status.remove(); },
  };
}
