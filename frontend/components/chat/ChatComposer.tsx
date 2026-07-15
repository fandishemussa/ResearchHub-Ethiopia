"use client";

import { FilePlus2, Send, Square } from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
  type RefObject,
} from "react";
import type { ResearchMode, WorkspaceAttachment } from "@/lib/chat-types";

export const researchModes: Array<{ value: ResearchMode; label: string }> = [
  { value: "ask", label: "Ask" },
  { value: "summarize", label: "Summarize" },
  { value: "compare", label: "Compare studies" },
  { value: "methodology", label: "Extract methodology" },
  { value: "evidence", label: "Find evidence" },
  { value: "literature_review", label: "Literature review" },
  { value: "citation", label: "Generate citation" },
  { value: "explain", label: "Explain findings" },
];

export function ChatComposer({
  draft,
  setDraft,
  mode,
  setMode,
  isGenerating,
  send,
  stop,
  addAttachments,
  attachments,
  removeAttachment,
  inputRef,
}: {
  draft: string;
  setDraft: (value: string) => void;
  mode: ResearchMode;
  setMode: (mode: ResearchMode) => void;
  isGenerating: boolean;
  send: () => void;
  stop: () => void;
  addAttachments: (files: FileList | File[]) => void;
  attachments: WorkspaceAttachment[];
  removeAttachment: (id: string) => void;
  inputRef: RefObject<HTMLTextAreaElement | null>;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  useEffect(() => {
    const element = inputRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 180)}px`;
  }, [draft, inputRef]);
  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  }
  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length)
      addAttachments(event.dataTransfer.files);
  }
  function paste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const files = Array.from(event.clipboardData.files);
    if (files.length) addAttachments(files);
  }
  return (
    <div className="sticky bottom-0 z-20 border-t border-stone-200 bg-stone-50/95 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur dark:border-stone-800 dark:bg-stone-950/95">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
        className={`mx-auto max-w-4xl rounded-2xl border bg-white p-2 shadow-lg dark:bg-stone-900 ${dragging ? "border-emerald-600 ring-2 ring-emerald-200" : "border-stone-300 dark:border-stone-700"}`}
      >
        {attachments.length > 0 && (
          <div
            className="flex flex-wrap gap-2 p-2"
            aria-label="Temporary attachments"
          >
            {attachments.map((item) => (
              <span
                key={item.id}
                className="inline-flex items-center gap-2 rounded-lg bg-stone-100 px-2 py-1 text-xs dark:bg-stone-800"
              >
                <span className="max-w-40 truncate">{item.file.name}</span>
                <span
                  className={
                    item.status === "ready"
                      ? "text-emerald-700"
                      : "text-red-700"
                  }
                >
                  {item.status === "too-large" ? "Too large" : item.status}
                </span>
                <button
                  type="button"
                  onClick={() => removeAttachment(item.id)}
                  aria-label={`Remove ${item.file.name}`}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
        <textarea
          ref={inputRef}
          value={draft}
          maxLength={4000}
          rows={1}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={keyDown}
          onPaste={paste}
          aria-label="Research question"
          placeholder="Ask about a thesis, methodology, research finding, university, author, or topic…"
          className="max-h-44 min-h-12 w-full resize-none bg-transparent px-3 py-2 text-sm outline-none placeholder:text-stone-400 focus-visible:ring-0"
        />
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-stone-100 px-2 pt-2 dark:border-stone-800">
          <div className="flex items-center gap-2">
            <select
              value={mode}
              onChange={(event) => setMode(event.target.value as ResearchMode)}
              aria-label="Research mode"
              className="h-10 max-w-44 rounded-lg border border-stone-200 bg-transparent px-2 text-xs dark:border-stone-700"
            >
              {researchModes.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
            <input
              ref={fileRef}
              type="file"
              multiple
              accept=".pdf,.txt,.md,.docx,application/pdf,text/plain"
              className="sr-only"
              onChange={(event) =>
                event.target.files && addAttachments(event.target.files)
              }
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              aria-label="Attach research files"
              className="grid size-10 place-items-center rounded-lg hover:bg-stone-100 focus:outline-none focus:ring-2 focus:ring-emerald-600 dark:hover:bg-stone-800"
            >
              <FilePlus2 size={18} />
            </button>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-stone-400" aria-live="polite">
              {draft.length}/4000
            </span>
            {isGenerating ? (
              <button
                type="button"
                onClick={stop}
                aria-label="Stop generation"
                className="inline-flex h-10 items-center gap-2 rounded-xl bg-red-700 px-3 text-sm font-semibold text-white"
              >
                <Square size={15} /> Stop
              </button>
            ) : (
              <button
                type="button"
                onClick={send}
                disabled={!draft.trim()}
                aria-label="Send question"
                className="inline-flex h-10 items-center gap-2 rounded-xl bg-emerald-800 px-3 text-sm font-semibold text-white disabled:opacity-40"
              >
                <Send size={16} /> Send
              </button>
            )}
          </div>
        </div>
      </div>
      <p className="mx-auto mt-2 max-w-4xl text-center text-[11px] text-stone-400">
        Enter sends · Shift+Enter adds a line · Answers should be verified
        against cited research
      </p>
    </div>
  );
}
