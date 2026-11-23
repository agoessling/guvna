// Compact tool glyphs in a shared 20-unit grid, with text alternatives on every button.
const paths = {
  'sidebar-toggle': 'M2 3h16v14H2z M7 3v14',
  geometry: 'm10 2 7 4v8l-7 4-7-4V6z M3 6l7 4 7-4 M10 10v8',
  mesh: 'M2 3h16v14H2z M2 3l16 14 M18 3 2 17 M2 10h16 M10 3v14',
  orbit: 'M17 8c-2-6-13-1-14 3s7 5 12 1 M17 4v4h-4 M9 10h2',
  pan: 'M10 2v16 M2 10h16 M7 5l3-3 3 3 M7 15l3 3 3-3 M5 7l-3 3 3 3 M15 7l3 3-3 3',
  fit: 'M3 8V3h5 M12 3h5v5 M17 12v5h-5 M8 17H3v-5',
  cut: 'm2 12 6-7 10 3-6 7z M10 2v4 M10 14v4',
};

const help = {
  'Field samples': 'Diamonds along the frequency axis mark saved fields for this drive. Click' +
    ' the plot or use its arrow keys to select a solved sample and inspect the available field.',
  'RF phase': 'Signed components show Re(E × exp(iφ)) at the selected RF phase. Blue and red' +
    ' mark opposite directions. Play advances one cycle in four seconds of viewing time.',
  'Field reference': 'The reference stays fixed across frequencies and drives. Fit uses the' +
    ' largest displayed magnitude for this quantity.',
  'Material side': 'Sample the electric field from inside the selected material, including at' +
    ' interfaces. All material faces includes the face exposed by the cut plane.' +
    ' You can also restrict the plot to a tagged boundary.',
  'Surface current': 'Sheet current density in A/m. On metal it represents conductor current.' +
    ' On a lumped port it represents the equivalent current of the source or load.' +
    ' Visible boundaries follows the eye controls in the model tree.',
  'Model browser': 'Select a row to locate its mesh group. The eyes control visibility.',
  Properties: 'Click a face in the model or a group in the tree to inspect its properties.',
  'Cut plane': 'Drag the blue arrow handle to move the cut. The position is in model coordinates.',
  'Keep side': 'Choose which side of the plane remains visible when the model is clipped.',
  'Physical tag': 'Gmsh identifies a group by dimension and tag. Palace uses these tags to assign' +
    ' materials to volumes and conditions to surfaces.',
  Boundary: 'The boundary assignment in the Palace input used for this model.',
  Attributes: 'All physical tags covered by this assignment or port element.',
  Excitation: 'Palace excitation index for this port. Zero or false means it is undriven.',
  Direction: 'Orientation of the port element in the Palace input coordinate system.',
  'Mesh sizing regions': 'These regions control the initial Gmsh element spacing.',
  'Intervals per span': 'Number of initial mesh intervals across each specified span.',
  'Construction grid': 'Reference grid for orientation. Its lines are independent of mesh cells.',
};

export function addHelp(element, name) {
  if (!help[name]) return;
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'info';
  button.textContent = 'i';
  button.setAttribute('aria-label', 'About ' + name);
  const tip = document.createElement('div');
  tip.popover = 'auto';
  tip.className = 'explanation';
  tip.textContent = help[name];
  button.popoverTargetElement = tip;
  button.onclick = (event) => event.stopPropagation();
  tip.addEventListener('beforetoggle', (event) => {
    if (event.newState !== 'open') return;
    const rect = button.getBoundingClientRect();
    tip.style.left = Math.min(rect.left, innerWidth - 258) + 'px';
    tip.style.top = Math.min(rect.bottom + 4, innerHeight - 95) + 'px';
  });
  element.append(button, tip);
}

export function decorate() {
  for (const [id, d] of Object.entries(paths)) {
    const button = document.getElementById(id);
    const label = button.getAttribute('aria-label') || button.textContent.trim();
    button.title ||= label;
    button.setAttribute('aria-label', label);
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 20 20');
    svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS(svg.namespaceURI, 'path');
    path.setAttribute('d', d);
    svg.append(path);
    if (['orbit', 'pan', 'fit', 'sidebar-toggle'].includes(id)) button.replaceChildren();
    button.prepend(svg);
  }
  for (const node of document.querySelectorAll('[data-help]')) addHelp(node, node.dataset.help);
}

export async function startInspection(mount) {
  const source = document.getElementById('source');
  const status = document.getElementById('error');
  const response = await fetch('/api/cases');
  if (!response.ok) throw Error('Could not load the inspection inputs.');
  const inputs = await response.json();
  const prompt = new Option(inputs.length ? 'Choose an input…' : 'No inspection inputs', '');
  prompt.disabled = true;
  source.replaceChildren(prompt);
  source.disabled = !inputs.length;
  if (!inputs.length) throw Error('No inspection inputs were supplied.');

  const byId = new Map(inputs.map((item) => [item.id, item]));
  for (const item of inputs) {
    const label = inputs.some((other) => other !== item && other.name === item.name)
      ? item.name + ' · ' + item.id : item.name;
    const option = new Option(label, item.id);
    if (item.path) option.title = item.path;
    source.append(option);
  }
  let active = '', pending;
  async function load(id) {
    pending?.abort();
    const controller = new AbortController();
    pending = controller;
    const item = byId.get(id);
    if (active === id) {
      status.hidden = true;
      return;
    }
    source.value = id;
    status.hidden = false;
    status.textContent = 'Loading ' + item.name + '…';
    try {
      const response = await fetch('/api/model?case=' + encodeURIComponent(id), {
        signal: controller.signal,
      });
      const data = await response.json();
      if (controller.signal.aborted) return;
      if (!response.ok) throw Error(data.error || response.statusText);
      if (!data.geometry?.mesh || !Array.isArray(data.groups) || !Array.isArray(data.points)) {
        throw Error('Invalid mesh response.');
      }
      mount(data, id);
      active = id;
      prompt.remove();
      const url = new URL(location.href);
      url.searchParams.set('inspect', id);
      history.replaceState(null, '', url);
      status.hidden = true;
    } catch (err) {
      if (controller.signal.aborted) return;
      source.value = active;
      status.hidden = false;
      status.textContent = 'Could not open ' + item.name + '. ' + err.message;
    }
  }
  source.onchange = () => load(source.value);
  const requested = new URLSearchParams(location.search).get('inspect');
  if (requested !== null && !byId.has(requested)) {
    source.value = '';
    throw Error('Unknown inspection input. Choose an input from the toolbar.');
  }
  await load(requested ?? inputs[0].id);
}
