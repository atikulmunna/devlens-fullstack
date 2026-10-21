"use client";

import { KeyboardEvent, useEffect, useMemo, useState } from "react";
import { DependencyGraph, getDependencyGraph } from "@/lib/api";
import { connectedFiles, mostImported, neighborhood, shortPath } from "@/lib/dependency-neighborhood";
import { plural } from "@/lib/format";

const ROW = 30;
const PAD = 18;
const WIDTH = 760;
const MAX_DRAWN = 12;
const LEFT_TEXT_X = 236;
const RIGHT_TEXT_X = 524;
const CENTER_LEFT = 280;
const CENTER_RIGHT = 480;

type Side = "left" | "right";

function rowY(index: number, count: number, height: number): number {
  const top = (height - count * ROW) / 2;
  return top + index * ROW + ROW / 2;
}

function Neighbor({
  file,
  side,
  y,
  centerY,
  onSelect,
}: {
  file: string;
  side: Side;
  y: number;
  centerY: number;
  onSelect: (file: string) => void;
}) {
  const left = side === "left";
  const dotX = left ? LEFT_TEXT_X + 10 : RIGHT_TEXT_X - 10;
  const fromX = left ? dotX : CENTER_RIGHT;
  const toX = left ? CENTER_LEFT : dotX;
  const fromY = left ? y : centerY;
  const toY = left ? centerY : y;
  const bend = (toX - fromX) / 2;
  const select = () => onSelect(file);
  const onKey = (event: KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      select();
    }
  };
  return (
    <g className="dep-node" role="button" tabIndex={0} aria-label={`Center on ${file}`} onClick={select} onKeyDown={onKey}>
      <title>{file}</title>
      <path className="dep-edge" d={`M${fromX} ${fromY} C${fromX + bend} ${fromY}, ${toX - bend} ${toY}, ${toX} ${toY}`} />
      <circle className="dep-dot" cx={dotX} cy={y} r={4} />
      <rect className="dep-hit" x={left ? 0 : RIGHT_TEXT_X - 16} y={y - ROW / 2} width={left ? LEFT_TEXT_X + 18 : WIDTH - RIGHT_TEXT_X + 16} height={ROW} />
      <text className="dep-label" x={left ? LEFT_TEXT_X : RIGHT_TEXT_X} y={y + 4} textAnchor={left ? "end" : "start"}>
        {shortPath(file)}
      </text>
    </g>
  );
}

function Column({ title, files, onSelect }: { title: string; files: string[]; onSelect: (file: string) => void }) {
  return (
    <div>
      <h3>
        {title} <span className="muted">{files.length}</span>
      </h3>
      {files.length === 0 ? (
        <p className="muted">None.</p>
      ) : (
        <ul className="dep-list">
          {files.map((file) => (
            <li key={file}>
              <button type="button" className="link-button" onClick={() => onSelect(file)}>
                {file}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// One file's neighborhood in the import graph: what imports it (left) and what it imports
// (right). Choosing a neighbor recenters on it, so you can walk the codebase file by file.
export function DependencyView({ repoId }: { repoId: string }) {
  const [graph, setGraph] = useState<DependencyGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [center, setCenter] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    getDependencyGraph(repoId)
      .then((payload) => {
        if (!cancelled) {
          setGraph(payload);
          setCenter(mostImported(payload.edges));
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load imports");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repoId]);

  const files = useMemo(() => (graph ? connectedFiles(graph.edges) : []), [graph]);

  if (error) {
    return <p className="error">Could not load the import graph: {error}</p>;
  }
  if (!graph) {
    return <p className="muted">Loading imports...</p>;
  }
  if (!center) {
    return <p className="muted">No imports between indexed files were found.</p>;
  }

  const view = neighborhood(graph.edges, center);
  const left = view.importedBy.slice(0, MAX_DRAWN);
  const right = view.imports.slice(0, MAX_DRAWN);
  const height = Math.max(left.length, right.length, 1) * ROW + PAD * 2;
  const centerY = height / 2;
  const hidden = view.importedBy.length - left.length + (view.imports.length - right.length);
  const choose = (file: string) => {
    setCenter(file);
    setQuery("");
  };

  return (
    <div className="dependencies">
      <p className="muted">
        {plural(files.length, "file")} linked by {plural(graph.edges.length, "import")}. Starting from the most imported
        file; choose any file to recenter.
      </p>
      <label className="dep-picker">
        <span className="visually-hidden">Center on a file</span>
        <input
          className="input"
          list="dep-files"
          placeholder="Find a file"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            if (files.includes(event.target.value)) {
              choose(event.target.value);
            }
          }}
        />
        <datalist id="dep-files">
          {files.map((file) => (
            <option key={file} value={file} />
          ))}
        </datalist>
      </label>

      <svg className="dep-graph" viewBox={`0 0 ${WIDTH} ${height}`} role="group" aria-label={`Imports of ${center}`}>
        {left.map((file, index) => (
          <Neighbor key={`l-${file}`} file={file} side="left" y={rowY(index, left.length, height)} centerY={centerY} onSelect={choose} />
        ))}
        {right.map((file, index) => (
          <Neighbor key={`r-${file}`} file={file} side="right" y={rowY(index, right.length, height)} centerY={centerY} onSelect={choose} />
        ))}
        <rect className="dep-center" x={CENTER_LEFT} y={centerY - 18} width={CENTER_RIGHT - CENTER_LEFT} height={36} rx={6} />
        <text className="dep-center-label" x={(CENTER_LEFT + CENTER_RIGHT) / 2} y={centerY + 5} textAnchor="middle">
          <title>{center}</title>
          {shortPath(center)}
        </text>
      </svg>
      {hidden > 0 && <p className="muted dep-graph-note">{plural(hidden, "more file")} in the lists below.</p>}

      <p className="dep-current">
        Centered on <span className="mono">{center}</span>
      </p>
      <div className="dep-columns">
        <Column title="Imported by" files={view.importedBy} onSelect={choose} />
        <Column title="Imports" files={view.imports} onSelect={choose} />
      </div>
    </div>
  );
}
