import uPlot from '/lib/uplot/uPlot.esm.js';

const body = document.querySelector('#design-table tbody');
const status = document.querySelector('output');
const fixed = (n, digits = 2) => Number.isFinite(n) ? n.toFixed(digits) : '—';

function link(item) {
  const a = document.createElement('a');
  a.textContent = item.name;
  a.href = '/?inspect=' + encodeURIComponent(item.id);
  return a;
}

const host = document.querySelector('#progress-plot');
let chart, chartMode;
new ResizeObserver(() => chart?.setSize({ width: host.clientWidth, height: 200 })).observe(host);

function progress(standard, fast, byName) {
  const trials = screens => screens.filter(i => i.design.optimizer?.phase === 'screen');
  const original = trials(standard);
  const fastSeed = fast.find(i => i.design.optimizer.phase === 'seed');
  const seed = byName.get(fastSeed?.design.parent ?? original[0]?.design.optimizer.seed);
  if (!seed) return;
  const manual = standard.slice(standard.indexOf(seed) + 1).filter(i => !i.design.optimizer);
  const groups = fastSeed ?
    [[seed, original, 'Standard mesh'], [fastSeed, trials(fast), 'Eight-cell mesh']] :
    [[seed, manual, 'Manual'], [seed, original, 'COBYQA']];
  const times = new Set([0]);
  const lines = groups.map(([start, items]) => {
    let best = start.design.metrics.score;
    let seconds = 0;
    const points = new Map([[0, best]]);
    for (const { design } of items) {
      seconds += design.wall_s;
      best = Math.min(best, design.metrics.score);
      points.set(seconds, best);
      times.add(seconds);
    }
    return points;
  });
  const xs = [...times].sort((a, b) => a - b);
  const data = [xs.map(s => s / 60), ...lines.map(line => xs.map(x => line.get(x) ?? null))];
  host.hidden = false;
  const mode = groups[1][2];
  if (chartMode === mode) return chart.setData(data);
  chart?.destroy();
  chartMode = mode;
  const series = (label, stroke) => ({
    label, stroke, spanGaps: true, paths: uPlot.paths.stepped({ align: 1 }),
    points: { show: true, size: 4 },
  });
  chart = new uPlot({
    width: host.clientWidth, height: 200, scales: { x: { time: false } },
    axes: [{ label: 'Cumulative screening time after seed (min)', labelSize: 16, size: 32 },
      { label: 'Best miss (dB)', labelSize: 16, size: 50 }],
    series: [{ label: 'Minutes' }, series(groups[0][2], '#627586'), series(mode, '#116582')],
  }, data, host);
}

let previous;
async function refresh() {
  try {
    const reply = await fetch('/api/history');
    const { enabled, runs, activity, optimization, error } = await reply.json();
    const fast = runs.filter(i => i.design.optimizer && i.design.half_gap_caps_mm?.length === 4);
    const completed = fast.filter(i => i.design.optimizer.phase === 'screen');
    if (!reply.ok) throw Error(error);
    const state = JSON.stringify(runs);
    if (state !== previous) {
      const byName = new Map(runs.map(item => [item.name, item]));
      const graded = runs.some(item => item.design.gap_refinement);
      const standard = runs.filter(item => !item.design.spot_ghz && !item.design.half_gap_caps_mm &&
        !item.name.endsWith('-mesh-check') && (!graded || item.design.gap_refinement === 1));
      const best = (fast.length ? fast : standard).reduce((a, b) =>
        !a || b.design.metrics.score < a.design.metrics.score ? b : a, null);
      progress(standard, fast, byName);
      const rows = runs.map(item => {
        const { parent, reason, metrics: m, wall_s: wall } = item.design;
        const row = document.createElement('tr');
        row.classList.toggle('best-design', item === best);
        const range = fixed(m.coupling_min) + ' … ' + fixed(m.coupling_max);
        const gapMesh = item.design.gap_mesh_label ?? (item.design.gap_refinement ?
          'Edge bands ×' + item.design.gap_refinement : 'Uniform gap');
        const spots = item.design.spot_ghz;
        const sampling = spots ? 'Spot · ' + spots.map(f => Number(f.toFixed(3))).join(', ') +
          ' GHz' : '100-point sweep';
        const opt = item.design.optimizer;
        const step = opt?.phase === 'screen' ? opt.evaluation + ' / ' + opt.generation :
          opt?.phase === 'validation' ? 'Check' : '—';
        for (const value of [link(item), byName.has(parent) ? link(byName.get(parent)) : '—',
          step, reason, gapMesh, sampling + (item.design.device ? ' · ' + item.design.device : ''),
          range, fixed(m.directivity_min), fixed(m.worst_ghz, 3),
          fixed(m.return_loss_min),
          fixed(m.through_loss_max), spots ? '—' : fixed(m.score), fixed(wall / 60, 1)]) {
          row.insertCell().append(value);
        }
        return row;
      });
      body.replaceChildren(...rows);
      previous = state;
    }
    const summary = optimization ? optimization.winner + ' · full-band gain ' +
      fixed(optimization.band_gain_db) + ' dB · finer-mesh spot gain ' +
      fixed(optimization.validation_gain_db) + ' dB' : '';
    const minutes = completed.map(i => i.design.wall_s / 60).sort((a, b) => a - b);
    const n = minutes.length;
    const median = (minutes[Math.floor(n / 2)] + minutes[Math.floor((n - 1) / 2)]) / 2;
    const timing = n ? '8-cell screens ' + n + '/' + completed[0].design.optimizer.budget +
      ' · median ' + fixed(median, 1) + ' min · range ' + fixed(minutes[0], 1) + '–' +
      fixed(minutes[n - 1], 1) + ' min' : '';
    status.textContent = enabled ? [activity, timing, summary, runs.length + ' completed']
      .filter(Boolean).join(' · ') :
      'Open the viewer with --history to inspect a design study.';
  } catch (e) {
    status.textContent = 'Could not update design history. ' + e.message;
  } finally {
    setTimeout(refresh, 10000);
  }
}
refresh();
