import { layoutBlast } from "@/lib/blast-layout";
import { shortPath } from "@/lib/dependency-neighborhood";
import { plural } from "@/lib/format";

// Labels stay readable up to this many files on a ring; past it the list below names them.
const LABELED_PER_RING = 10;

type Props = { changed: string[]; byDepth: string[][] };

// The commit's reach drawn as terrain: what changed at the summit, files importing it on the first
// contour, files importing those on the next.
export function BlastMap({ changed, byDepth }: Props) {
  const layout = layoutBlast(byDepth);
  const crowded = new Set(
    layout.rings.filter((ring) => (byDepth[ring.depth - 1] ?? []).length > LABELED_PER_RING).map((ring) => ring.depth)
  );
  const summit = changed.length === 1 ? shortPath(changed[0]) : plural(changed.length, "changed file");

  return (
    <figure className="blast">
      <svg
        className="blast-map"
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        role="img"
        aria-label={`${summit}; ${byDepth.map((level, i) => `${plural(level.length, "file")} at ${i + 1} ${i === 0 ? "import" : "imports"} away`).join(", ")}`}
      >
        {layout.rings.map((ring) => (
          <path key={ring.depth} className={ring.depth === 1 ? "ring" : "ring-faint"} d={ring.path} />
        ))}
        {layout.nodes.map((node) => (
          <g key={node.path}>
            <title>{node.path}</title>
            <circle className="node" cx={node.x} cy={node.y} r={4.5} />
            {!crowded.has(node.depth) && (
              <text className="label" x={node.x + (node.anchor === "start" ? 8 : -8)} y={node.y + 4} textAnchor={node.anchor}>
                {shortPath(node.path)}
              </text>
            )}
          </g>
        ))}
        <circle className="node-changed" cx={layout.cx} cy={layout.cy} r={9} />
        <text className="label" x={layout.cx} y={layout.cy + 26} textAnchor="middle">
          {summit}
        </text>
      </svg>
      <figcaption className="muted">
        Each ring out is one more import away from the change.
        {layout.hiddenDeeper > 0 && ` ${plural(layout.hiddenDeeper, "file")} further out are listed below.`}
      </figcaption>
    </figure>
  );
}
