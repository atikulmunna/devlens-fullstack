"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { SignInLink, useAuth } from "@/components/auth";
import { useRepo } from "@/components/repo-context";
import { ChatCitation, createChatSession, getSuggestions, sendChatMessageStream } from "@/lib/api";

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

export function RepoChat() {
  const repo = useRepo();
  const { status } = useAuth();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [messages, setMessages] = useState<ChatBubble[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (status !== "signed-in") {
      return;
    }
    let cancelled = false;
    getSuggestions(repo.repo_id)
      .then((items) => {
        if (!cancelled) {
          setSuggestions(items);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSuggestions([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [status, repo.repo_id]);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [messages]);

  // The chat session is created on the first question, so there is no separate "start" step.
  async function ensureSession(): Promise<string> {
    if (sessionId) {
      return sessionId;
    }
    const session = await createChatSession(repo.repo_id);
    setSessionId(session.session_id);
    return session.session_id;
  }

  function applyToLastAssistant(update: (bubble: ChatBubble) => ChatBubble) {
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
  }

  async function ask(question: string) {
    const content = question.trim();
    if (!content || busy) {
      return;
    }
    setError(null);
    setInput("");
    setBusy(true);
    setMessages((prev) => [...prev, { role: "user", content }, { role: "assistant", content: "", streaming: true }]);
    try {
      const id = await ensureSession();
      await sendChatMessageStream(id, content, 5, {
        onToken: (token) => applyToLastAssistant((bubble) => ({ ...bubble, content: bubble.content + token })),
        onDone: (meta) =>
          applyToLastAssistant((bubble) => ({
            ...bubble,
            streaming: false,
            citations: meta.citations || [],
            noCitation: Boolean(meta.no_citation)
          }))
      });
    } catch (err) {
      applyToLastAssistant((bubble) => ({ ...bubble, streaming: false, content: bubble.content || "(no answer)" }));
      setError(err instanceof Error ? err.message : "The question could not be answered");
    } finally {
      setBusy(false);
    }
  }

  function onSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void ask(input);
  }

  if (status === "loading") {
    return <p className="notice">Checking sign-in...</p>;
  }
  if (status === "signed-out") {
    return (
      <article className="card">
        <h2>Sign in to ask about {repo.full_name}</h2>
        <p className="muted">Chat uses your GitHub sign-in. You will come back to this page afterwards.</p>
        <SignInLink>Sign in with GitHub</SignInLink>
      </article>
    );
  }

  return (
    <section className="chat">
      {suggestions.length > 0 && messages.length === 0 && (
        <div className="suggestions">
          {suggestions.map((question) => (
            <button key={question} type="button" className="suggestion" onClick={() => void ask(question)}>
              {question}
            </button>
          ))}
        </div>
      )}

      {messages.length > 0 && (
        <div className="chat-log" ref={logRef}>
          {messages.map((bubble, index) => (
            <div key={index} className={`bubble ${bubble.role}`}>
              <div className="role">{bubble.role === "user" ? "You" : "DevLens"}</div>
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
                <div className="no-citation">No source lines matched this answer.</div>
              )}
            </div>
          ))}
        </div>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <form className="chat-form" onSubmit={onSend}>
        <input
          className="input"
          aria-label={`Ask about ${repo.full_name}`}
          placeholder={`Ask how something works in ${repo.full_name}`}
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit" className="button" disabled={busy || !input.trim()}>
          {busy ? "Answering..." : "Ask"}
        </button>
      </form>
    </section>
  );
}
