import { describe, expect, it } from "vitest";

import { layoutBlast, MAX_RINGS } from "./blast-layout";

describe("layoutBlast", () => {
  it("places each import distance on its own ring, nearest first", () => {
    const layout = layoutBlast([["a.py", "b.py", "c.py"], ["d.py"]]);

    expect(layout.rings.map((ring) => ring.depth)).toEqual([1, 2]);
    expect(layout.nodes.map((node) => [node.path, node.depth])).toEqual([
      ["a.py", 1],
      ["b.py", 1],
      ["c.py", 1],
      ["d.py", 2],
    ]);
    const distance = (node: { x: number; y: number }) => Math.hypot(node.x - layout.cx, node.y - layout.cy);
    const ring1 = layout.nodes.filter((node) => node.depth === 1).map(distance);
    const ring2 = layout.nodes.filter((node) => node.depth === 2).map(distance);
    expect(Math.max(...ring1)).toBeLessThan(Math.min(...ring2));
  });

  it("starts the first ring at the top and labels nodes away from the center", () => {
    const layout = layoutBlast([["top.py", "right.py", "bottom.py", "left.py"]]);
    const [top, right, , left] = layout.nodes;

    expect(top.y).toBeLessThan(layout.cy);
    expect(right.anchor).toBe("start");
    expect(left.anchor).toBe("end");
  });

  it("counts files beyond the last drawn ring instead of drawing them", () => {
    const levels = Array.from({ length: MAX_RINGS + 2 }, (_, depth) => [`d${depth}.py`, `e${depth}.py`]);
    const layout = layoutBlast(levels);

    expect(layout.rings).toHaveLength(MAX_RINGS);
    expect(layout.hiddenDeeper).toBe(4);
    expect(layout.nodes.every((node) => node.x > 0 && node.x < layout.width && node.y > 0 && node.y < layout.height)).toBe(true);
  });

  it("handles a commit nothing imports", () => {
    const layout = layoutBlast([]);
    expect(layout.nodes).toEqual([]);
    expect(layout.rings).toEqual([]);
    expect(layout.width).toBeGreaterThan(layout.height);
  });
});
