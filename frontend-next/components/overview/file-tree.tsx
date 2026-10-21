import { buildFileTree, TreeNode } from "@/lib/file-tree";
import { plural } from "@/lib/format";
import { githubFileUrl } from "@/lib/github-links";

type Props = { paths: string[]; githubUrl: string; commitSha: string | null | undefined };

function Node({ node, githubUrl, commitSha }: { node: TreeNode } & Omit<Props, "paths">) {
  if (node.kind === "file") {
    return (
      <li>
        <a className="mono" href={githubFileUrl(githubUrl, commitSha, node.path)} rel="noreferrer">
          {node.name}
        </a>
      </li>
    );
  }
  return (
    <li>
      <details>
        <summary>
          <span className="mono">{node.name}/</span> <span className="muted">{plural(node.fileCount, "file")}</span>
        </summary>
        <ul>
          {node.children.map((child) => (
            <Node key={child.path} node={child} githubUrl={githubUrl} commitSha={commitSha} />
          ))}
        </ul>
      </details>
    </li>
  );
}

// The indexed files as collapsible folders; every file opens on GitHub at the analyzed commit.
export function FileTree({ paths, githubUrl, commitSha }: Props) {
  if (paths.length === 0) {
    return <p className="muted">No files were indexed.</p>;
  }
  const root = buildFileTree(paths);
  return (
    <div className="file-tree">
      <p className="muted">{plural(root.fileCount, "indexed file")}.</p>
      <ul>
        {root.children.map((child) => (
          <Node key={child.path} node={child} githubUrl={githubUrl} commitSha={commitSha} />
        ))}
      </ul>
    </div>
  );
}
