// Lays out a commit's blast radius as contour rings: the changed files at the summit, files that
// import them on the first ring, files that import those on the next, the way the home page
// illustration draws it. Rings wobble a little so they read as terrain, and nodes sit on the line.

export const MAX_RINGS = 3;
const FIRST_RADIUS = 78;
const RING_GAP = 66;
// Labels run sideways from their node, so the sides need room the top and bottom do not.
const MARGIN_X = 130;
const MARGIN_Y = 36;

export type PlacedNode = { path: string; depth: number; x: number; y: number; anchor: "start" | "end" };
export type Ring = { depth: number; path: string };
export type BlastLayout = {
  width: number;
  height: number;
  cx: number;
  cy: number;
  rings: Ring[];
  nodes: PlacedNode[];
  // Files more than MAX_RINGS imports away, counted but not drawn.
  hiddenDeeper: number;
};

function radiusAt(depth: number, angle: number): number {
  const base = FIRST_RADIUS + (depth - 1) * RING_GAP;
  return base * (1 + 0.045 * Math.sin(3 * angle + depth) + 0.025 * Math.cos(5 * angle - depth));
}

function point(cx: number, cy: number, depth: number, angle: number): [number, number] {
  const r = radiusAt(depth, angle);
  return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
}

function ringPath(cx: number, cy: number, depth: number): string {
  const steps = 72;
  const parts: string[] = [];
  for (let i = 0; i <= steps; i += 1) {
    const [x, y] = point(cx, cy, depth, (i / steps) * 2 * Math.PI);
    parts.push(`${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`);
  }
  return `${parts.join(" ")} Z`;
}

export function layoutBlast(byDepth: string[][]): BlastLayout {
  const drawn = byDepth.slice(0, MAX_RINGS).filter((level) => level.length > 0);
  // The outermost ring reaches about 7% past its base radius at its widest wobble.
  const reach = (FIRST_RADIUS + (Math.max(drawn.length, 1) - 1) * RING_GAP) * 1.07;
  const cx = reach + MARGIN_X;
  const cy = reach + MARGIN_Y;
  const nodes: PlacedNode[] = [];
  drawn.forEach((level, index) => {
    const depth = index + 1;
    // Start at the top, offset each ring by half a step so neighbors on adjacent rings do not line up.
    const step = (2 * Math.PI) / level.length;
    level.forEach((path, i) => {
      const angle = -Math.PI / 2 + i * step + (depth % 2 === 0 ? step / 2 : 0);
      const [x, y] = point(cx, cy, depth, angle);
      nodes.push({ path, depth, x, y, anchor: x < cx - 1 ? "end" : "start" });
    });
  });
  return {
    width: cx * 2,
    height: cy * 2,
    cx,
    cy,
    rings: drawn.map((_, index) => ({ depth: index + 1, path: ringPath(cx, cy, index + 1) })),
    nodes,
    hiddenDeeper: byDepth.slice(MAX_RINGS).reduce((total, level) => total + level.length, 0),
  };
}
