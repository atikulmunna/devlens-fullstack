"use client";

import { useState } from "react";
import { useAuth } from "@/components/auth";
import { createShareLink, revokeShareLink, ShareLink } from "@/lib/api";
import { friendlyShareError } from "@/lib/errors";
import { longDate } from "@/lib/format";

// A read-only link to this repository's overview for people without a DevLens sign-in. Links are
// tied to the signed-in user who made them, so the button only shows when someone is signed in.
export function ShareButton({ repoId }: { repoId: string }) {
  const { status } = useAuth();
  const [link, setLink] = useState<ShareLink | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stopped, setStopped] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status !== "signed-in") {
    return null;
  }
  // Built from this page's address, so the link points wherever DevLens was opened from.
  const url = link ? `${window.location.origin}/share/${link.share_token}` : "";

  async function toggle() {
    setError(null);
    setStopped(false);
    if (link) {
      setOpen((current) => !current);
      return;
    }
    setBusy(true);
    try {
      setLink(await createShareLink(repoId));
      setOpen(true);
    } catch (err) {
      setError(friendlyShareError(err, "create"));
      setOpen(true);
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Copying is blocked in this browser. Select the link to copy it.");
    }
  }

  async function stop() {
    if (!link) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await revokeShareLink(link.share_id);
      setLink(null);
      setStopped(true);
    } catch (err) {
      setError(friendlyShareError(err, "stop"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="button secondary share-toggle"
        aria-expanded={open}
        aria-controls="share-panel"
        disabled={busy}
        onClick={() => void toggle()}
      >
        {busy && !link ? "Creating link..." : "Share"}
      </button>
      {open && (
        <div id="share-panel" className="share-panel">
          {link && (
            <>
              <p>
                Anyone with this link can read the overview until {longDate(link.expires_at)}, without signing in.
                Chat and Changes stay private.
              </p>
              <div className="share-row">
                <input
                  className="input mono"
                  readOnly
                  value={url}
                  aria-label="Share link"
                  onFocus={(event) => event.currentTarget.select()}
                />
                <button type="button" className="button" onClick={() => void copy()}>
                  {copied ? "Copied" : "Copy link"}
                </button>
              </div>
              <button type="button" className="link-button" disabled={busy} onClick={() => void stop()}>
                Stop sharing
              </button>
            </>
          )}
          {stopped && <p role="status">Sharing stopped. The link no longer opens.</p>}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
        </div>
      )}
    </>
  );
}
