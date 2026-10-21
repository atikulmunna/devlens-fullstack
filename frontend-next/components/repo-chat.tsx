"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { SignInLink, useAuth } from "@/components/auth";
import { Answer } from "@/components/chat/answer";
import { Citations } from "@/components/chat/citations";
import { SessionList } from "@/components/chat/session-list";
import { useRepo } from "@/components/repo-context";
import {
  ChatCitation,
  ChatSessionDetail,
  ChatSessionSummary,
  createChatSession,
  getChatSession,
  getSuggestions,
  listChatSessions,
  sendChatMessageStream
} from "@/lib/api";
import { friendlyChatError, isAbort } from "@/lib/errors";

type ChatBubble = {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  stopped?: boolean;
  citations?: ChatCitation[];
  noCitation?: boolean;
  commitSha?: string | null;
};

type StoredCitations = { citations?: ChatCitation[]; no_citation?: boolean; commit_sha?: string | null };

// A stopped answer is never saved, so a question with no answer after it was stopped.
const UNANSWERED: ChatBubble = { role: "assistant", content: "", stopped: true };

function bubblesFrom(session: ChatSessionDetail): ChatBubble[] {
  const bubbles: ChatBubble[] = [];
  for (const message of session.messages ?? []) {
    if (message.role === "user" && bubbles.at(-1)?.role === "user") {
      bubbles.push(UNANSWERED);
    }
    const stored = (message.source_citations ?? {}) as StoredCitations;
    bubbles.push({
      role: message.role === "user" ? "user" : "assistant",
      content: message.content,
      citations: stored.citations ?? [],
      noCitation: Boolean(stored.no_citation),
      commitSha: stored.commit_sha ?? null
    });
  }
  if (bubbles.at(-1)?.role === "user") {
    bubbles.push(UNANSWERED);
  }
  return bubbles;
}

export function RepoChat() {
  const repo = useRepo();
  const { status } = useAuth();
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [messages, setMessages] = useState<ChatBubble[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<number | null>(null);
  const logRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const refreshSessions = useCallback(() => {
    listChatSessions(repo.repo_id)
      .then(setSessions)
      .catch(() => setSessions([]));
  }, [repo.repo_id]);

  useEffect(() => {
    if (status !== "signed-in") {
      return;
    }
    refreshSessions();
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
  }, [status, repo.repo_id, refreshSessions]);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [messages]);

  // Leaving the page stops an answer that is still streaming.
  useEffect(() => () => abortRef.current?.abort(), []);

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
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const id = await ensureSession();
      await sendChatMessageStream(
        id,
        content,
        5,
        {
          onToken: (token) => applyToLastAssistant((bubble) => ({ ...bubble, content: bubble.content + token })),
          onDone: (meta) =>
            applyToLastAssistant((bubble) => ({
              ...bubble,
              streaming: false,
              citations: meta.citations || [],
              noCitation: Boolean(meta.no_citation),
              commitSha: meta.commit_sha ?? null
            }))
        },
        controller.signal
      );
    } catch (err) {
      if (isAbort(err)) {
        applyToLastAssistant((bubble) => ({ ...bubble, streaming: false, stopped: true }));
      } else {
        // The failed question stays in the log; only the empty answer bubble goes.
        setMessages((prev) => prev.filter((bubble, index) => !(index === prev.length - 1 && !bubble.content)));
        setError(friendlyChatError(err));
      }
    } finally {
      abortRef.current = null;
      setBusy(false);
      refreshSessions();
    }
  }

  async function openSession(id: string) {
    if (busy || id === sessionId) {
      return;
    }
    setError(null);
    try {
      const session = await getChatSession(id);
      setSessionId(id);
      setMessages(bubblesFrom(session));
    } catch (err) {
      setError(friendlyChatError(err));
    }
  }

  function newChat() {
    setSessionId(null);
    setMessages([]);
    setError(null);
  }

  async function copy(index: number) {
    try {
      await navigator.clipboard.writeText(messages[index].content.trim());
      setCopied(index);
      window.setTimeout(() => setCopied((current) => (current === index ? null : current)), 2000);
    } catch {
      setError("Copying is blocked in this browser. Select the answer text to copy it.");
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
    <section className="chat-layout">
      <SessionList sessions={sessions} activeId={sessionId} disabled={busy} onSelect={(id) => void openSession(id)} onNew={newChat} />

      <div className="chat">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p className="muted">
              Ask how something works in {repo.full_name}. Answers name the files and lines they come from.
            </p>
            {suggestions.length > 0 && (
              <div className="suggestions">
                {suggestions.map((question) => (
                  <button key={question} type="button" className="suggestion" onClick={() => void ask(question)}>
                    {question}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.length > 0 && (
          <div className="chat-log" ref={logRef}>
            {messages.map((bubble, index) => {
              const links = { citations: bubble.citations ?? [], githubUrl: repo.github_url, commitSha: bubble.commitSha };
              return (
                <div key={index} className={`bubble ${bubble.role}`}>
                  <div className="role">{bubble.role === "user" ? "You" : "DevLens"}</div>
                  {bubble.role === "user" ? (
                    <div className="question">{bubble.content}</div>
                  ) : (
                    <div className={bubble.streaming ? "blink" : undefined}>
                      <Answer content={bubble.content} {...links} />
                    </div>
                  )}
                  {bubble.role === "assistant" && links.citations.length > 0 && <Citations {...links} />}
                  {bubble.role === "assistant" && !bubble.streaming && (
                    <div className="answer-foot">
                      {bubble.stopped && (
                        <span className="muted">{bubble.content ? "Stopped." : "Stopped before an answer was saved."}</span>
                      )}
                      {bubble.noCitation && !bubble.stopped && <span className="muted">No source lines matched this answer.</span>}
                      {bubble.content.trim() && (
                        <button type="button" className="link-button" onClick={() => void copy(index)}>
                          {copied === index ? "Copied" : "Copy answer"}
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
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
          {busy ? (
            <button type="button" className="button secondary" onClick={() => abortRef.current?.abort()}>
              Stop
            </button>
          ) : (
            <button type="submit" className="button" disabled={!input.trim()}>
              Ask
            </button>
          )}
        </form>
      </div>
    </section>
  );
}
