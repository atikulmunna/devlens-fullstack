// An API call that came back with an error status, with what a person needs to act on it.
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly retryAfterSeconds: number | null = null
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

// What to tell someone whose question failed: what happened and what to do next.
export function friendlyChatError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 429) {
      const minutes = err.retryAfterSeconds ? Math.max(1, Math.ceil(err.retryAfterSeconds / 60)) : null;
      const wait = minutes ? `in about ${minutes} minute${minutes === 1 ? "" : "s"}` : "later";
      return `You have reached the hourly limit for questions. Try again ${wait}.`;
    }
    if (err.status === 401) {
      return "Your sign-in has expired. Sign in again to keep asking.";
    }
    if (err.status === 404) {
      return "This chat could not be found. Start a new chat and ask again.";
    }
    if (err.status === 400) {
      return err.message;
    }
    if (err.status >= 500) {
      return "DevLens could not answer right now. Try again in a moment.";
    }
    return err.message;
  }
  if (err instanceof TypeError) {
    return "The connection dropped before the answer arrived. Check your connection and ask again.";
  }
  return "The question could not be answered. Try again in a moment.";
}

// Creating or stopping a share link failed: what to do about it.
export function friendlyShareError(err: unknown, action: "create" | "stop"): string {
  if (err instanceof ApiError && err.status === 401) {
    return "Your sign-in has expired. Sign in again to manage share links.";
  }
  if (action === "create" && err instanceof ApiError && err.status === 404) {
    return "There is nothing to share yet: this repository has no finished analysis.";
  }
  return action === "create"
    ? "The share link could not be created. Try again in a moment."
    : "Sharing could not be stopped. Try again in a moment.";
}

// Why a shared link did not open, for someone who may never have used DevLens.
export function sharedLinkError(err: unknown): string {
  if (err instanceof ApiError && err.status === 401) {
    if (/expired/i.test(err.message)) {
      return "This link has expired. Ask the person who shared it for a new one.";
    }
    if (/revoked/i.test(err.message)) {
      return "The person who shared this link has stopped sharing it.";
    }
    return "This link is not valid. Check that it was copied in full.";
  }
  if (err instanceof ApiError && err.status === 404) {
    return "The repository behind this link is no longer in DevLens.";
  }
  if (err instanceof TypeError) {
    return "DevLens could not be reached. Check your connection and reload the page.";
  }
  return "The shared overview could not be loaded. Try again in a moment.";
}
