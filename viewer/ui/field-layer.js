import * as T from 'three';

const el = id => document.getElementById(id);
const electricPalette = ['#377ac1', '#479bd0', '#65bed1', '#a6d9c1', '#f3e89e', '#ffc565',
  '#f38a48', '#ce492f'];
const currentPalette = ['#836daf', '#737fb8', '#628fb5', '#519fa8', '#58b599', '#82c782',
  '#bbda70', '#f6e965'];

function colorScale(view, prefix, unit, palette) {
  const legend = el(prefix + '-legend'), input = el(prefix + '-reference');
  const mode = el(prefix + '-map'), fit = el(prefix + '-fit');
  const reference = { value: 1 }, windowDb = { value: 40 };
  const phase = { value: new T.Vector2(1, 0) }, signed = { value: false };
  const savedReferences = new Map();
  let component = 'magnitude', magnitudeMap = '40';
  let peak = 0, locked = 0;
  input.value = '';
  mode.value = '40';
  mode.disabled = false;
  legend.hidden = true;
  legend.open = false;
  const ramp = el(prefix + '-ramp');
  const magnitudeRamp = 'linear-gradient(to right,' + palette.join(',') + ')';
  function render() {
    reference.value = locked || 1;
    windowDb.value = Number(mode.value);
    ramp.style.background = signed.value
      ? 'linear-gradient(to right,#2166ac,#f7f7f7,#b2182b)' : magnitudeRamp;
    const ref = locked.toLocaleString(undefined, { maximumSignificantDigits: 4 }) + ' ' + unit;
    let range = '0 – ' + ref;
    if (signed.value) range = '±' + ref;
    else if (windowDb.value) range = '−' + windowDb.value + ' … 0 dB re ' + ref;
    el(prefix + '-range').textContent = locked ? range : '—';
    input.value = locked || '';
    view.draw();
  }
  fit.onclick = () => { if (peak > 0) locked = peak; render(); };
  mode.onchange = render;
  input.onchange = () => {
    if (input.valueAsNumber > 0 && Number.isFinite(input.valueAsNumber)) {
      locked = input.valueAsNumber;
    }
    render();
  };
  render();
  return {
    reference, windowDb, phase, signed,
    get component() { return component; },
    setComponent(next) {
      savedReferences.set(component, locked);
      if (!signed.value) magnitudeMap = mode.value;
      component = next;
      signed.value = next !== 'magnitude';
      mode.disabled = signed.value;
      mode.value = signed.value ? '0' : magnitudeMap;
      locked = savedReferences.get(next) || 0;
      render();
    },
    colors: palette.map(hex => new T.Vector3(
      ...hex.slice(1).match(/../g).map(x => parseInt(x, 16) / 255),
    )),
    update(visible, maximum) {
      legend.hidden = !visible;
      peak = maximum;
      fit.disabled = !peak;
      if (!locked && peak) { locked = peak; render(); }
    },
  };
}

function fieldPlot(view, status, scale, order, updateLegends) {
  // The field cut sits on its plane. Surface plots are clipped with the model in world space.
  const plane = new T.Vector4(0, 0, 0, 1);
  const material = new T.ShaderMaterial({
    side: T.DoubleSide, polygonOffset: true,
    // The field sits between the solid faces and their unbiased outline or mesh lines.
    // Coincident field layers share a depth bias and composite in renderOrder.
    polygonOffsetFactor: 1, polygonOffsetUnits: 1,
    uniforms: {
      reference: scale.reference, windowDb: scale.windowDb,
      phase: scale.phase, useSigned: scale.signed,
      palette: { value: scale.colors }, plane: { value: plane },
    },
    vertexShader: `
      attribute vec2 phasor;
      uniform vec2 phase;
      varying float amp, distanceToPlane;
      uniform vec4 plane;
      void main() {
        amp = dot(phasor, phase);
        distanceToPlane = dot(plane, vec4(position, 1.0));
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      varying float amp, distanceToPlane;
      uniform float reference, windowDb;
      uniform vec3 palette[8];
      uniform bool useSigned;
      void main() {
        if (distanceToPlane < 0.0) discard;
        if (useSigned) {
          float u = clamp(amp / reference, -1.0, 1.0);
          vec3 end = u < 0.0 ? vec3(33,102,172)/255.0 : vec3(178,24,43)/255.0;
          gl_FragColor = vec4(mix(vec3(247.0/255.0), end, abs(u)), 1.0);
          return;
        }
        float ratio = max(amp / reference, 1e-20);
        float t = windowDb == 0.0 ? ratio : 1.0 + 8.68588964 * log(ratio) / windowDb;
        float i = clamp(t, 0.0, 1.0) * 7.0;
        int k = min(6, int(i));
        gl_FragColor = vec4(mix(palette[k], palette[k+1], i-float(k)), 1.0);
      }`,
  });
  let pending, timer, last = '', mesh, sample, peak = 0;
  let plottedComponent, amplitudes;
  let visible = () => true;
  function clear() {
    clearTimeout(timer);
    pending?.abort();
    if (mesh) {
      view.fieldSurfaces.delete(mesh);
      mesh.removeFromParent();
      mesh.geometry.dispose();
      view.draw();
    }
    mesh = sample = amplitudes = null;
    peak = 0;
    status.textContent = '';
  }
  function filter() {
    if (!mesh) return;
    const indices = [];
    peak = 0;
    sample.faces.forEach((face, i) => {
      if (!visible(sample.materials[i])) return;
      indices.push(...face);
      for (const vertex of face) peak = Math.max(peak, amplitudes[vertex]);
    });
    mesh.geometry.setIndex(indices);
    status.textContent = indices.length ? '' : 'No matching faces in this selection';
    updateLegends();
    view.draw();
  }
  return {
    get peak() { return scale.component === plottedComponent ? peak : 0; },
    filter(fn) { visible = fn; filter(); },
    clip(cut) {
      plane.set(0, 0, 0, 1);
      if (cut) {
        const sign = cut.keepPositive ? 1 : -1;
        plane.setComponent(cut.axis, sign);
        plane.w = -sign * cut.positionMm;
      }
    },
    load(url, debounce = 0) {
      if (last === url) return;
      last = url;
      clear();
      updateLegends();
      if (!url) return;
      const controller = new AbortController();
      pending = controller;
      status.textContent = 'Loading field…';
      timer = setTimeout(async () => {
        try {
          const reply = await fetch(url, { signal: controller.signal });
          const result = await reply.json();
          if (controller.signal.aborted) return;
          if (!reply.ok) throw Error(result.error || reply.statusText);
          sample = result;
          const geo = new T.BufferGeometry();
          geo.setAttribute('position', new T.Float32BufferAttribute(result.points.flat(), 3));
          plottedComponent = scale.component;
          const signed = plottedComponent !== 'magnitude';
          const phasors = signed ? result.values.flat() : result.values;
          geo.setAttribute('phasor', new T.Float32BufferAttribute(phasors, signed ? 2 : 1));
          amplitudes = signed ? result.values.map(([re, im]) => Math.hypot(re, im)) : result.values;
          mesh = new T.Mesh(geo, material);
          mesh.renderOrder = order;
          view.scene.add(mesh);
          view.fieldSurfaces.add(mesh);
          filter();
        } catch (error) {
          if (controller.signal.aborted) return;
          status.textContent = error.message;
          last = '';
        }
      }, debounce);
    },
    dispose() { clear(); material.dispose(); },
  };
}

function phaseDial(view, electric) {
  const dial = el('field-phase'), play = el('phase-play');
  const knob = el('phase-knob');
  let animation = 0, playing = false;
  function setPhase(degrees) {
    dial.value = String(degrees);
    const phi = degrees * Math.PI / 180;
    electric.phase.value.set(Math.cos(phi), -Math.sin(phi));
    knob.setAttribute('aria-valuenow', degrees);
    knob.setAttribute('aria-valuetext', degrees + ' degrees');
    knob.style.setProperty('--angle', degrees + 'deg');
    view.draw();
  }
  function pause() {
    cancelAnimationFrame(animation);
    playing = false;
    play.textContent = 'Play';
    play.setAttribute('aria-label', 'Play RF phase');
  }
  play.onclick = () => {
    if (playing) { pause(); return; }
    playing = true;
    play.textContent = 'Pause';
    play.setAttribute('aria-label', 'Pause RF phase');
    const start = performance.now(), initial = Number(dial.value);
    function tick(now) {
      setPhase(Math.floor(initial + (now - start) * 0.09) % 360);
      animation = requestAnimationFrame(tick);
    }
    animation = requestAnimationFrame(tick);
  };
  function turnKnob(event) {
    const box = knob.getBoundingClientRect();
    const x = event.clientX - box.left - box.width / 2;
    const y = event.clientY - box.top - box.height / 2;
    if (Math.hypot(x, y) > 2) setPhase((360 + Math.round(Math.atan2(x, -y) * 180 / Math.PI)) % 360);
  }
  knob.onpointerdown = event => {
    if (event.button !== 0) return;
    pause();
    knob.setPointerCapture(event.pointerId);
    turnKnob(event);
  };
  knob.onpointermove = event => {
    if (knob.hasPointerCapture(event.pointerId)) turnKnob(event);
  };
  knob.onkeydown = event => {
    const steps = { ArrowUp: 1, ArrowRight: 1, ArrowDown: -1, ArrowLeft: -1,
      PageUp: 15, PageDown: -15 };
    let next;
    if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = 360;
    else if (Object.hasOwn(steps, event.key)) {
      next = (Number(dial.value) + steps[event.key] + 360) % 360;
    }
    else return;
    event.preventDefault();
    pause();
    setPhase(next);
  };
  dial.oninput = () => {
    pause();
    if (dial.value !== '' && dial.validity.valid) setPhase(dial.valueAsNumber);
  };
  dial.onchange = () => setPhase(Math.max(0, Math.min(360, Math.round(Number(dial.value) || 0))));
  pause();
  setPhase(0);
  return { pause, setPhase };
}

export function fieldLayer(view, data, source, enableCut, onFrame) {
  const cutButton = el('fields'), surfaces = el('surfaces'), options = el('surface-options');
  const drive = el('field-drive'), frequency = el('field-frequency');
  const cutDomain = el('field-domain'), skinDomain = el('skin-domain');
  const sheetOn = el('sheet-on'), skinOn = el('skin-on');
  const skinTarget = el('skin-target'), sheetTarget = el('sheet-target');
  const lifetime = new AbortController();
  const missing = el('field-missing');
  missing.hidden = true;
  let frames = [], cutOn = false, surfaceOn = false;
  const electric = colorScale(view, 'field', 'V/m', electricPalette);
  const current = colorScale(view, 'current', 'A/m', currentPalette);
  const cut = fieldPlot(view, el('field-status'), electric, 2, legends);
  const skin = fieldPlot(view, el('skin-status'), electric, 3, legends);
  const sheet = fieldPlot(view, el('sheet-status'), current, 4, legends);
  const volumes = data.groups.filter(g => g.dimension === 3 && g.tag != null);
  const boundaries = data.groups.filter(g => g.dimension === 2 && g.tag != null);
  const choices = groups => groups.map(g => new Option(g.name, g.tag));
  cutDomain.replaceChildren(new Option('All volumes', ''), ...choices(volumes));
  skinDomain.replaceChildren(...choices(volumes));
  skinTarget.replaceChildren(new Option('All material faces', ''), ...choices(boundaries));
  sheetTarget.replaceChildren(new Option('Visible boundaries', 'visible'),
    new Option('All boundaries', ''), ...choices(boundaries));
  for (const button of [cutButton, surfaces]) {
    button.disabled = true;
    button.setAttribute('aria-pressed', 'false');
  }
  const component = el('field-component');
  component.value = 'magnitude';
  const phaseControl = phaseDial(view, electric);
  options.open = true;
  skinOn.checked = false;
  sheetOn.checked = true;
  // A tagged boundary has no interior. Only a material skin gains a face when clipped.
  const capOn = () => Boolean(view.cut && surfaceOn && skinOn.checked && skinTarget.value === '');
  const cutFaceVisible = tag => (capOn() && String(tag) === skinDomain.value) ||
    (cutOn && (cutDomain.value === '' || String(tag) === cutDomain.value));
  cut.filter(cutFaceVisible);
  function legends() {
    const showSkin = surfaceOn && skinOn.checked;
    const showSheet = surfaceOn && sheetOn.checked && !sheetOn.disabled;
    const peak = Math.max(cutOn || capOn() ? cut.peak : 0, showSkin ? skin.peak : 0);
    electric.update(cutOn || showSkin, peak);
    current.update(showSheet, showSheet ? sheet.peak : 0);
    const symbol = component.value === 'magnitude' ? '|E|' : 'E' + component.value;
    el('field-symbol').textContent = symbol;
    el('field-fit').textContent = showSkin ? 'Fit to plotted ' + symbol : 'Fit to cut';
    el('phase-controls').hidden = !electric.signed.value;
    if ((!showSkin && !cutOn) || !electric.signed.value) phaseControl.pause();
    el('cut-material').hidden = !cutOn;
  }
  function filters() {
    const match = select => tag => select.value === '' || String(tag) === select.value;
    skin.filter(match(skinTarget));
    if (sheetTarget.value === 'visible') {
      const tags = new Set(boundaries.filter(g => view.models.get(g.key)?.visible).map(g => g.tag));
      sheet.filter(tag => tags.has(tag));
    } else sheet.filter(match(sheetTarget));
  }
  function update() {
    const frame = frequency.value === '' ? null : frames[Number(frequency.value)];
    if (cutOn && !view.cut) cutOn = false;
    cutButton.setAttribute('aria-pressed', String(cutOn));
    surfaces.setAttribute('aria-pressed', String(surfaceOn));
    options.hidden = !surfaceOn;
    el('field-sample').hidden = !cutOn && !surfaceOn;
    sheetOn.disabled = !frame?.current;
    sheetTarget.disabled = sheetOn.disabled || !sheetOn.checked;
    skinTarget.disabled = skinDomain.disabled = !skinOn.checked;
    skin.clip(view.cut);
    sheet.clip(view.cut);
    const params = { case: source, frame: frequency.value };
    const eParams = { component: electric.component };
    const url = (path, args) => '/api/field-' + path + '?' +
      new URLSearchParams({ ...params, ...args });
    cut.load((cutOn || capOn()) && frame ? url('cut', { ...eParams, axis: view.cut.axis,
      mm: view.cut.positionMm, keep: view.cut.keepPositive ? 'upper' : 'lower'}) : '', 90);
    skin.load(surfaceOn && skinOn.checked && frame ? url('surface',
      { ...eParams, quantity: 'E', domain: skinDomain.value }) : '');
    sheet.load(surfaceOn && sheetOn.checked && frame?.current ?
      url('surface', { quantity: 'J_s' }) : '');
    legends();
    view.draw();
  }
  function frequencies(selected) {
    const previous = frequency.selectedOptions[0]?.text;
    const available = frames.filter(f => String(f.excitation ?? '') === drive.value);
    frequency.replaceChildren(...available.map(f => new Option(f.ghz + ' GHz', f.id)));
    const same = [...frequency.options].find(o => o.text === previous);
    if (same) frequency.value = same.value;
    if (selected) frequency.value = selected.id;
  }
  function useToolbarFrame() {
    missing.hidden = true;
    const frame = frequency.value === '' ? null : frames[Number(frequency.value)];
    if (frame) onFrame(frame);
    update();
  }
  function updateLayers() {
    update();
    cut.filter(cutFaceVisible);
  }
  component.onchange = () => {
    electric.setComponent(component.value);
    if (!electric.signed.value) {
      phaseControl.pause();
      phaseControl.setPhase(0);
    }
    update();
  };
  sheetTarget.onchange = filters;
  skinTarget.onchange = () => { updateLayers(); filters(); };
  cutDomain.onchange = () => cut.filter(cutFaceVisible);
  for (const control of [skinOn, sheetOn, skinDomain]) control.onchange = updateLayers;
  frequency.onchange = useToolbarFrame;
  drive.onchange = () => { frequencies(); useToolbarFrame(); };
  cutButton.onclick = () => {
    cutOn = !cutOn;
    if (cutOn && !view.cut) enableCut();
    updateLayers();
  };
  surfaces.onclick = () => {
    surfaceOn = !surfaceOn;
    if (surfaceOn && sheetOn.disabled && !skinOn.checked) skinOn.checked = true;
    updateLayers();
  };
  filters();
  update();
  const ready = (async () => {
    try {
      const reply = await fetch('/api/fields?case=' + encodeURIComponent(source),
        { signal: lifetime.signal });
      const result = await reply.json();
      if (lifetime.signal.aborted) return;
      if (!reply.ok) throw Error(result.error || reply.statusText);
      frames = result;
      cutButton.disabled = surfaces.disabled = !frames.length;
      const drives = [...new Set(frames.map(f => f.excitation))];
      drive.replaceChildren(...drives.map(d => new Option(d ?? 'Default', d ?? '')));
      frequencies();
      update();
    } catch (error) {
      if (!lifetime.signal.aborted) cutButton.title = surfaces.title = error.message;
    }
  })();
  return {
    update, filters, ready,
    get frames() { return frames; },
    selectSample(frame, driveNumber, ghz) {
      if (frame) {
        missing.hidden = true;
        drive.value = frame.excitation ?? '';
        frequencies(frame);
        if (!surfaceOn && !cutOn) cutButton.click();
      } else {
        drive.value = driveNumber;
        frequencies();
        frequency.selectedIndex = -1;
        missing.textContent = 'No saved field · Drive ' + driveNumber + ' · ' + ghz + ' GHz';
        missing.hidden = false;
      }
      update();
    },
    dispose() {
      phaseControl.pause();
      lifetime.abort();
      for (const plot of [cut, skin, sheet]) plot.dispose();
    },
  };
}
