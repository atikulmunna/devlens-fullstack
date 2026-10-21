import type { ChatSessionSummary } from "@/lib/api";
import { plural } from "@/lib/format";

type Props = {
  sessions: ChatSessionSummary[];
  activeId: string | null;
  disabled: boolean;
  onSelect: (sessionId: string) => void;
  onNew: () => void;
};

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// Earlier chats about this repository, newest first, titled by the question that opened them.
export function SessionList({ sessions, activeId, disabled, onSelect, onNew }: Props) {
  return (
    <nav className="chat-sessions" aria-label="Chats about this repository">
      <div className="chat-sessions-head">
        <h2>Chats</h2>
        <button type="button" className="button secondary" onClick={onNew} disabled={disabled}>
          New chat
        </button>
      </div>
      {sessions.length === 0 ? (
        <p className="muted">Your chats about this repository will be listed here.</p>
      ) : (
        <ul>
          {sessions.map((session) => (
            <li key={session.id}>
              <button
                type="button"
                className="session-item"
                aria-current={session.id === activeId ? "true" : undefined}
                onClick={() => onSelect(session.id)}
                disabled={disabled}
              >
                <span className="session-title">{session.first_question || "A chat with no questions yet"}</span>
                <span className="session-meta">
                  {plural(session.message_count ?? 0, "message")}, {shortDate(session.created_at)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </nav>
  );
}
