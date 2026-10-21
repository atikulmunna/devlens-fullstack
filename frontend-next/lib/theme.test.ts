import { describe, expect, it } from "vitest";

import { saveTheme, storedTheme, THEME_KEY, THEME_SCRIPT } from "./theme";

function memoryStorage(initial: Record<string, string> = {}) {
  const items = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => void items.set(key, value),
  };
}

const blocked = {
  getItem: () => {
    throw new DOMException("blocked", "SecurityError");
  },
  setItem: () => {
    throw new DOMException("blocked", "SecurityError");
  },
};

describe("storedTheme", () => {
  it("is light unless dark was chosen", () => {
    expect(storedTheme(memoryStorage())).toBe("light");
    expect(storedTheme(memoryStorage({ [THEME_KEY]: "dark" }))).toBe("dark");
    expect(storedTheme(memoryStorage({ [THEME_KEY]: "sepia" }))).toBe("light");
  });

  it("falls back to light when storage is missing or blocked", () => {
    expect(storedTheme(undefined)).toBe("light");
    expect(storedTheme(blocked)).toBe("light");
  });
});

describe("saveTheme", () => {
  it("remembers the choice for the next visit", () => {
    const storage = memoryStorage();
    expect(saveTheme(storage, "dark")).toBe(true);
    expect(storedTheme(storage)).toBe("dark");
  });

  it("reports when the choice cannot be kept", () => {
    expect(saveTheme(blocked, "dark")).toBe(false);
    expect(saveTheme(undefined, "dark")).toBe(false);
  });
});

describe("THEME_SCRIPT", () => {
  it("reads the same key the toggle writes", () => {
    expect(THEME_SCRIPT).toContain(`"${THEME_KEY}"`);
  });
});
