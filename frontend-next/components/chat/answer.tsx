import { Fragment, ReactNode } from "react";
import type { ChatCitation } from "@/lib/api";
import { githubFileUrl } from "@/lib/github-links";
import { Block, Inline, parseBlocks } from "@/lib/markdown";

export type SourceLinks = { citations: ChatCitation[]; githubUrl: string; commitSha?: string | null };

export function citationUrl(citation: ChatCitation, links: Omit<SourceLinks, "citations">): string | null {
  if (!citation.file_path) {
    return null;
  }
  const lines = citation.line_start ? { start: citation.line_start, end: citation.line_end } : undefined;
  return githubFileUrl(links.githubUrl, links.commitSha, citation.file_path, lines);
}

function renderInline(nodes: Inline[], links: SourceLinks): ReactNode[] {
  return nodes.map((node, index) => {
    switch (node.kind) {
      case "text":
        return <Fragment key={index}>{node.text}</Fragment>;
      case "code":
        return (
          <code key={index} className="inline-code">
            {node.text}
          </code>
        );
      case "strong":
        return <strong key={index}>{renderInline(node.children, links)}</strong>;
      case "em":
        return <em key={index}>{renderInline(node.children, links)}</em>;
      case "cite": {
        const cited = node.refs.map((ref) => links.citations.find((citation) => citation.ref === ref));
        // A number in brackets that is not one of this answer's sources stays as written.
        if (cited.some((citation) => !citation)) {
          return <Fragment key={index}>{node.raw}</Fragment>;
        }
        return (
          <sup key={index} className="cite">
            {cited.map((citation) => {
              const url = citation ? citationUrl(citation, links) : null;
              const label = `${citation?.file_path}:${citation?.line_start ?? 1}`;
              return url ? (
                <a key={citation?.ref} href={url} target="_blank" rel="noreferrer" title={label}>
                  {citation?.ref}
                </a>
              ) : (
                <span key={citation?.ref}>{citation?.ref}</span>
              );
            })}
          </sup>
        );
      }
    }
  });
}

function renderBlock(block: Block, index: number, links: SourceLinks): ReactNode {
  switch (block.kind) {
    case "paragraph":
      return <p key={index}>{renderInline(block.inline, links)}</p>;
    case "heading":
      return <h3 key={index}>{renderInline(block.inline, links)}</h3>;
    case "list": {
      const items = block.items.map((item, itemIndex) => <li key={itemIndex}>{renderInline(item, links)}</li>);
      return block.ordered ? <ol key={index}>{items}</ol> : <ul key={index}>{items}</ul>;
    }
    case "code":
      return (
        <pre key={index} className="code-block">
          <code data-language={block.language || undefined}>{block.text}</code>
        </pre>
      );
  }
}

// A model answer rendered from its Markdown; each [n] links to the lines it cites.
export function Answer({ content, ...links }: { content: string } & SourceLinks) {
  return <div className="answer">{parseBlocks(content).map((block, index) => renderBlock(block, index, links))}</div>;
}
