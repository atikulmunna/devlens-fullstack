export type ImportEdge = { source: string; target: string };

// One file's place in the import graph: what it imports, and what imports it.
export type Neighborhood = { center: string; imports: string[]; importedBy: string[] };

export function neighborhood(edges: ImportEdge[], center: string): Neighborhood {
  const imports = new Set<string>();
  const importedBy = new Set<string>();
  for (const edge of edges) {
    if (edge.source === center) {
      imports.add(edge.target);
    }
    if (edge.target === center) {
      importedBy.add(edge.source);
    }
  }
  const sorted = (files: Set<string>) => [...files].sort((a, b) => a.localeCompare(b));
  return { center, imports: sorted(imports), importedBy: sorted(importedBy) };
}

// Files that appear in at least one import, alphabetical.
export function connectedFiles(edges: ImportEdge[]): string[] {
  const files = new Set<string>();
  for (const edge of edges) {
    files.add(edge.source);
    files.add(edge.target);
  }
  return [...files].sort((a, b) => a.localeCompare(b));
}

// The file the most others import: the natural first view of a codebase's structure.
export function mostImported(edges: ImportEdge[]): string | null {
  const counts = new Map<string, number>();
  for (const edge of edges) {
    counts.set(edge.target, (counts.get(edge.target) ?? 0) + 1);
  }
  let best: string | null = null;
  let bestCount = 0;
  for (const [file, count] of counts) {
    if (count > bestCount || (count === bestCount && best !== null && file < best)) {
      best = file;
      bestCount = count;
    }
  }
  return best;
}

// The last two path segments: enough to tell `api/v1/chat.py` from `services/chat.py` in a label.
export function shortPath(path: string): string {
  const parts = path.split("/");
  return parts.length <= 2 ? path : parts.slice(-2).join("/");
}
