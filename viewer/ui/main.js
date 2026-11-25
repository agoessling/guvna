import { Viewport, regionColor } from './cad.js';
import { resultsPanel } from './results.js';
import { fieldLayer } from './field-layer.js';
import { addHelp, decorate, startInspection } from './inspector.js';

const el = (id) => document.getElementById(id);
const num = (v) => Number(v.toFixed(5)).toString();
const integer = (v) => v.toLocaleString();

function mountModel(input, source, stages, inputs) {
  let data = input, stage = 0, loading;
  const stageSelect = el('stage'), stageStats = el('stage-stats');
  const stageInfo = () => stages.find(s => s.id === stage);
  const stageName = id => id === 1 ? 'Initial solve' : 'Refinement ' + (id - 1);
  const cache = new Map();
  let field, results;
  const plotPrefs = { compare: 'overlay', quantity: '1', hidden: new Set() };
  const params = new URLSearchParams(location.search);
  const initialStage = params.get('inspect') === source ? Number(params.get('stage')) : 0;
  let responseOpen = !stages.length || stages.some(s => s.id === initialStage);
  const meta = data.geometry;
  const groups = new Map(data.groups.map((g) => [g.key, g]));
  const regions = new Map(data.regions.map((r, i) => [r, i]));
  const shown = new Set(data.groups.filter((g) => g.visible).map((g) => g.key));
  const rows = new Map();
  const visibilityGroups = [];
  let mode = stages.length ? 'mesh' : 'geometry';
  let axis = 0;
  let cutEnabled = false;
  const bounds = meta.bounds_mm;
  const offsets = bounds[0].map((lo, a) => (lo + bounds[1][a]) / 2);
  const viewport = new Viewport(el('scene'), data, select, (position) => {
    const clamped = Math.max(bounds[0][axis], Math.min(bounds[1][axis], position));
    offsets[axis] = clamped;
    el('position').value = Number(clamped.toPrecision(12));
    updatePlane();
  }, mode === 'mesh');
  el('tree').replaceChildren();
  function mountResults() {
    const query = stages.length ? { case: source, stage } : { case: source };
    field = fieldLayer(viewport, data, query, () => el('cut').click(),
      frame => results.follow(frame));
    results = resultsPanel(query, field, (title, entries) => {
      rows.forEach(r => r.classList.remove('selected'));
      viewport.highlight(null);
      props(title, entries);
    }, responseOpen, stages, inputs, plotPrefs);
  }
  mountResults();
  el('axis').value = axis;
  el('keep').value = 'lower';
  el('cut').setAttribute('aria-pressed', cutEnabled);
  el('cut-controls').hidden = !cutEnabled;
  for (const s of ['geometry', 'mesh']) el(s).setAttribute('aria-pressed', s === mode);
  viewport.setTool(el('pan').getAttribute('aria-pressed') === 'true' ? 'pan' : 'orbit');
  viewport.grid.visible = el('grid').checked;
  if (el('projection').value === 'persp') viewport.projection('persp');
  function props(title, entries) {
    el('selection').textContent = title;
    el('props').replaceChildren(
      ...entries.flatMap(([k, v]) => {
        const dt = document.createElement('dt'),
          dd = document.createElement('dd');
        dt.textContent = k;
        addHelp(dt, k);
        dd.textContent = v && typeof v === 'object' ? JSON.stringify(v) : String(v);
        return [dt, dd];
      }),
    );
  }

  function select(key) {
    results.deselect();
    rows.forEach((r, k) => r.classList.toggle('selected', k === key));
    viewport.highlight(regions.has(key) ? null : key);
    const active = rows.get(key);
    if (active) {
      active.parentElement.open = true;
      active.scrollIntoView({ block: 'nearest' });
    }
    if (key === null) {
      props(meta.model, [
        ['Mesh', stage ? stageName(stage) : meta.mesh_file],
        ['Cells', integer(stageInfo()?.cells ?? meta.mesh.cells)],
        [stage ? 'Preview vertices' : 'Nodes', integer(data.points.length)],
        ['Elements', meta.mesh.elements],
        ...Object.entries(meta.properties || {}),
      ]);
    } else if (regions.has(key)) {
      const r = key;
      const a = 'XYZ'.indexOf(r.axis);
      const first = r.boxes?.[0];
      const entries = [
        ['Rule', r.rule], ['Sizing axis', r.axis], ['Intervals per span', r.intervals],
      ];
      if (r.spacing_mm) {
        const [min, max] = r.spacing_mm;
        entries.push(['Smallest interval', num(min) + ' mm'],
          ['Largest interval', num(max) + ' mm']);
      }
      if (first) {
        entries.push(['Span', num(first[a + 3] - first[a]) + ' mm']);
        // Read actual node spacing within the declared boxes of the sizing region.
        let min = Infinity, max = -Infinity;
        for (const box of r.boxes) {
          const levels = new Set();
          for (const pt of input.points) {
            if (pt.every((v, i) => v >= box[i] - 1e-8 && v <= box[i + 3] + 1e-8)) {
              levels.add(Number(pt[a].toFixed(8)));
            }
          }
          const coords = [...levels].sort((x, y) => x - y);
          for (let i = 1; i < coords.length; i++) {
            const step = coords[i] - coords[i - 1];
            min = Math.min(min, step);
            max = Math.max(max, step);
          }
        }
        if (Number.isFinite(min)) entries.push(
          ['Smallest interval', num(min) + ' mm'], ['Largest interval', num(max) + ' mm'],
        );
      }
      props(r.name, entries);
    } else {
      const g = groups.get(key);
      const entries = [
        ['Physical tag', g.tag ?? '—'],
        ['Dimension', g.dimension === 3 ? 'Volume' : 'Surface'],
        [stage ? 'Palace elements' : 'Gmsh elements', integer(g.cells.length)],
      ];
      if (g.conditions) {
        if (!g.conditions.length) entries.push(['Boundary', 'No explicit assignment']);
        for (const condition of g.conditions) {
          entries.push(['Boundary', condition.type]);
          for (const [name, value] of Object.entries(condition.settings)) {
            entries.push([name, value]);
          }
        }
      }
      props(g.name, [...entries, ...Object.entries(g.properties || {})]);
    }
  }

  function setVisible(key, visible) {
    if (!regions.has(key) && viewport.selected === key) viewport.markSelection(visible);
    if (visible) shown.add(key);
    else shown.delete(key);
  }

  function sync() {
    rows.forEach((r, k) => {
      const on = shown.has(k);
      r.querySelector('input').checked = on;
      const object = regions.has(k) ? viewport.regions[regions.get(k)] : viewport.models.get(k);
      object.visible = on;
    });
    for (const { keys, checkbox } of visibilityGroups) {
      const count = keys.filter((key) => shown.has(key)).length;
      checkbox.checked = count > 0 && count === keys.length;
      checkbox.indeterminate = count > 0 && count < keys.length;
    }
    field.filters();
    viewport.draw();
  }

  function section(title, keys) {
    const d = document.createElement('details'),
      s = document.createElement('summary');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.disabled = keys.length === 0;
    checkbox.setAttribute('aria-label', 'Show all ' + title.toLowerCase());
    checkbox.title = 'Show or hide all ' + title.toLowerCase();
    checkbox.onchange = () => {
      for (const key of keys) setVisible(key, checkbox.checked);
      sync();
    };
    visibilityGroups.push({ keys, checkbox });
    d.open = true;
    s.append(checkbox, title);
    addHelp(s, title);
    d.append(s);
    el('tree').append(d);
    return d;
  }

  function row(parent, key, name, tint, hint) {
    const r = document.createElement('div'),
      check = document.createElement('input');
    const pick = document.createElement('button'),
      sw = document.createElement('i');
    const note = document.createElement('small');
    r.className = 'row';
    check.type = 'checkbox';
    check.setAttribute('aria-label', 'Show ' + name);
    sw.className = 'swatch';
    sw.style.backgroundColor = tint;
    note.textContent = hint;
    pick.append(sw, name, note);
    pick.title = 'Inspect ' + name;
    r.append(check, pick);
    parent.append(r);
    rows.set(key, r);
    pick.onclick = () => select(key);
    check.onchange = () => {
      setVisible(key, check.checked);
      sync();
    };
  }

  function buildTree() {
    rows.clear();
    visibilityGroups.length = 0;
    el('tree').replaceChildren();
    const categories = new Map();
    for (const g of data.groups) {
      const category = g.category;
      if (!categories.has(category)) categories.set(category, []);
      categories.get(category).push(g);
    }
    for (const [name, groups] of categories) {
      const parent = section(
        name,
        groups.map((g) => g.key),
      );
      for (const g of groups) {
        row(parent, g.key, g.name, g.color, String(g.tag ?? '—'));
      }
    }
    if (data.regions.length) {
      const refinement = section('Mesh sizing regions', data.regions);
      data.regions.forEach((r, i) =>
        row(refinement, r, r.name, regionColor(i), r.axis + ' ×' + r.intervals),
      );
    }
  }
  buildTree();

  function updatePlane() {
    const positionMm = offsets[axis],
      keepPositive = el('keep').value === 'upper';
    viewport.setCut(cutEnabled ? { axis, positionMm, keepPositive } : null);
    field.update();
    let label =
      mode === 'mesh' ? stage ? 'Palace · ' + stageName(stage) : 'Gmsh · ' + meta.mesh.elements
        : 'Model · mm';
    if (stage || meta.mesh.corner_preview) label += ' · corner-node preview';
    if (cutEnabled) {
      label += ' · ' + 'XYZ'[axis] + (keepPositive ? ' ≥ ' : ' ≤ ') + num(positionMm) + ' mm';
    }
    el('readout').textContent = label;
  }

  function configureAxis() {
    axis = Number(el('axis').value);
    const input = el('position');
    input.min = bounds[0][axis];
    input.max = bounds[1][axis];
    input.title = input.min + ' to ' + input.max + ' mm';
    input.value = offsets[axis];
    updatePlane();
  }

  for (const id of ['geometry', 'mesh'])
    el(id).onclick = () => {
      if (mode === id) return;
      mode = id;
      for (const s of ['geometry', 'mesh']) el(s).setAttribute('aria-pressed', s === mode);
      viewport.meshMode = mode === 'mesh';
      viewport.rebuild();
      updatePlane();
      sync();
    };
  el('cut').onclick = () => {
    cutEnabled = !cutEnabled;
    el('cut').setAttribute('aria-pressed', cutEnabled);
    el('cut-controls').hidden = !cutEnabled;
    updatePlane();
  };
  el('axis').onchange = configureAxis;
  el('keep').onchange = updatePlane;
  el('position').oninput = (event) => {
    const input = event.target;
    if (!input.validity.valid) return;
    offsets[axis] = input.valueAsNumber;
    updatePlane();
  };
  el('position').onblur = () => {
    el('position').value = offsets[axis];
  };
  for (const id of ['orbit', 'pan'])
    el(id).onclick = () => {
      viewport.setTool(id);
      for (const s of ['orbit', 'pan']) el(s).setAttribute('aria-pressed', s === id);
    };
  el('projection').onchange = (e) => viewport.projection(e.target.value);
  el('fit').onclick = () => viewport.fit();
  el('view').onchange = (e) => {
    if (e.target.value) viewport.snap(e.target.value);
    e.target.value = '';
  };
  el('grid').onchange = (e) => {
    viewport.grid.visible = e.target.checked;
    viewport.draw();
  };
  configureAxis();
  select(null);
  sync();
  const inputSummary = meta.mesh_file + ' · ' + integer(meta.mesh.cells) + ' cells · ' +
    integer(meta.mesh.nodes) + ' nodes' +
    (meta.mesh.gmsh_version ? ' · Gmsh ' + meta.mesh.gmsh_version : '');
  function stageStatus() {
    const index = stageSelect.selectedIndex;
    el('stage-prev').disabled = index <= 0;
    el('stage-next').disabled = index >= stageSelect.length - 1;
    const info = stageInfo();
    stageStats.title = info ? 'Cell count, degrees of freedom and global error indicator' : '';
    stageStats.textContent = info ? integer(info.cells) + ' cells · ' + integer(info.dofs) +
      ' DOFs' + (info.indicator == null ? '' : ' · η ' + info.indicator.toPrecision(3)) :
      integer(meta.mesh.cells) + ' input cells';
    el('summary').textContent = info ? 'Palace · ' + stageName(stage) + ' · ' +
      integer(info.cells) + ' cells' : inputSummary;
  }

  // Keep physical group identities stable across MPI partitions and solver-added attributes.
  const identities = new Map(input.groups.map(g => [g.dimension + ':' + g.tag, g]));
  function stageData(payload) {
    const stageGroups = payload.groups.map(g => {
      const id = g.dimension + ':' + g.tag;
      if (!identities.has(id)) {
        const volume = g.dimension === 3;
        identities.set(id, { key: identities.size + 1, name: 'Palace attribute ' + g.tag,
          category: volume ? 'Materials' : 'Palace boundaries', dimension: g.dimension,
          tag: g.tag, color: '#8198a8', translucent: !volume, properties: {} });
      }
      return { ...identities.get(id), ...g };
    });
    return { ...input, refined: true, points: payload.points, groups: stageGroups };
  }

  async function changeStage() {
    loading?.abort();
    const controller = new AbortController();
    loading = controller;
    const wanted = Number(stageSelect.value);
    stageStatus();
    if (wanted === stage) return;
    try {
      let next = wanted ? cache.get(wanted) : input;
      if (!next) {
        stageStats.textContent = 'Loading ' + stageName(wanted) + '…';
        const query = new URLSearchParams({ case: source, stage: wanted });
        const reply = await fetch('/api/stage-mesh?' + query, { signal: controller.signal });
        const payload = await reply.json();
        if (controller.signal.aborted) return;
        if (!reply.ok) throw Error(payload.error || reply.statusText);
        next = stageData(payload);
        if (cache.size >= 3) cache.delete(cache.keys().next().value);
        cache.set(wanted, next);
      }
      if (!el('results').hidden) responseOpen = !el('results-body').hidden;
      results.dispose();
      field.dispose();
      const selected = viewport.selected;
      data = next;
      stage = wanted;
      groups.clear();
      for (const group of data.groups) groups.set(group.key, group);
      viewport.setMesh(data);
      viewport.meshMode = true;
      mode = 'mesh';
      el('geometry').setAttribute('aria-pressed', false);
      el('mesh').setAttribute('aria-pressed', true);
      viewport.rebuild();
      buildTree();
      mountResults();
      select(groups.has(selected) ? selected : null);
      updatePlane();
      sync();
      stageStatus();
      const url = new URL(location.href);
      if (stage) url.searchParams.set('stage', stage);
      else url.searchParams.delete('stage');
      history.replaceState(null, '', url);
    } catch (error) {
      if (controller.signal.aborted) return;
      stageSelect.value = stage;
      stageStatus();
      stageStats.textContent = error.message;
    }
  }
  el('stage-controls').hidden = !stages.length;
  stageSelect.replaceChildren(new Option('Input · Gmsh', 0),
    ...stages.map(s => new Option(stageName(s.id), s.id)));
  stageSelect.onchange = changeStage;
  for (const [id, delta] of [['stage-prev', -1], ['stage-next', 1]]) {
    el(id).onclick = () => { stageSelect.selectedIndex += delta; changeStage(); };
  }
  stageStatus();
  if (stages.some(s => s.id === initialStage)) {
    stageSelect.value = initialStage;
    changeStage();
  }
  el('error').hidden = true;
  function clearOnEscape(event) {
    if (event.key === 'Escape' && !event.defaultPrevented && !event.isComposing &&
        !document.querySelector(':popover-open')) {
      select(null);
    }
  }
  document.addEventListener('keydown', clearOnEscape);
  return () => {
    loading?.abort();
    document.removeEventListener('keydown', clearOnEscape);
    results.dispose();
    field.dispose();
    viewport.dispose();
    const canvas = el('scene');
    canvas.replaceWith(canvas.cloneNode(false));
  };
}

function toggleSidebar(hidden) {
  el('sidebar').hidden = hidden;
  el('sidebar-toggle').setAttribute('aria-expanded', !hidden);
}
el('sidebar-toggle').onclick = () => toggleSidebar(!el('sidebar').hidden);
toggleSidebar(matchMedia('(max-width:600px)').matches);
decorate();
let dispose;
startInspection((data, source, stages, inputs) => {
  dispose?.();
  dispose = mountModel(data, source, stages, inputs);
}).catch((error) => {
  el('error').hidden = false;
  el('error').textContent = error.message;
});
