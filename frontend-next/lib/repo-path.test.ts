import { describe, expect, it } from "vitest";

import { repoPath, tabFromPath } from "./repo-path";

describe("repoPath", () => {
  it("builds readable addresses for each tab", () => {
    expect(repoPath("pallets/itsdangerous")).toBe("/r/pallets/itsdangerous");
    expect(repoPath("pallets/itsdangerous", "chat")).toBe("/r/pallets/itsdangerous/chat");
    expect(repoPath("pallets/itsdangerous", "changes")).toBe("/r/pallets/itsdangerous/changes");
  });

  it("keeps GitHub's allowed name characters readable", () => {
    expect(repoPath("vercel/next.js")).toBe("/r/vercel/next.js");
    expect(repoPath("some_org/my-repo_v2")).toBe("/r/some_org/my-repo_v2");
  });
});

describe("tabFromPath", () => {
  it("reads the tab from the path", () => {
    expect(tabFromPath("/r/pallets/itsdangerous")).toBe("overview");
    expect(tabFromPath("/r/pallets/itsdangerous/chat")).toBe("chat");
    expect(tabFromPath("/r/pallets/itsdangerous/changes/")).toBe("changes");
  });

  it("does not mistake a repository named like a tab for a tab", () => {
    expect(tabFromPath("/r/someone/chat")).toBe("overview");
    expect(tabFromPath("/r/someone/chat/chat")).toBe("chat");
    expect(tabFromPath("/r/someone/changes/changes")).toBe("changes");
  });
});
