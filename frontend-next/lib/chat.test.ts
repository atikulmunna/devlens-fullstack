import { describe, expect, it } from "vitest";

import { ApiError, friendlyChatError, isAbort } from "./errors";
import { parseBlocks, parseInline } from "./markdown";

describe("parseInline", () => {
  it("reads code, bold, italic, and citation markers", () => {
    expect(parseInline("Use `loads` with **max_age** and *care* [1, 3][2].")).toEqual([
      { kind: "text", text: "Use " },
      { kind: "code", text: "loads" },
      { kind: "text", text: " with " },
      { kind: "strong", children: [{ kind: "text", text: "max_age" }] },
      { kind: "text", text: " and " },
      { kind: "em", children: [{ kind: "text", text: "care" }] },
      { kind: "text", text: " " },
      { kind: "cite", refs: [1, 3], raw: "[1, 3]" },
      { kind: "cite", refs: [2], raw: "[2]" },
      { kind: "text", text: "." },
    ]);
  });

  it("leaves snake_case, type hints, and lone asterisks alone", () => {
    expect(parseInline("list[str] and max_age * 2")).toEqual([{ kind: "text", text: "list[str] and max_age * 2" }]);
  });
});

describe("parseBlocks", () => {
  it("splits paragraphs, headings, lists, and fenced code", () => {
    const blocks = parseBlocks(
      "## Flow\n\nIt signs data.\nThen loads it.\n\n- first\n- second\n  continued\n\n1. one\n2. two\n\n```python\nx = 1\n```"
    );

    expect(blocks.map((block) => block.kind)).toEqual(["heading", "paragraph", "list", "list", "code"]);
    expect(blocks[1]).toEqual({ kind: "paragraph", inline: [{ kind: "text", text: "It signs data. Then loads it." }] });
    expect(blocks[2]).toEqual({
      kind: "list",
      ordered: false,
      items: [[{ kind: "text", text: "first" }], [{ kind: "text", text: "second continued" }]],
    });
    expect(blocks[3]).toMatchObject({ kind: "list", ordered: true });
    expect(blocks[4]).toEqual({ kind: "code", language: "python", text: "x = 1" });
  });

  it("keeps a list together across blank lines between items", () => {
    const blocks = parseBlocks("- Purpose: signing [1].\n\n- Components: serializers [2].\n\nThat is all.");

    expect(blocks.map((block) => block.kind)).toEqual(["list", "paragraph"]);
    expect(blocks[0]).toMatchObject({ items: [expect.anything(), expect.anything()] });
  });

  it("treats an unclosed fence in a streaming answer as code so far", () => {
    expect(parseBlocks("Here:\n```js\nconst a = 1;")).toEqual([
      { kind: "paragraph", inline: [{ kind: "text", text: "Here:" }] },
      { kind: "code", language: "js", text: "const a = 1;" },
    ]);
  });
});

describe("friendlyChatError", () => {
  it("says when the hourly limit resets", () => {
    expect(friendlyChatError(new ApiError("Rate limit exceeded", 429, 690))).toBe(
      "You have reached the hourly limit for questions. Try again in about 12 minutes."
    );
    expect(friendlyChatError(new ApiError("Rate limit exceeded", 429, null))).toContain("Try again later.");
  });

  it("explains sign-in, missing chats, server trouble, and dropped connections", () => {
    expect(friendlyChatError(new ApiError("x", 401))).toMatch(/Sign in again/);
    expect(friendlyChatError(new ApiError("x", 404))).toMatch(/Start a new chat/);
    expect(friendlyChatError(new ApiError("x", 503))).toMatch(/Try again in a moment/);
    expect(friendlyChatError(new ApiError("Message content must not be empty", 400))).toBe(
      "Message content must not be empty"
    );
    expect(friendlyChatError(new TypeError("Failed to fetch"))).toMatch(/connection dropped/);
  });

  it("recognizes a stopped request", () => {
    expect(isAbort(new DOMException("stopped", "AbortError"))).toBe(true);
    expect(isAbort(new Error("x"))).toBe(false);
  });
});
