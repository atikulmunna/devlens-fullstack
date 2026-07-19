"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import {
  ChatCitation,
  clearToken,
  createChatSession,
  getSuggestions,
  getToken,
  refreshAccessToken,
  sendChatMessageStream,
  setToken as persistToken
} from "@/lib/api";

type ChatBubble = {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  citations?: ChatCitation[];
  noCitation?: boolean;
};

function citationLabel(citation: ChatCitation): string {
  const path = citation.file_path || "source";
  const line = citation.line_start ? `:${citation.line_start}` : "";
  return `${path}${line}`;
}

export default function WorkspacePage() {
  const [tokenInput, setTokenInput] = useState("");
  const [hasToken, setHasToken] = useState(false);
  const [authNote, setAuthNote] = useState("No token saved.");

  const [repoId, setRepoId] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);

  const [messages, setMessages] = useState<ChatBubble[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const logRef = useRef<HTMLDivElement | null>(null);

  // Read the token and any ?repo= hint on mount (client-only, avoids Suspense).
  useEffect(() => {
    setHasToken(getToken().length > 0);
    setAuthNote(getToken().length > 0 ? "Token saved." : "No token saved.");
    const params = new URLSearchParams(window.location.search);
    const repo = params.get("repo");
    if (repo) {
      setRepoId(repo);
    }
  }, []);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [messages]);

  function saveToken() {
    persistToken(tokenInput);
    setHasToken(getToken().length > 0);
    setAuthNote(getToken().length > 0 ? "Token saved." : "No token saved.");
    setTokenInput("");
  }

  function forgetToken() {
    clearToken();
    setHasToken(false);
    setAuthNote("No token saved.");
  }

  async function refresh() {
    setError(null);
    try {
      await refreshAccessToken();
      setHasToken(true);
      setAuthNote("Access token refreshed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Token refresh failed");
    }
  }

  async function startSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const repo = repoId.trim();
    if (!repo) {
      setError("Enter a repository id (from the dashboard) to start a chat.");
      return;
    }
    setBusy(true);
    try {
      const session = await createChatSession(repo);
      setSessionId(session.session_id);
      setMessages([]);
      try {
        setSuggestions(await getSuggestions(repo));
      } catch {
        setSuggestions([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start chat session");
    } finally {
      setBusy(false);
    }
  }

  async function ask(question: string) {
    const content = question.trim();
    if (!content || !sessionId || busy) {
      return;
    }
    setError(null);
    setInput("");
    setBusy(true);
    setMessages((prev) => [
      ...prev,
      { role: "user", content },
      { role: "assistant", content: "", streaming: true }
    ]);

    const applyToLastAssistant = (update: (bubble: ChatBubble) => ChatBubble) => {
      setMessages((prev) => {
        const copy = [...prev];
        for (let i = copy.length - 1; i >= 0; i -= 1) {
          if (copy[i].role === "assistant") {
            copy[i] = update(copy[i]);
            break;
          }
        }
        return copy;
      });
    };

    try {
      await sendChatMessageStream(sessionId, content, 5, {
        onToken: (token) =>
          applyToLastAssistant((bubble) => ({ ...bubble, content: bubble.content + token })),
        onDone: (meta) =>
          applyToLastAssistant((bubble) => ({
            ...bubble,
            streaming: false,
            citations: meta.citations || [],
            noCitation: Boolean(meta.no_citation)
          }))
      });
    } catch (err) {
      applyToLastAssistant((bubble) => ({
        ...bubble,
        streaming: false,
        content: bubble.content || "(no answer returned)"
      }));
      setError(err instanceof Error ? err.message : "Chat request failed");
    } finally {
      setBusy(false);
    }
  }

  function onSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void ask(input);
  }

  return (
    <section className="grid">
      <article className="card">
        <h2>Workspace</h2>
        <p className="muted">
          Analyze a repo, open its dashboard, then chat with citation-grounded answers over the
          indexed code.
        </p>
        <div className="row">
          <Link href="/analyze">Analyze a repo</Link>
          <a href="/api/v1/auth/github?next=/workspace">Login with GitHub</a>
        </div>
      </article>

      <article className="card">
        <h3>Access</h3>
        <p className="muted">{authNote}</p>
        <div className="grid">
          <input
            className="input"
            placeholder="Paste bearer access token"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
          />
          <div className="row">
            <button type="button" className="button" onClick={saveToken}>
              Save token
            </button>
            <button type="button" className="button secondary" onClick={refresh}>
              Refresh token
            </button>
            {hasToken && (
              <button type="button" className="button secondary" onClick={forgetToken}>
                Clear
              </button>
            )}
          </div>
        </div>
      </article>

      <article className="card">
        <h3>Repository</h3>
        <form className="grid" onSubmit={startSession}>
          <label htmlFor="repo-id">Repository id</label>
          <input
            id="repo-id"
            className="input"
            placeholder="repo id from the dashboard"
            value={repoId}
            onChange={(e) => setRepoId(e.target.value)}
            required
          />
          <div className="row">
            <button type="submit" className="button" disabled={busy}>
              {sessionId ? "Restart chat" : "Start chat"}
            </button>
            {repoId.trim() && (
              <Link href={`/dashboard/${encodeURIComponent(repoId.trim())}`}>Open dashboard</Link>
            )}
          </div>
        </form>
      </article>

      {error && (
        <article className="error">
          <strong>Problem:</strong> {error}
        </article>
      )}

      {sessionId && (
        <article className="card">
          <h3>Chat</h3>
          {suggestions.length > 0 && messages.length === 0 && (
            <div className="suggestions">
              {suggestions.map((question) => (
                <button
                  key={question}
                  type="button"
                  className="suggestion"
                  onClick={() => void ask(question)}
                >
                  {question}
                </button>
              ))}
            </div>
          )}

          <div className="chat-log" ref={logRef}>
            {messages.map((bubble, index) => (
              <div key={index} className={`bubble ${bubble.role}`}>
                <div className="role">{bubble.role}</div>
                <div className={bubble.streaming ? "blink" : undefined}>{bubble.content}</div>
                {bubble.role === "assistant" && bubble.citations && bubble.citations.length > 0 && (
                  <div className="citations">
                    {bubble.citations.map((citation, cIndex) => (
                      <span key={cIndex} className="citation-pill mono">
                        {citationLabel(citation)}
                      </span>
                    ))}
                  </div>
                )}
                {bubble.role === "assistant" && !bubble.streaming && bubble.noCitation && (
                  <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
                    No exact citation anchor.
                  </div>
                )}
              </div>
            ))}
          </div>

          <form className="row" onSubmit={onSend} style={{ marginTop: 12 }}>
            <input
              className="input"
              placeholder="Ask about this repository..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              style={{ flex: 1 }}
            />
            <button type="submit" className="button" disabled={busy || !input.trim()}>
              {busy ? "..." : "Send"}
            </button>
          </form>
        </article>
      )}
    </section>
  );
}
