import type { ChatCitation } from "@/lib/api";
import { citationUrl, SourceLinks } from "./answer";

function citationLabel(citation: ChatCitation): string {
  const ref = citation.ref ? `[${citation.ref}] ` : "";
  const path = citation.file_path || "source";
  const line = citation.line_start ? `:${citation.line_start}` : "";
  return `${ref}${path}${line}`;
}

// Every source the model was given, each opening its lines on GitHub. When the answer cites some
// by [n], the rest are drawn muted and dashed, like the unwalked trail in the progress steps.
export function Citations({ citations, ...links }: SourceLinks) {
  const anyCited = citations.some((citation) => citation.cited);
  return (
    <div className="citations">
      {citations.map((citation, index) => {
        const unused = anyCited && !citation.cited;
        const url = citationUrl(citation, links);
        const className = `citation-pill mono${unused ? " unused" : ""}`;
        const label = (
          <>
            {citationLabel(citation)}
            {unused && <span className="visually-hidden"> (given to the model, not cited)</span>}
          </>
        );
        return url ? (
          <a key={index} className={className} href={url} target="_blank" rel="noreferrer">
            {label}
          </a>
        ) : (
          <span key={index} className={className}>
            {label}
          </span>
        );
      })}
    </div>
  );
}
