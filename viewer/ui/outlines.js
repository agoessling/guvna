// Split polygon edges at hanging vertices before classifying borders and creases.
import { Vector3 } from 'three';

export function featureEdges(faces, positions, angleDegrees) {
  const edges = [], incident = new Map(), vertices = new Map();
  const points = [];
  function vertex(id) {
    if (points[id]) return points[id];
    const p = new Vector3().fromBufferAttribute(positions, id);
    const key = p.toArray().join(',');
    if (!vertices.has(key)) vertices.set(key, { p, id });
    points[id] = vertices.get(key);
    return points[id];
  }
  function root(edge) {
    while (edge.parent !== edge) {
      edge.parent = edge.parent.parent;
      edge = edge.parent;
    }
    return edge;
  }
  const cross = new Vector3(), tangent = new Vector3();
  for (const face of faces) {
    const corners = face.map(vertex);
    const normal = new Vector3();
    for (let i = 1; i + 1 < corners.length; i++) {
      tangent.subVectors(corners[i].p, corners[0].p);
      normal.add(cross.subVectors(corners[i + 1].p, corners[0].p).cross(tangent));
    }
    if (normal.lengthSq() === 0) continue;
    normal.normalize();
    for (let i = 0; i < corners.length; i++) {
      const a = corners[i], b = corners[(i + 1) % corners.length];
      if (a.id === b.id) continue;
      const dir = b.p.clone().sub(a.p).normalize();
      const edge = { a, b, dir, normal };
      edge.parent = edge;
      edges.push(edge);
      for (const { id } of [a, b]) {
        if (!incident.has(id)) incident.set(id, []);
        const lines = incident.get(id);
        const match = lines.find(other => cross.crossVectors(dir, other.dir).lengthSq() < 1e-12);
        if (match) root(edge).parent = root(match);
        else lines.push(edge);
      }
    }
  }

  const lines = new Map(), indices = [];
  for (const edge of edges) {
    const line = root(edge);
    if (!lines.has(line)) lines.set(line, []);
    lines.get(line).push(edge);
  }
  const threshold = -Math.cos(angleDegrees * Math.PI / 180);
  for (const [line, segments] of lines) {
    const events = new Map();
    for (const edge of segments) {
      edge.forward = edge.dir.dot(line.dir) > 0;
      for (const vertex of [edge.a, edge.b]) {
        if (!events.has(vertex)) events.set(vertex, []);
        events.get(vertex).push(edge);
      }
    }
    const sorted = [...events.keys()].sort((a, b) => a.p.dot(line.dir) - b.p.dot(line.dir));
    const active = new Set();
    for (let i = 0; i + 1 < sorted.length; i++) {
      for (const edge of events.get(sorted[i])) {
        if (!active.delete(edge)) active.add(edge);
      }
      if (!active.size) continue;
      if (active.size === 2) {
        const [a, b] = active;
        const dot = a.normal.dot(b.normal) * (a.forward === b.forward ? 1 : -1);
        if (dot <= threshold) continue;
      }
      indices.push(sorted[i].id, sorted[i + 1].id);
    }
  }
  return indices;
}
