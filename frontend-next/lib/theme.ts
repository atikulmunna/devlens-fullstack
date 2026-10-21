export type Theme = "light" | "dark";

type ThemeStorage = Pick<Storage, "getItem" | "setItem">;

// deploy/gate.html reads the same key, so the access page matches the app.
export const THEME_KEY = "devlens-theme";

// Runs in <head> before the first paint, so a saved dark choice never flashes light first.
export const THEME_SCRIPT = `try{if(localStorage.getItem(${JSON.stringify(THEME_KEY)})==="dark")document.documentElement.dataset.theme="dark"}catch(e){/* storage blocked: stay light */}`;

// Reading localStorage itself throws when site data is blocked.
export function browserStorage(): ThemeStorage | undefined {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}

// Light unless the visitor chose dark.
export function storedTheme(storage: ThemeStorage | undefined): Theme {
  try {
    return storage?.getItem(THEME_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

// False when the choice cannot be kept; it still applies to the page that is open.
export function saveTheme(storage: ThemeStorage | undefined, theme: Theme): boolean {
  if (!storage) {
    return false;
  }
  try {
    storage.setItem(THEME_KEY, theme);
    return true;
  } catch {
    return false;
  }
}
