import { describe, expect, it } from "vitest";

import { connectedFiles, mostImported, neighborhood, shortPath } from "./dependency-neighborhood";
import { buildFileTree, FolderNode } from "./file-tree";
import { githubAvatarUrl, githubFileUrl } from "./github-links";

describe("githubFileUrl", () => {
  const repo = "https://github.com/pallets/markupsafe";

  it("pins files and line ranges to the analyzed commit", () => {
    expect(githubFileUrl(repo, "abc123", "src/markupsafe/__init__.py", { start: 10, end: 40 })).toBe(
      "https://github.com/pallets/markupsafe/blob/abc123/src/markupsafe/__init__.py#L10-L40"
    );
    expect(githubFileUrl(repo, "abc123", "a.py", { start: 7 })).toBe(`${repo}/blob/abc123/a.py#L7`);
  });

  it("falls back to HEAD and encodes unusual path characters", () => {
    expect(githubFileUrl(`${repo}/`, null, "app/r/[owner]/page.tsx")).toBe(
      `${repo}/blob/HEAD/app/r/%5Bowner%5D/page.tsx`
    );
  });

  it("builds avatar URLs", () => {
    expect(githubAvatarUrl("atikulmunna")).toBe("https://github.com/atikulmunna.png?size=64");
  });
});

describe("buildFileTree", () => {
  const names = (folder: FolderNode) => folder.children.map((child) => child.name);

  it("puts folders before files, alphabetically, with file counts", () => {
    const tree = buildFileTree(["README.md", "backend/app/main.py", "backend/app/deps.py", "backend/Dockerfile", "a.txt"]);

    expect(names(tree)).toEqual(["backend", "a.txt", "README.md"]);
    expect(tree.fileCount).toBe(5);
    const backend = tree.children[0] as FolderNode;
    expect(names(backend)).toEqual(["app", "Dockerfile"]);
    expect((backend.children[0] as FolderNode).fileCount).toBe(2);
  });

  it("collapses a chain of single folders into one row", () => {
    const tree = buildFileTree(["src/markupsafe/__init__.py", "src/markupsafe/_native.py", "tests/test_escape.py"]);

    const src = tree.children[0] as FolderNode;
    expect(src.name).toBe("src/markupsafe");
    expect(src.path).toBe("src/markupsafe");
    expect(names(src)).toEqual(["__init__.py", "_native.py"]);
  });

  it("handles an empty list", () => {
    expect(buildFileTree([])).toEqual({ kind: "folder", name: "", path: "", children: [], fileCount: 0 });
  });
});

describe("dependency neighborhood", () => {
  const edges = [
    { source: "app/api.py", target: "app/core.py" },
    { source: "app/cli.py", target: "app/core.py" },
    { source: "app/core.py", target: "app/util.py" },
    { source: "app/api.py", target: "app/util.py" },
  ];

  it("splits a file's edges into imports and importers", () => {
    expect(neighborhood(edges, "app/core.py")).toEqual({
      center: "app/core.py",
      imports: ["app/util.py"],
      importedBy: ["app/api.py", "app/cli.py"],
    });
  });

  it("starts from the most imported file, breaking ties alphabetically", () => {
    expect(mostImported(edges)).toBe("app/core.py");
    expect(mostImported([])).toBeNull();
  });

  it("lists connected files and shortens long paths", () => {
    expect(connectedFiles(edges)).toEqual(["app/api.py", "app/cli.py", "app/core.py", "app/util.py"]);
    expect(shortPath("backend/app/api/v1/chat.py")).toBe("v1/chat.py");
    expect(shortPath("main.py")).toBe("main.py");
  });
});
