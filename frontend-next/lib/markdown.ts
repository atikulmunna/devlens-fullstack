// A small Markdown reader for model answers: paragraphs, headings, bullet and numbered lists,
// fenced code, inline code, bold, italic, and citation markers like [2] or [1, 3]. It returns a
// tree that the answer component renders as React elements, so model output never becomes HTML.
// It also accepts the half-finished text of a streaming answer (an unclosed fence is code so far).

export type Inline =
  | { kind: "text"; text: string }
  | { kind: "code"; text: string }
  | { kind: "strong"; children: Inline[] }
  | { kind: "em"; children: Inline[] }
  | { kind: "cite"; refs: number[]; raw: string };

export type Block =
  | { kind: "paragraph"; inline: Inline[] }
  | { kind: "heading"; inline: Inline[] }
  | { kind: "list"; ordered: boolean; items: Inline[][] }
  | { kind: "code"; language: string; text: string };

const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+?\*\*)|(\*[^*\s][^*\n]*?\*)|(\[\d+(?:\s*,\s*\d+)*\])/g;
const FENCE = /^\s*```\s*([\w+#.-]*)\s*$/;
const HEADING = /^\s{0,3}#{1,6}\s+(.*)$/;
const LIST_ITEM = /^\s*([-*+•]|\d+[.)])\s+(.*)$/;

export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    const index = match.index ?? 0;
    if (index > last) {
      out.push({ kind: "text", text: text.slice(last, index) });
    }
    const [token, code, strong, em, cite] = match;
    if (code) {
      out.push({ kind: "code", text: code.slice(1, -1) });
    } else if (strong) {
      out.push({ kind: "strong", children: parseInline(strong.slice(2, -2)) });
    } else if (em) {
      out.push({ kind: "em", children: parseInline(em.slice(1, -1)) });
    } else if (cite) {
      out.push({ kind: "cite", refs: cite.slice(1, -1).split(",").map((n) => Number(n.trim())), raw: cite });
    }
    last = index + token.length;
  }
  if (last < text.length) {
    out.push({ kind: "text", text: text.slice(last) });
  }
  return out;
}

export function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let blankSinceItem = false;

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ kind: "paragraph", inline: parseInline(paragraph.join(" ")) });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list) {
      blocks.push({ kind: "list", ordered: list.ordered, items: list.items.map(parseInline) });
      list = null;
    }
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const fence = line.match(FENCE);
    if (fence) {
      flushParagraph();
      flushList();
      const code: string[] = [];
      for (i += 1; i < lines.length && !FENCE.test(lines[i]); i += 1) {
        code.push(lines[i]);
      }
      blocks.push({ kind: "code", language: fence[1], text: code.join("\n") });
      continue;
    }
    if (!line.trim()) {
      flushParagraph();
      blankSinceItem = list !== null;
      continue;
    }
    const heading = line.match(HEADING);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "heading", inline: parseInline(heading[1].trim()) });
      continue;
    }
    const item = line.match(LIST_ITEM);
    if (item) {
      flushParagraph();
      const ordered = /\d/.test(item[1]);
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push(item[2].trim());
      blankSinceItem = false;
      continue;
    }
    // A line right under a list item continues it; after a blank line it starts a paragraph.
    if (list && !blankSinceItem) {
      list.items[list.items.length - 1] += ` ${line.trim()}`;
      continue;
    }
    flushList();
    paragraph.push(line.trim());
  }
  flushParagraph();
  flushList();
  return blocks;
}
