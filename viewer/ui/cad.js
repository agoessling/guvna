import * as T from 'three';
import { featureEdges } from './outlines.js';
import { facesByCorners, sectionCells } from './section.js';
import { OrbitControls } from '/lib/OrbitControls.js';
import { RoomEnvironment } from '/lib/RoomEnvironment.js';

const regionColors = ['#3174ca', '#736ac2', '#248d88', '#908135', '#4884a6', '#9b6875'];
export const regionColor = (index) => regionColors[index % regionColors.length];
const directions = {
  Iso: [1, -1.5, 1.15],
  Front: [0, -1, 0],
  Back: [0, 1, 0],
  Top: [0, 0, 1],
  Bottom: [0, 0, -1],
  Right: [1, 0, 0],
  Left: [-1, 0, 0],
};

function skin(group) {
  // Shared volume faces cancel, leaving the exterior skin.
  const boundary = new Map(),
    sheets = [];
  for (const cell of group.cells) {
    if (group.dimension === 2) {
      sheets.push(cell);
      continue;
    }
    for (const face of facesByCorners[cell.length]) {
      const ids = face.map((i) => cell[i]);
      const key = [...ids].sort((a, b) => a - b).join(':');
      if (!boundary.delete(key)) boundary.set(key, ids);
    }
  }
  return group.dimension === 2 ? sheets : [...boundary.values()];
}

function block(faces, positions, material, meshMode, refined) {
  const idx = [],
    edges = [],
    seen = new Set();
  for (const face of faces) {
    for (let i = 1; i < face.length - 1; i++) idx.push(face[0], face[i], face[i + 1]);
    if (meshMode) {
      for (let k = 0; k < face.length; k++) {
        const i = face[k],
          j = face[(k + 1) % face.length];
        const key = i < j ? i + ':' + j : j + ':' + i;
        if (!seen.has(key)) {
          seen.add(key);
          edges.push(i, j);
        }
      }
    }
  }
  const geom = new T.BufferGeometry();
  geom.setAttribute('position', positions);
  geom.setIndex(idx);
  const solid = new T.Mesh(geom, material);
  // Shader flat shading uses the face derivatives, preserving sharp CAD corners.
  const explicitEdges = meshMode || refined;
  const lines = explicitEdges ? new T.BufferGeometry() : new T.EdgesGeometry(geom, 12);
  if (explicitEdges) {
    lines.setAttribute('position', positions);
    lines.setIndex(meshMode ? edges : featureEdges(faces, positions, 12));
  }
  const pen = new T.LineBasicMaterial({
    color: meshMode ? 0x263643 : 0x3c413f,
    transparent: true,
    opacity: meshMode ? 0.8 : 0.7,
    depthWrite: false,
  });
  solid.add(new T.LineSegments(lines, pen));
  return solid;
}

// A sizing band follows the same piecewise-linear stations as the hexahedral mesh.
function sweptRegion({ sections, z: [bottom, top] }) {
  const positions = [], indices = [0, 2, 1, 0, 3, 2];
  for (const [x, lo, hi] of sections) {
    const base = positions.length / 3;
    positions.push(x, lo, bottom, x, hi, bottom, x, hi, top, x, lo, top);
    if (!base) continue;
    for (let i = 0; i < 4; i++) {
      const a = base - 4 + i, b = base - 4 + (i + 1) % 4;
      indices.push(a, b, b + 4, a, b + 4, a + 4);
    }
  }
  const last = positions.length / 3 - 4;
  indices.push(last, last + 1, last + 2, last, last + 2, last + 3);
  const geometry = new T.BufferGeometry();
  geometry.setAttribute('position', new T.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  return geometry;
}

function disposeMesh(root) {
  root.traverse((o) => {
    o.geometry?.dispose();
    o.material?.dispose();
  });
}

function viewCube() {
  const labels = ['RIGHT', 'LEFT', 'BACK', 'FRONT', 'TOP', 'BOTTOM'];
  // BoxGeometry's native face textures assume Y up. Orient the text in model coordinates.
  const turns = [-1, 1, 2, 0, 0, 0];
  const axisNames = ['+X', '−X', '+Y', '−Y', '+Z', '−Z'];
  const mats = labels.map((label, index) => {
    const c = document.createElement('canvas');
    c.width = c.height = 160;
    const g = c.getContext('2d');
    g.fillStyle = '#edf0f2';
    g.fillRect(0, 0, 160, 160);
    g.strokeStyle = '#788797';
    g.lineWidth = 4;
    g.strokeRect(0, 0, 160, 160);
    g.fillStyle = '#273c4c';
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.font = '600 31px system-ui';
    g.translate(80, 80);
    g.rotate((turns[index] * Math.PI) / 2);
    g.fillText(label, 0, -8);
    g.font = '25px system-ui';
    g.fillText(axisNames[index], 0, 26);
    const map = new T.CanvasTexture(c);
    map.colorSpace = T.SRGBColorSpace;
    return new T.MeshBasicMaterial({ map, toneMapped: false });
  });
  return new T.Mesh(new T.BoxGeometry(1, 1, 1), mats);
}

function makePlaneWidget() {
  const widget = new T.Group();
  const geometry = new T.PlaneGeometry(1, 1);
  const face = new T.Mesh(
    geometry,
    new T.MeshBasicMaterial({
      color: 0x278daf,
      opacity: 0.09,
      transparent: true,
      side: T.DoubleSide,
      depthWrite: false,
    }),
  );
  const frame = new T.LineSegments(
    new T.EdgesGeometry(geometry),
    new T.LineBasicMaterial({ color: 0x187399, depthTest: false }),
  );
  frame.renderOrder = 2;
  face.add(frame);
  const handle = new T.Group();
  const ink = new T.MeshBasicMaterial({ color: 0x187399, depthTest: false });
  for (const sign of [-1, 1]) {
    const arrow = new T.Mesh(new T.ConeGeometry(0.17, 0.42, 12), ink);
    arrow.position.z = sign * 0.64;
    arrow.rotation.x = (sign * Math.PI) / 2;
    arrow.renderOrder = 3;
    handle.add(arrow);
  }
  const shaft = new T.Mesh(new T.CylinderGeometry(0.045, 0.045, 0.9, 8), ink);
  shaft.rotation.x = Math.PI / 2;
  shaft.renderOrder = 3;
  handle.add(shaft);
  widget.add(face, handle);
  widget.visible = false;
  return widget;
}

export class Viewport {
  constructor(canvas, data, onPick, onMovePlane, meshMode = false) {
    this.scale = document.getElementById('scale');
    this.canvas = canvas;
    this.data = data;
    this.onPick = onPick;
    this.onMovePlane = onMovePlane;
    this.cut = null;
    this.cutDirty = false;
    this.clip = new T.Plane();
    this.caps = new Map();
    this.fieldSurfaces = new Set();
    this.pivot = null;
    this.pivotMark = document.getElementById('orbit-pivot');
    this.scene = new T.Scene();
    this.renderer = new T.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.autoClear = false;
    this.renderer.localClippingEnabled = true;
    const pmrem = new T.PMREMGenerator(this.renderer);
    const studio = new RoomEnvironment();
    this.env = pmrem.fromScene(studio, 0.035);
    this.scene.environment = this.env.texture;
    pmrem.dispose();
    studio.dispose();
    this.scene.add(new T.HemisphereLight(0xffffff, 0x78858b, 0.6));
    const lamp = new T.DirectionalLight(0xfff3e2, 1.2);
    lamp.position.set(-3, -5, 8);
    this.scene.add(lamp);
    const box = data.geometry.bounds_mm;
    this.bounds = new T.Box3(new T.Vector3(...box[0]), new T.Vector3(...box[1]));
    this.center = this.bounds.getCenter(new T.Vector3());
    this.span = this.bounds.getSize(new T.Vector3()).length();
    const fill = new T.PointLight(0xfff5e7, 1.6 * this.span ** 2);
    fill.position.set(0.65, 0.38, 0.7).multiplyScalar(this.span).add(this.center);
    this.scene.add(fill);

    this.grid = new T.GridHelper(this.span * 2, 40, 0x8f989e, 0xaab1b6);
    this.grid.rotation.x = Math.PI / 2;
    this.grid.position.copy(this.center);
    this.grid.position.z = box[0][2] - this.span * 0.006;
    this.grid.material.transparent = true;
    this.grid.material.opacity = 0.24;
    this.grid.material.depthWrite = false;
    this.scene.add(this.grid);
    this.models = new Map();
    this.setMesh(data);
    this.planeWidget = makePlaneWidget();
    this.scene.add(this.planeWidget);
    this.regions = data.regions.map((r, i) => this.region(r, i));
    this.gizmo = new T.Scene();
    this.cube = viewCube();
    this.gizmo.add(this.cube);
    this.cubeCamera = new T.OrthographicCamera(-0.99, 0.99, 0.99, -0.99, 0.1, 10);
    this.ray = new T.Raycaster();
    this.selected = null;
    this.selectionMark = new T.Mesh(new T.BufferGeometry(), new T.MeshBasicMaterial({
      color: 0x0073ff, transparent: true, opacity: 0.67, side: T.DoubleSide,
      depthTest: false, depthWrite: false,
    }));
    this.selectionMark.renderOrder = 5;
    this.selectionMark.visible = false;
    this.scene.add(this.selectionMark);
    this.pending = false;
    this.meshMode = meshMode;
    this.projection('ortho');
    this.snap('Iso');
    this.fit();
    this.rebuild();
    this.events();
    this.planeDragEvents();
    this.pivotEvents();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas.parentElement);
    this.resize();
  }

  dispose() {
    this.disposed = true;
    this.hidePivot();
    this.resizeObserver.disconnect();
    this.controls.dispose();
    this.selectionMark.removeFromParent();
    this.selectionMark.material.dispose();
    disposeMesh(this.scene);
    this.cube.geometry.dispose();
    for (const material of this.cube.material) {
      material.map.dispose();
      material.dispose();
    }
    this.env.dispose();
    this.renderer.dispose();
    this.renderer.forceContextLoss();
  }

  projection(type) {
    this.orbitDrag = null;
    const target = this.controls?.target.clone() || this.center.clone();
    const old = this.camera,
      distance = old?.position.distanceTo(target) || 2 * this.span;
    const height = !old
      ? this.span
      : old.isOrthographicCamera
        ? (old.top - old.bottom) / old.zoom
        : 2 * distance * Math.tan(T.MathUtils.degToRad(old.fov / 2));
    this.controls?.dispose();
    this.camera =
      type === 'ortho'
        ? new T.OrthographicCamera(-1, 1, 1, -1, 0.001, 1000)
        : new T.PerspectiveCamera(35, 1, 0.001, 1000);
    const cam = this.camera;
    cam.up.set(0, 0, 1);
    cam.near = this.span * 0.0002;
    cam.far = this.span * 150;
    const dir = old ? old.position.clone().sub(target).normalize() : new T.Vector3(1, -1, 1);
    const dist = cam.isPerspectiveCamera
      ? height / (2 * Math.tan(T.MathUtils.degToRad(cam.fov / 2)))
      : distance;
    cam.position.copy(target).addScaledVector(dir, dist);
    this.orthoHeight = height;
    this.controls = new OrbitControls(cam, this.canvas);
    this.controls.target.copy(target);
    this.controls.zoomToCursor = true;
    this.controls.screenSpacePanning = true;
    this.controls.minDistance = this.span * 0.005;
    this.controls.maxDistance = this.span * 50;
    this.controls.minZoom = 0.025;
    this.controls.maxZoom = 120;
    this.controls.mouseButtons.MIDDLE = T.MOUSE.PAN;
    this.controls.mouseButtons.RIGHT = T.MOUSE.PAN;
    this.setTool(this.tool || 'orbit');
    this.controls.addEventListener('change', () => {
      const local = this.orbitDrag?.local;
      if (local) {
        // Keep the grabbed world point at its original camera-space position during rotation.
        // Translate eye and target together to preserve the upright OrbitControls orientation.
        const delta = this.pivot.clone().sub(cam.localToWorld(local.clone()));
        cam.position.add(delta);
        this.controls.target.add(delta);
        cam.updateMatrixWorld();
      }
      this.draw();
    });
    this.controls.update();
    this.resize();
  }

  setTool(tool) {
    this.tool = tool;
    this.controls.mouseButtons.LEFT = tool === 'pan' ? T.MOUSE.PAN : T.MOUSE.ROTATE;
    this.canvas.style.cursor = tool === 'pan' ? 'grab' : 'default';
  }

  region(r, i) {
    const group = new T.Group(),
      tint = regionColor(i);
    const shapes = (r.sweeps || []).map(sweptRegion);
    for (const [x, y, z, X, Y, Z] of r.boxes || []) {
      shapes.push(new T.BoxGeometry(X - x, Y - y, Z - z)
        .translate((X + x) / 2, (Y + y) / 2, (Z + z) / 2));
    }
    for (const g of shapes) {
      const m = new T.MeshBasicMaterial({
        color: tint,
        transparent: true,
        opacity: 0.13,
        depthWrite: false,
      });
      const cube = new T.Mesh(g, m);
      cube.add(
        new T.LineSegments(new T.EdgesGeometry(g), new T.LineBasicMaterial({ color: tint })),
      );
      group.add(cube);
    }
    group.visible = false;
    this.scene.add(group);
    return group;
  }

  setMesh(data) {
    this.data = data;
    this.positions = new T.Float32BufferAttribute(data.points.flat(), 3);
    this.volumeBounds = new Map();
    for (const group of data.groups.filter((g) => g.dimension === 3)) {
      const bounds = Array.from({ length: 3 }, () => [Infinity, -Infinity]);
      for (const cell of group.cells)
        for (const id of cell) {
          data.points[id].forEach((p, axis) => {
            bounds[axis][0] = Math.min(p, bounds[axis][0]);
            bounds[axis][1] = Math.max(p, bounds[axis][1]);
          });
        }
      this.volumeBounds.set(group.key, bounds);
    }
  }

  rebuild() {
    this.clearCaps();
    for (const [tag, group] of this.models) {
      this.scene.remove(group);
      disposeMesh(group);
      this.models.delete(tag);
    }
    for (const g of this.data.groups) {
      const volume = g.dimension === 3;
      const translucent = g.translucent;
      const material = new T.MeshStandardMaterial({
        color: g.color,
        side: T.DoubleSide,
        flatShading: true,
        metalness: g.metallic ? 0.73 : 0.11,
        roughness: volume ? 0.64 : 0.39,
        transparent: translucent,
        opacity: translucent ? 0.12 : 1,
        depthWrite: !translucent,
        polygonOffset: true,
        polygonOffsetFactor: volume ? 4 : 2,
        polygonOffsetUnits: volume ? 4 : 2,
      });
      const faces = g.skin ?? skin(g);
      const obj = block(faces, this.positions, material, this.meshMode, this.data.refined);
      obj.userData.tag = g.key;
      obj.userData.sheet = !volume;
      if (translucent) obj.children[0].material.opacity = this.meshMode ? 0.24 : 0.42;
      this.models.set(obj.userData.tag, obj);
      this.scene.add(obj);
    }
    this.setCut(this.cut, true);
    this.markSelection(this.selectionMark.visible);
  }

  setCut(cut, newMaterials = false) {
    const toggle = Boolean(cut) !== Boolean(this.cut);
    this.cut = cut;
    this.cutDirty = true;
    if (cut) {
      this.clip.normal.set(0, 0, 0).setComponent(cut.axis, cut.keepPositive ? 1 : -1);
      this.clip.constant = -this.clip.normal.getComponent(cut.axis) * cut.positionMm;
      const axis = cut.axis,
        u = (axis + 1) % 3,
        v = (axis + 2) % 3;
      const basis = [u, v, axis].map((i) => new T.Vector3().setComponent(i, 1));
      const size = this.bounds.getSize(new T.Vector3());
      const widget = this.planeWidget;
      widget.position.copy(this.center).setComponent(axis, cut.positionMm);
      widget.quaternion.setFromRotationMatrix(new T.Matrix4().makeBasis(...basis));
      const width = size.getComponent(u) + this.span * 0.12;
      const height = size.getComponent(v) + this.span * 0.12;
      widget.children[0].scale.set(width, height, 1);
      const handle = widget.children[1];
      handle.position.set(width * 0.44, height * 0.44, 0);
      handle.scale.setScalar(this.span * 0.08);
    }
    this.planeWidget.visible = Boolean(cut);
    if (!cut) this.setTool(this.tool);
    if (toggle || newMaterials) {
      const planes = cut ? [this.clip] : [];
      const applyClip = (obj) => {
        if (obj.material) {
          obj.material.clippingPlanes = planes;
          obj.material.needsUpdate = true;
        }
      };
      applyClip(this.selectionMark);
      for (const model of this.models.values()) {
        applyClip(model);
        applyClip(model.children[0]);
      }
      for (const region of this.regions) region.traverse(applyClip);
    }
    this.draw();
  }

  clearCaps() {
    for (const cap of this.caps.values()) {
      cap.removeFromParent();
      disposeMesh(cap);
    }
    this.caps.clear();
  }

  updateSection() {
    this.cutDirty = false;
    this.clearCaps();
    if (!this.cut) return;
    const { axis, positionMm } = this.cut;
    const epsilon = this.span * 1e-9;
    for (const group of this.data.groups) {
      if (group.dimension !== 3) continue;
      const key = group.key;
      const [lo, hi] = this.volumeBounds.get(key)[axis];
      // A group's exterior already contains the face at either of these bounds.
      if (positionMm <= lo + epsilon || positionMm >= hi - epsilon) continue;
      const section = sectionCells(this.data.points, group.cells, this.cut, epsilon);
      if (!section.faces.length) continue;
      const parent = this.models.get(key);
      const material = parent.material.clone();
      material.clippingPlanes = null;
      const positions = new T.Float32BufferAttribute(section.vertices.flat(), 3);
      const cap = block(section.faces, positions, material, this.meshMode, this.data.refined);
      cap.userData.tag = key;
      cap.children[0].material.opacity = parent.children[0].material.opacity;
      parent.add(cap);
      this.caps.set(key, cap);
    }
  }

  pickPlaneHandle(event) {
    if (!this.cut || event.shiftKey || this.pick(event, 'cube')) return null;
    const rect = this.canvas.getBoundingClientRect();
    const pointer = new T.Vector2(
      (2 * (event.clientX - rect.left)) / rect.width - 1,
      1 - (2 * (event.clientY - rect.top)) / rect.height,
    );
    this.ray.setFromCamera(pointer, this.camera);
    return this.ray.intersectObject(this.planeWidget.children[1], true)[0];
  }

  planeDragEvents() {
    const canvas = this.canvas;
    let drag = null;
    const end = (event) => {
      if (drag?.pointer !== event.pointerId) return;
      event.stopImmediatePropagation();
      if (event.type === 'pointerup' && !drag.moved) {
        this.onPick(this.pick(event)?.object.userData.tag ?? null);
      }
      drag = null;
      if (canvas.hasPointerCapture(event.pointerId))
        canvas.releasePointerCapture(event.pointerId);
      this.setTool(this.tool);
    };
    canvas.addEventListener(
      'pointerdown',
      (event) => {
        if (event.button !== 0) return;
        const widgetHit = this.pickPlaneHandle(event);
        if (!widgetHit) return;
        const rect = canvas.getBoundingClientRect();
        const at = widgetHit.point.clone();
        const axis = this.cut.axis;
        const along = new T.Vector3().setComponent(axis, 1);
        // Screen-space derivative at the grab point, in CSS pixels per model millimetre.
        const delta = this.span * 0.001;
        const start = at.clone().project(this.camera);
        const end = at.clone().addScaledVector(along, delta).project(this.camera);
        const projected = new T.Vector2(
          ((end.x - start.x) * rect.width) / (2 * delta),
          ((start.y - end.y) * rect.height) / (2 * delta),
        );
        const viewDepth = -at.applyMatrix4(this.camera.matrixWorldInverse).z;
        const viewHeight = this.camera.isOrthographicCamera
          ? this.orthoHeight / this.camera.zoom
          : 2 * viewDepth * Math.tan(T.MathUtils.degToRad(this.camera.fov / 2));
        const pxPerMm = rect.height / viewHeight;
        // In an axial view the normal projects to a point. Drag up to increase the coordinate.
        if (projected.length() < pxPerMm * 0.2) projected.set(0, -pxPerMm);
        drag = {
          pointer: event.pointerId,
          x: event.clientX,
          y: event.clientY,
          position: this.cut.positionMm,
          motion: projected.divideScalar(projected.lengthSq()),
        };
        event.stopImmediatePropagation();
        canvas.focus();
        canvas.setPointerCapture(event.pointerId);
        canvas.style.cursor = 'grabbing';
      },
      true,
    );
    canvas.addEventListener(
      'pointermove',
      (event) => {
        if (!drag) {
          if (!event.buttons && this.cut) {
            canvas.style.cursor = this.pickPlaneHandle(event)
              ? 'grab'
              : this.tool === 'pan'
                ? 'grab'
                : '';
          }
          return;
        }
        if (drag.pointer !== event.pointerId) return;
        event.stopImmediatePropagation();
        const dx = event.clientX - drag.x,
          dy = event.clientY - drag.y;
        if (!drag.moved && Math.hypot(dx, dy) < 2) return;
        drag.moved = true;
        this.onMovePlane(drag.position + dx * drag.motion.x + dy * drag.motion.y);
      },
      true,
    );
    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
      canvas.addEventListener(type, end, true);
    }
  }

  highlight(tag) {
    this.selected = tag;
    this.markSelection(true);
  }

  markSelection(enabled) {
    const model = this.models.get(this.selected);
    this.selectionMark.visible = !!model && enabled;
    if (model) this.selectionMark.geometry = model.geometry;
    this.draw();
  }

  snap(name) {
    this.orbitDrag = null;
    const dir = new T.Vector3(...directions[name]).normalize();
    const t = this.controls.target,
      dist = this.camera.position.distanceTo(t);
    this.camera.position.copy(t).addScaledVector(dir, dist || this.span * 2);
    this.controls.update();
    this.draw();
  }

  fit() {
    this.orbitDrag = this.pivot = null;
    this.hidePivot();
    const cam = this.camera,
      target = this.controls.target;
    const dir = cam.position.clone().sub(target).normalize();
    target.copy(this.center);
    const aspect = Math.max(0.1, this.canvas.clientWidth / (this.canvas.clientHeight || 1));
    this.orthoHeight = (this.span * 1.04) / Math.min(1, aspect);
    const dist = this.orthoHeight / (2 * Math.tan(T.MathUtils.degToRad(17.5)));
    cam.zoom = 1;
    cam.position.copy(target).addScaledVector(dir, dist);
    this.resize();
    this.controls.update();
  }

  resize() {
    const w = this.canvas.clientWidth,
      h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    const c = this.camera;
    if (c.isOrthographicCamera) {
      c.top = this.orthoHeight / 2;
      c.bottom = -c.top;
      c.right = (c.top * w) / h;
      c.left = -c.right;
    } else c.aspect = w / h;
    c.updateProjectionMatrix();
    this.draw();
  }

  draw() {
    if (this.pending) return;
    this.pending = true;
    requestAnimationFrame(() => {
      this.pending = false;
      if (this.disposed) return;
      const r = this.renderer,
        w = this.canvas.clientWidth,
        h = this.canvas.clientHeight;
      if (!w || !h) return;
      if (this.cutDirty) this.updateSection();
      this.updateScale(h);
      r.setViewport(0, 0, w, h);
      r.setScissorTest(false);
      r.clear();
      r.render(this.scene, this.camera);
      if (this.pivot && !this.pivotMark.hidden) {
        const p = this.pivot.clone().project(this.camera);
        this.pivotMark.style.left = (p.x + 1) * 50 + '%';
        this.pivotMark.style.top = (1 - p.y) * 50 + '%';
        this.pivotMark.style.visibility = Math.abs(p.z) <= 1 ? 'visible' : 'hidden';
      }
      const size = this.cubeSize();
      this.cubeCamera.position
        .copy(this.camera.position)
        .sub(this.controls.target)
        .normalize()
        .multiplyScalar(3);
      this.cubeCamera.quaternion.copy(this.camera.quaternion);
      r.setViewport(w - size - 7, h - size - 7, size, size);
      r.setScissor(w - size - 7, h - size - 7, size, size);
      r.setScissorTest(true);
      r.clearDepth();
      r.render(this.gizmo, this.cubeCamera);
      r.setScissorTest(false);
    });
  }

  updateScale(height) {
    this.scale.hidden = !this.camera.isOrthographicCamera;
    if (this.scale.hidden) return;
    const mmPerPixel = this.orthoHeight / (height * this.camera.zoom);
    const target = 110 * mmPerPixel;
    const decade = 10 ** Math.floor(Math.log10(target));
    const step = [5, 2, 1].find((n) => n * decade <= target) * decade;
    this.scale.style.width = step / mmPerPixel + 'px';
    this.scale.textContent = Number(step.toPrecision(3)) + ' mm';
  }

  cubeSize() {
    return Math.min(94, this.canvas.clientWidth * 0.22);
  }

  pick(e, kind = 'model') {
    const cube = kind === 'cube', forOrbit = kind === 'pivot';
    const b = this.canvas.getBoundingClientRect(),
      size = this.cubeSize();
    const x = e.clientX - b.left,
      y = e.clientY - b.top;
    let uv, camera, objects;
    if (cube) {
      if (x < b.width - size - 7 || y > size + 7) return null;
      uv = new T.Vector2((2 * (x - b.width + size + 7)) / size - 1, 1 - (2 * (y - 7)) / size);
      camera = this.cubeCamera;
      objects = [this.cube];
    } else {
      uv = new T.Vector2((2 * x) / b.width - 1, 1 - (2 * y) / b.height);
      camera = this.camera;
      objects = [];
      for (const [tag, model] of this.models) {
        const highlighted = this.selectionMark.visible && tag === this.selected;
        if (!model.visible && !highlighted) continue;
        objects.push(model);
        if (this.caps.has(tag) && (model.visible || !forOrbit)) objects.push(this.caps.get(tag));
      }
      if (forOrbit) objects.push(...this.fieldSurfaces);
    }
    this.ray.setFromCamera(uv, camera);
    const hits = this.ray
      .intersectObjects(objects, false)
      .filter(
        (hit) => cube || !this.cut || this.clip.distanceToPoint(hit.point) >= -this.span * 1e-7,
      );
    // Look through translucent shells when an opaque model or plotted field lies behind them.
    if (forOrbit) return hits.find(hit => !hit.object.material.transparent) || hits[0];
    const first = hits[0];
    if (!first || cube) return first;
    // Prefer a surface group when its face coincides with a volume boundary.
    return (
      hits.find(
        (hit) => hit.distance <= first.distance + this.span * 1e-7 && hit.object.userData.sheet,
      ) || first
    );
  }

  hidePivot() {
    clearTimeout(this.pivotTimer);
    this.pivotMark.hidden = true;
  }

  showPivot() {
    this.pivotMark.hidden = false;
    clearTimeout(this.pivotTimer);
    this.pivotTimer = setTimeout(() => this.hidePivot(), 650);
    this.draw();
  }

  pivotEvents() {
    const canvas = this.canvas;
    canvas.addEventListener('wheel', event => {
      if (this.controls.state !== -1 || this.pick(event, 'cube')) return;
      const hit = this.pick(event, 'pivot');
      if (hit) {
        this.pivot = hit.point;
        this.showPivot();
      }
    }, { capture: true, passive: true });

    canvas.addEventListener('pointerdown', event => {
      this.orbitDrag = null;
      if (!event.isPrimary || this.pick(event, 'cube')) return;
      const modified = event.ctrlKey || event.metaKey || event.shiftKey;
      if (event.pointerType !== 'touch') {
        // OrbitControls swaps rotate and pan for a modified mouse drag.
        const rotates = event.button === 0 && this.tool === 'orbit';
        if (event.button > 2 || (modified ? rotates : !rotates)) return;
      }
      this.orbitDrag = { id: event.pointerId, clientX: event.clientX, clientY: event.clientY };
    }, true);
    canvas.addEventListener('pointermove', event => {
      const drag = this.orbitDrag;
      if (!drag || drag.id !== event.pointerId || drag.local) return;
      if (event.clientX === drag.clientX && event.clientY === drag.clientY) return;
      const hit = this.pick(drag, 'pivot');
      this.pivot = hit?.point ?? this.pivot ?? this.controls.target.clone();
      drag.local = this.camera.worldToLocal(this.pivot.clone());
      this.showPivot();
    }, true);
    const end = event => {
      if (this.orbitDrag?.id === event.pointerId) this.orbitDrag = null;
    };
    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
      canvas.addEventListener(type, end, true);
    }
  }

  events() {
    let down;
    this.canvas.addEventListener('pointerdown', (e) => {
      if (e.button === 0) down = [e.clientX, e.clientY];
      else down = null;
    });
    this.canvas.addEventListener('pointerup', (e) => {
      if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
      down = null;
      const cube = this.pick(e, 'cube');
      if (cube) {
        this.snap(['Right', 'Left', 'Back', 'Front', 'Top', 'Bottom'][cube.face.materialIndex]);
        return;
      }
      const hit = this.pick(e);
      this.onPick(hit?.object.userData.tag ?? null);
    });
    this.canvas.addEventListener('dblclick', (e) => {
      if (this.pick(e, 'cube')) return;
      const hit = this.pick(e, 'pivot');
      if (!hit) return;
      this.pivot = hit.point;
      this.showPivot();
      const delta = hit.point.clone().sub(this.controls.target);
      this.camera.position.add(delta);
      this.controls.target.copy(hit.point);
      this.controls.update();
      this.draw();
    });
    this.canvas.addEventListener('keydown', (e) => {
      if (e.key.toLowerCase() === 'f') {
        e.preventDefault();
        this.fit();
      }
    });
  }
}
