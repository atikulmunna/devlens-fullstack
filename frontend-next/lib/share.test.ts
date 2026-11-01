import { describe, expect, it } from "vitest";

import { ApiError, friendlyShareError, sharedLinkError } from "./errors";
import { longDate, windowLabel } from "./format";

describe("sharedLinkError", () => {
  it("tells expired, stopped, and broken links apart", () => {
    expect(sharedLinkError(new ApiError("Share token expired", 401))).toMatch(/expired.*new one/);
    expect(sharedLinkError(new ApiError("Share token revoked", 401))).toMatch(/stopped sharing/);
    expect(sharedLinkError(new ApiError("Invalid share token", 401))).toMatch(/copied in full/);
  });

  it("explains a missing repository and a dropped connection", () => {
    expect(sharedLinkError(new ApiError("Repository not found", 404))).toMatch(/no longer in DevLens/);
    expect(sharedLinkError(new TypeError("Failed to fetch"))).toMatch(/could not be reached/);
    expect(sharedLinkError(new ApiError("boom", 500))).toMatch(/Try again in a moment/);
  });
});

describe("friendlyShareError", () => {
  it("asks for sign-in again whichever action failed", () => {
    expect(friendlyShareError(new ApiError("x", 401), "create")).toMatch(/Sign in again/);
    expect(friendlyShareError(new ApiError("x", 401), "stop")).toMatch(/Sign in again/);
  });

  it("explains that a repository without an analysis has nothing to share", () => {
    expect(friendlyShareError(new ApiError("Analysis result not found", 404), "create")).toMatch(/nothing to share/);
    expect(friendlyShareError(new ApiError("Share token not found", 404), "stop")).toMatch(/could not be stopped/);
  });
});

describe("longDate", () => {
  it("spells out the day a link stops working", () => {
    expect(longDate("2026-10-28T12:00:00Z")).toBe("October 28, 2026");
  });
});

describe("windowLabel", () => {
  it("names a year as such and other windows in days", () => {
    expect(windowLabel(365)).toBe("the past year");
    expect(windowLabel(90)).toBe("the past 90 days");
    expect(windowLabel(null)).toBe("the past year");
  });
});
