"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { streamAgent } from "@/lib/agent-client";

type Part = { type: "text"; text: string } | { type: "tool"; name: string };

interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  parts: Part[];
  error?: string;
  pending?: boolean;
}

const STARTERS = [
  "What is … called here?",
  "Critique this instruction: …",
  "Quiz me on this page's terms",
];

let nextId = 1;

// The language-calibration coach, docked bottom-right. Mounted in the
// register layout so the conversation survives navigation within a register.
export default function AgentPanel({
  corpus,
  register,
  title,
}: {
  corpus: string;
  register: string;
  title: string;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const sessionRef = useRef<string | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);
  const lastSentRef = useRef<string>("");
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  function patchLast(patch: (m: ChatMessage) => ChatMessage) {
    setMessages((ms) =>
      ms.length === 0 ? ms : [...ms.slice(0, -1), patch(ms[ms.length - 1])],
    );
  }

  async function run(text: string, isRetry: boolean) {
    lastSentRef.current = text;
    setBusy(true);
    setMessages((ms) => {
      const next = [...ms];
      // A retry replaces the failed assistant bubble instead of stacking one.
      if (isRetry && next[next.length - 1]?.role === "assistant") next.pop();
      if (!isRetry) {
        next.push({
          id: nextId++,
          role: "user",
          parts: [{ type: "text", text }],
        });
      }
      next.push({ id: nextId++, role: "assistant", parts: [], pending: true });
      return next;
    });

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const events = streamAgent(
        {
          corpus,
          register,
          message: text,
          sessionId: sessionRef.current,
          pathname,
        },
        controller.signal,
      );
      for await (const event of events) {
        if (event.kind === "init" || event.kind === "done") {
          sessionRef.current = event.sessionId;
        } else if (event.kind === "delta") {
          patchLast((m) => {
            const parts = [...m.parts];
            const last = parts[parts.length - 1];
            if (last?.type === "text") {
              parts[parts.length - 1] = {
                type: "text",
                text: last.text + event.text,
              };
            } else {
              parts.push({ type: "text", text: event.text });
            }
            return { ...m, parts };
          });
        } else if (event.kind === "tool") {
          patchLast((m) => ({
            ...m,
            parts: [...m.parts, { type: "tool", name: event.name }],
          }));
        } else if (event.kind === "error") {
          patchLast((m) => ({ ...m, error: event.message }));
        }
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        const message = err instanceof Error ? err.message : String(err);
        patchLast((m) => ({ ...m, error: message }));
      }
    } finally {
      abortRef.current = null;
      patchLast((m) => ({ ...m, pending: false }));
      setBusy(false);
    }
  }

  function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    void run(text, false);
  }

  if (!open) {
    return (
      <button
        className="agent-pill"
        onClick={() => setOpen(true)}
        title={`Language coach for ${title} (${corpus}/${register})`}
      >
        coach
      </button>
    );
  }

  return (
    <section className="agent-panel" aria-label="Language coach">
      <header className="agent-header">
        <span className="agent-title">
          coach <span className="muted">· {corpus}/{register}</span>
        </span>
        <button className="agent-close" onClick={() => setOpen(false)}>
          &times;
        </button>
      </header>

      <div className="agent-messages" ref={listRef}>
        {messages.length === 0 && (
          <div className="agent-starters">
            <p className="muted">
              Train your articulation in this corpus&apos;s own terms.
            </p>
            {STARTERS.map((s) => (
              <button
                key={s}
                className="agent-starter"
                onClick={() => {
                  setInput(s);
                  inputRef.current?.focus();
                }}
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`agent-msg ${m.role}`}>
            {m.parts.map((p, i) =>
              p.type === "tool" ? (
                <span key={i} className="agent-tool-chip">
                  {p.name}
                </span>
              ) : m.role === "assistant" ? (
                <div key={i} className="agent-md">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {p.text}
                  </ReactMarkdown>
                </div>
              ) : (
                <div key={i} className="agent-user-text">
                  {p.text}
                </div>
              ),
            )}
            {m.pending && m.parts.length === 0 && !m.error && (
              <span className="muted agent-thinking">thinking…</span>
            )}
            {m.error && (
              <div className="agent-error">
                <span>{m.error}</span>
                {!busy && (
                  <button
                    className="agent-retry"
                    onClick={() => void run(lastSentRef.current, true)}
                  >
                    Retry
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <footer className="agent-composer">
        <textarea
          ref={inputRef}
          value={input}
          rows={2}
          placeholder="Ask the coach… (Enter to send, Shift+Enter for newline)"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
        {busy ? (
          <button
            className="agent-stop"
            onClick={() => abortRef.current?.abort()}
          >
            Stop
          </button>
        ) : (
          <button
            className="agent-send"
            onClick={send}
            disabled={!input.trim()}
          >
            Send
          </button>
        )}
      </footer>
    </section>
  );
}
