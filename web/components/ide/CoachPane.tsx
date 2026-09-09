"use client";

import { useEffect, useImperativeHandle, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { streamAgent } from "@/lib/agent-client";
import type { WorkspaceRegister } from "@/lib/workspace-types";

type Part = { type: "text"; text: string } | { type: "tool"; name: string };

interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  parts: Part[];
  error?: string;
  pending?: boolean;
}

interface Conversation {
  messages: ChatMessage[];
  busy: boolean;
  lastSent: string;
}

export interface CoachHandle {
  focus(): void;
}

const EMPTY_CONVO: Conversation = { messages: [], busy: false, lastSent: "" };

const STARTERS = [
  "What is … called here?",
  "Critique this instruction: …",
  "Quiz me on this page's terms",
];

let nextId = 1;

// The language-calibration coach, docked as the shell's right pane. Stays
// mounted (hidden via CSS when closed) so conversations survive both panel
// toggles and navigation; one conversation per register key.
export default function CoachPane({
  reg,
  onClose,
  ref,
}: {
  reg: WorkspaceRegister | null;
  onClose: () => void;
  ref?: React.Ref<CoachHandle>;
}) {
  const pathname = usePathname();
  const [convos, setConvos] = useState<Record<string, Conversation>>({});
  const [input, setInput] = useState("");
  const sessions = useRef(new Map<string, string>());
  const aborts = useRef(new Map<string, AbortController>());
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const convo = reg ? (convos[reg.key] ?? EMPTY_CONVO) : null;

  useImperativeHandle(ref, () => ({
    focus: () => inputRef.current?.focus(),
  }));

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [convo?.messages]);

  function mutate(key: string, fn: (c: Conversation) => Conversation) {
    setConvos((cs) => ({ ...cs, [key]: fn(cs[key] ?? EMPTY_CONVO) }));
  }

  function patchLast(key: string, fn: (m: ChatMessage) => ChatMessage) {
    mutate(key, (c) =>
      c.messages.length === 0
        ? c
        : {
            ...c,
            messages: [
              ...c.messages.slice(0, -1),
              fn(c.messages[c.messages.length - 1]),
            ],
          },
    );
  }

  async function run(r: WorkspaceRegister, text: string, isRetry: boolean) {
    const key = r.key;
    mutate(key, (c) => {
      const messages = [...c.messages];
      // A retry replaces the failed assistant bubble instead of stacking one.
      if (isRetry && messages[messages.length - 1]?.role === "assistant") {
        messages.pop();
      }
      if (!isRetry) {
        messages.push({
          id: nextId++,
          role: "user",
          parts: [{ type: "text", text }],
        });
      }
      messages.push({ id: nextId++, role: "assistant", parts: [], pending: true });
      return { ...c, messages, busy: true, lastSent: text };
    });

    const controller = new AbortController();
    aborts.current.set(key, controller);
    try {
      const events = streamAgent(
        {
          corpus: r.corpus,
          register: r.register,
          message: text,
          sessionId: sessions.current.get(key),
          pathname,
        },
        controller.signal,
      );
      for await (const event of events) {
        if (event.kind === "init" || event.kind === "done") {
          sessions.current.set(key, event.sessionId);
        } else if (event.kind === "delta") {
          patchLast(key, (m) => {
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
          patchLast(key, (m) => ({
            ...m,
            parts: [...m.parts, { type: "tool", name: event.name }],
          }));
        } else if (event.kind === "error") {
          patchLast(key, (m) => ({ ...m, error: event.message }));
        }
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        const message = err instanceof Error ? err.message : String(err);
        patchLast(key, (m) => ({ ...m, error: message }));
      }
    } finally {
      aborts.current.delete(key);
      patchLast(key, (m) => ({ ...m, pending: false }));
      mutate(key, (c) => ({ ...c, busy: false }));
    }
  }

  function send() {
    const text = input.trim();
    if (!text || !reg || convo?.busy) return;
    setInput("");
    void run(reg, text, false);
  }

  return (
    <div className="coach" aria-label="Language coach">
      <header className="pane-head">
        <span className="pane-title">
          coach
          {reg && <span className="pane-title-meta"> · {reg.key}</span>}
        </span>
        <button className="pane-x" onClick={onClose} title="Close panel (⌘J)">
          ×
        </button>
      </header>

      {!reg ? (
        <p className="coach-empty muted">
          Open a corpus register to talk to its coach.
        </p>
      ) : (
        <>
          <div className="coach-messages" ref={listRef}>
            {convo!.messages.length === 0 && (
              <div className="coach-starters">
                <p className="muted">
                  Train your articulation in this corpus&apos;s own terms.
                </p>
                {STARTERS.map((s) => (
                  <button
                    key={s}
                    className="coach-starter"
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
            {convo!.messages.map((m) => (
              <div key={m.id} className={`coach-msg ${m.role}`}>
                {m.parts.map((p, i) =>
                  p.type === "tool" ? (
                    <span key={i} className="coach-tool-chip">
                      {p.name}
                    </span>
                  ) : m.role === "assistant" ? (
                    <div key={i} className="coach-md">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {p.text}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <div key={i} className="coach-user-text">
                      {p.text}
                    </div>
                  ),
                )}
                {m.pending && m.parts.length === 0 && !m.error && (
                  <span className="muted coach-thinking">thinking…</span>
                )}
                {m.error && (
                  <div className="coach-error">
                    <span>{m.error}</span>
                    {!convo!.busy && (
                      <button
                        className="coach-retry"
                        onClick={() => void run(reg, convo!.lastSent, true)}
                      >
                        Retry
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          <footer className="coach-composer">
            <textarea
              ref={inputRef}
              value={input}
              rows={2}
              placeholder="Ask the coach… (Enter to send)"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                } else if (e.key === "Escape") {
                  e.currentTarget.blur();
                }
              }}
            />
            {convo!.busy ? (
              <button
                className="coach-stop"
                onClick={() => aborts.current.get(reg.key)?.abort()}
              >
                Stop
              </button>
            ) : (
              <button
                className="coach-send"
                onClick={send}
                disabled={!input.trim()}
              >
                Send
              </button>
            )}
          </footer>
        </>
      )}
    </div>
  );
}
