import uPlot from '/lib/uplot/uPlot.esm.js';

const el = id => document.getElementById(id);
const colors = ['#176389', '#ac4f27', '#297556', '#764d99', '#91691d', '#4f6494'];
const near = (a, b) => Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b));
const label = t => 'S[' + t.port + ',' + t.drive + ']';
const number = v => v === '-inf' ? '−∞' : v == null ? '—' : Number(v.toPrecision(6)).toString();

export function resultsPanel(source, field, inspect) {
  const panel = el('results'), plot = el('plot'), body = el('results-body');
  const drive = el('plot-drive'), marker = el('plot-marker'), quantity = el('plot-quantity');
  const status = document.createTextNode('');
  el('plot-status').prepend(status);
  const node = el('results-node'), lifetime = new AbortController();
  let traces = [], active = [], samples = [], saved = new Map(), index = 0;
  let selection, inspecting = false, chart;
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

  function focusTrace(trace) {
    selection = trace;
    active.forEach((t, i) => {
      if (chart) chart.series[i + 1].width = t === selection ? 2.5 : 1.5;
    });
  }

  function selectResult(trace) {
    inspecting = true;
    focusTrace(trace);
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

  // These annotations link the library chart to the field frames available in this run.
  function markFields(u) {
    const ctx = u.ctx, box = u.bbox, ratio = uPlot.pxRatio;
    const x = u.valToPos(frequency(), 'x', true);
    if (!Number.isFinite(x)) return;
    ctx.save();
    ctx.strokeStyle = ctx.fillStyle = '#405a6e';
    ctx.lineWidth = ratio;
    ctx.setLineDash([3 * ratio, 3 * ratio]);
    ctx.beginPath();
    ctx.moveTo(x, box.top);
    ctx.lineTo(x, box.top + box.height);
    ctx.stroke();
    for (const f of saved.keys()) {
      const px = u.valToPos(f, 'x', true), py = box.top + box.height;
      ctx.save();
      ctx.translate(px, py);
      ctx.rotate(Math.PI / 4);
      ctx.fillRect(-2 * ratio, -2 * ratio, 4 * ratio, 4 * ratio);
      ctx.restore();
    }
    ctx.restore();
  }

  function buildChart() {
    chart?.destroy();
    chart = null;
    if (!samples.length || body.hidden || !plot.clientWidth) return;
    const q = Number(quantity.value);
    const values = active.map(trace => samples.map(f => {
      const v = trace.points.get(f)?.[q];
      return Number.isFinite(v) ? v : null;
    }));
    const series = active.map((trace, i) => ({
      label: label(trace), stroke: trace.color, width: trace === selection ? 2.5 : 1.5,
      show: !hidden.has(trace),
      points: { show: samples.length <= 100, size: 4 },
      gaps: (u, _series, first, last, gaps) => {
        if (q === 2) {
          for (let j = first + 1; j <= last; j++) {
            const a = values[i][j - 1], b = values[i][j];
            if (a != null && b != null && Math.abs(b - a) > 180) {
              gaps.push([u.valToPos(samples[j - 1], 'x', true), u.valToPos(samples[j], 'x', true)]);
            }
          }
          gaps.sort((a, b) => a[0] - b[0]);
        }
        return gaps;
      },
    }));
    const axis = { font: '10px monospace', stroke: '#4d606f', grid: { stroke: '#d8e1e6' },
      ticks: { size: 4, stroke: '#9caeb9' }, labelFont: '11px sans-serif', labelSize: 15 };
    chart = new uPlot({
      width: plot.clientWidth, height: plot.clientHeight,
      legend: { show: false }, cursor: { show: false },
      scales: { x: { time: false, range: (_u, lo, hi) =>
        lo === hi ? [lo - 0.05, hi + 0.05] : [lo, hi] } },
      axes: [{ ...axis, size: 25, label: 'Frequency (GHz)' },
        { ...axis, size: 40, label: q === 1 ? 'Magnitude (dB)' : 'Phase (°)' }],
      series: [{}, ...series], hooks: { draw: [markFields] },
    }, [samples, ...values], plot);
  }

  function draw() {
    if (panel.hidden || body.hidden || !samples.length) return;
    if (!chart) { buildChart(); return; }
    if (chart.width !== plot.clientWidth || chart.height !== plot.clientHeight) {
      chart.setSize({ width: plot.clientWidth, height: plot.clientHeight });
    } else chart.redraw(false);
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
        chart?.setSeries(i + 1, { show: check.checked });
      };
      button.textContent = label(trace);
      button.title = 'Inspect ' + label(trace);
      button.onclick = () => selectResult(trace);
      cell.append(check, button);
      row.insertCell();
      row.insertCell();
      trace.row = row;
    }
    buildChart();
    render();
  }

  drive.onchange = () => { configureDrive(frequency()); choose(index); };
  marker.onchange = () => choose(marker.selectedIndex);
  quantity.onchange = buildChart;
  plot.onclick = event => {
    if (!chart) return;
    const rect = chart.over.getBoundingClientRect();
    if (event.clientY < rect.top || event.clientY > rect.bottom) return;
    choose(chart.posToIdx(event.clientX - rect.left));
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
      focusTrace(null);
      node.classList.remove('selected');
      if (active.length) render();
    },
    dispose() { chart?.destroy(); observer.disconnect(); lifetime.abort(); status.remove(); },
  };
}
