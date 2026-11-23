// Corner topology in Gmsh/meshio order. Preview cells are linearized at their vertices.
export const facesByCorners = {
  4: [
    [0, 2, 1],
    [0, 1, 3],
    [1, 2, 3],
    [2, 0, 3],
  ],
  5: [
    [0, 3, 2, 1],
    [0, 1, 4],
    [1, 2, 4],
    [2, 3, 4],
    [3, 0, 4],
  ],
  6: [
    [0, 2, 1],
    [3, 4, 5],
    [0, 1, 4, 3],
    [1, 2, 5, 4],
    [2, 0, 3, 5],
  ],
  8: [
    [0, 3, 2, 1],
    [4, 5, 6, 7],
    [0, 1, 5, 4],
    [1, 2, 6, 5],
    [2, 3, 7, 6],
    [3, 0, 4, 7],
  ],
};

const edgesByCorners = {};
for (const [n, faces] of Object.entries(facesByCorners)) {
  const edges = new Map();
  for (const face of faces)
    face.forEach((i, k) => {
      const j = face[(k + 1) % face.length];
      edges.set(Math.min(i, j) + ':' + Math.max(i, j), [i, j]);
    });
  edgesByCorners[n] = [...edges.values()];
}

export function sectionCells(points, cells, { axis, positionMm, keepPositive }, tolerance) {
  const vertices = [],
    faces = [];
  const shared = new Map();
  const u = (axis + 1) % 3,
    v = (axis + 2) % 3;
  function vertex(key, source) {
    if (!shared.has(key)) {
      const point = source.slice();
      point[axis] = positionMm;
      shared.set(key, vertices.length);
      vertices.push(point);
    }
    return shared.get(key);
  }

  cells.forEach((cell) => {
    const distance = cell.map((id) => points[id][axis] - positionMm);
    const lo = Math.min(...distance),
      hi = Math.max(...distance);
    // At an existing cell face only the cell on the retained side owns the section.
    if (lo > tolerance || hi < -tolerance) return;
    if (keepPositive ? hi <= tolerance : lo >= -tolerance) return;
    const ring = new Set();
    for (const [a, b] of edgesByCorners[cell.length]) {
      const da = distance[a],
        db = distance[b];
      const i = cell[a],
        j = cell[b];
      if (Math.abs(da) <= tolerance) ring.add(vertex(i, points[i]));
      if (Math.abs(db) <= tolerance) ring.add(vertex(j, points[j]));
      if (Math.min(da, db) >= -tolerance || Math.max(da, db) <= tolerance) continue;
      const key = i < j ? i + ':' + j : j + ':' + i;
      const t = da / (da - db);
      const p = points[i].map((value, k) => value + t * (points[j][k] - value));
      ring.add(vertex(key, p));
    }
    if (ring.size < 3) return;
    const ids = [...ring];
    const cu = ids.reduce((sum, i) => sum + vertices[i][u], 0) / ids.length;
    const cv = ids.reduce((sum, i) => sum + vertices[i][v], 0) / ids.length;
    const angle = (i) => Math.atan2(vertices[i][v] - cv, vertices[i][u] - cu);
    ids.sort((i, j) => angle(i) - angle(j));
    if (keepPositive) ids.reverse();
    faces.push(ids);
  });
  return { vertices, faces };
}
