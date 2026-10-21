export type FileNode = { kind: "file"; name: string; path: string };
export type FolderNode = { kind: "folder"; name: string; path: string; children: TreeNode[]; fileCount: number };
export type TreeNode = FileNode | FolderNode;

type Draft = { folders: Map<string, Draft>; files: string[] };

function emptyDraft(): Draft {
  return { folders: new Map(), files: [] };
}

function toFolder(name: string, path: string, draft: Draft): FolderNode {
  const folders = [...draft.folders.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([child, childDraft]) => toFolder(child, path ? `${path}/${child}` : child, childDraft));
  const files: FileNode[] = [...draft.files]
    .sort((a, b) => a.localeCompare(b))
    .map((file) => ({ kind: "file", name: file, path: path ? `${path}/${file}` : file }));
  const fileCount = files.length + folders.reduce((total, folder) => total + folder.fileCount, 0);
  return collapseChain({ kind: "folder", name, path, children: [...folders, ...files], fileCount });
}

// A folder whose only entry is another folder reads better as one row, the way GitHub shows
// `src/itsdangerous` instead of two levels.
function collapseChain(folder: FolderNode): FolderNode {
  const only = folder.children.length === 1 ? folder.children[0] : null;
  if (!folder.name || !only || only.kind !== "folder") {
    return folder;
  }
  return { ...only, name: `${folder.name}/${only.name}` };
}

// Folders first, then files, each alphabetical. The root has an empty name.
export function buildFileTree(paths: string[]): FolderNode {
  const root = emptyDraft();
  for (const path of paths) {
    const parts = path.split("/").filter(Boolean);
    const file = parts.pop();
    if (!file) {
      continue;
    }
    let draft = root;
    for (const part of parts) {
      if (!draft.folders.has(part)) {
        draft.folders.set(part, emptyDraft());
      }
      draft = draft.folders.get(part) as Draft;
    }
    draft.files.push(file);
  }
  return toFolder("", "", root);
}
