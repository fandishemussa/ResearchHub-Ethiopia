"use client";

import {
  BookOpen,
  Check,
  ChevronDown,
  Clipboard,
  Download,
  ExternalLink,
  MessageSquareText,
  Pencil,
  Printer,
  RefreshCw,
  Settings,
  SlidersHorizontal,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  Volume2,
  X,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { submitChatFeedback } from "@/lib/chat-api";
import {
  exportCurrentConversation,
  type ChatExportFormat,
} from "@/lib/chat-export";
import type {
  ChatSettings,
  ChatSource,
  ResearchChatMessage,
  ResearchMode,
} from "@/lib/chat-types";
import { safeHttpUrl } from "@/lib/urls";
import {
  useResearchChat,
  type InitialChatScope,
} from "@/hooks/useResearchChat";
import { cn } from "@/lib/utils";
import { ChatComposer, researchModes } from "./ChatComposer";
import {
  ConversationMenuButton,
  ConversationSidebar,
} from "./ConversationSidebar";
import { DocumentTypeBadge, GroundingBadge, SourceBadge } from "./Badges";
import { MarkdownContent } from "./MarkdownContent";
import { ResearchContextPanel } from "./ResearchContextPanel";

const stages = [
  "Searching repositories",
  "Retrieving document chunks",
  "Ranking evidence",
  "Generating grounded answer",
  "Verifying citations",
];

export function ResearchChatPage({
  initialScope,
}: {
  initialScope: InitialChatScope;
}) {
  const chat = useResearchChat(initialScope);
  const queryClient = useQueryClient();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const [historyCollapsed, setHistoryCollapsed] = useState(false);
  const [contextCollapsed, setContextCollapsed] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const historyIsDesktop = useMediaQuery("(min-width: 1024px)");
  const contextIsDesktop = useMediaQuery("(min-width: 1280px)");
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const messageEndRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    messageEndRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
    });
  }, [chat.messages, chat.isGenerating]);
  useEffect(() => {
    if (chat.sessionId) {
      void queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
    }
  }, [chat.messages.length, chat.sessionId, queryClient]);
  const suggestions = useMemo(() => modeSuggestions(chat.mode), [chat.mode]);
  const historyExpanded = historyIsDesktop ? !historyCollapsed : historyOpen;
  const contextExpanded = contextIsDesktop ? !contextCollapsed : contextOpen;
  function toggleHistory() {
    if (historyIsDesktop) {
      setHistoryCollapsed((collapsed) => !collapsed);
      setHistoryOpen(false);
      return;
    }
    setHistoryOpen(true);
  }
  function toggleContext() {
    if (contextIsDesktop) {
      setContextCollapsed((collapsed) => !collapsed);
      setContextOpen(false);
      return;
    }
    setContextOpen(true);
  }
  function clearConversation() {
    if (
      chat.messages.length &&
      !window.confirm(
        "Clear the current conversation view? The saved conversation remains in history until you delete it there.",
      )
    )
      return;
    chat.clear();
    window.setTimeout(() => composerRef.current?.focus(), 0);
  }
  return (
    <div className="-m-4 flex min-h-[calc(100vh-4rem)] bg-stone-50 dark:bg-stone-950 sm:-m-6 lg:-m-8">
      <ConversationSidebar
        open={historyOpen}
        desktopCollapsed={historyCollapsed}
        close={() => setHistoryOpen(false)}
        activeSessionId={chat.sessionId}
        newConversation={clearConversation}
        loadConversation={chat.loadConversation}
      />
      <section className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-16 z-30 border-b border-stone-200 bg-white/95 px-4 py-3 backdrop-blur dark:border-stone-800 dark:bg-stone-950/95">
          <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <ConversationMenuButton
                open={toggleHistory}
                expanded={historyExpanded}
              />
              <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-emerald-900 text-amber-300">
                <BookOpen size={20} />
              </span>
              <div className="min-w-0">
                <h1 className="truncate font-serif text-lg font-bold sm:text-xl">
                  ResearchHub AI Assistant
                </h1>
                <p className="hidden truncate text-xs text-stone-500 sm:block">
                  Ask questions across Ethiopian university research
                  repositories.
                </p>
              </div>
              {(initialScope.documentId || initialScope.publicationId) && (
                <span className="hidden rounded-full bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-900 md:inline">
                  Document scoped
                </span>
              )}
            </div>
            <div className="flex items-center gap-1">
              <span className="mr-1 hidden items-center gap-1 text-xs text-stone-500 sm:inline-flex">
                <span
                  className={cn(
                    "size-2 rounded-full",
                    chat.isGenerating
                      ? "animate-pulse bg-amber-500"
                      : chat.error
                        ? "bg-red-500"
                        : "bg-emerald-500",
                  )}
                />
                {chat.isGenerating
                  ? "Working"
                  : chat.error
                    ? "Needs attention"
                    : "Ready"}
              </span>
              <button
                type="button"
                onClick={() => window.print()}
                aria-label="Print conversation"
                className="toolbar-button"
              >
                <Printer size={17} />
              </button>
              <button
                type="button"
                onClick={toggleContext}
                aria-label={`${contextExpanded ? "Hide" : "Show"} source filters and research context`}
                aria-controls="research-context-panel"
                aria-expanded={contextExpanded}
                className="toolbar-button"
              >
                <SlidersHorizontal size={17} />
                <span className="hidden md:inline">Context</span>
              </button>
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setExportOpen((open) => !open)}
                  aria-label="Export current conversation"
                  className="toolbar-button"
                >
                  <Download size={17} />
                  <ChevronDown size={13} />
                </button>
                {exportOpen && (
                  <div className="absolute right-0 top-11 z-40 w-40 rounded-xl border border-stone-200 bg-white p-1 shadow-xl dark:border-stone-700 dark:bg-stone-900">
                    {(
                      [
                        "markdown",
                        "text",
                        "bibtex",
                        "ris",
                      ] as ChatExportFormat[]
                    ).map((format) => (
                      <button
                        key={format}
                        type="button"
                        disabled={!chat.messages.length}
                        onClick={() => {
                          exportCurrentConversation(chat.messages, format);
                          setExportOpen(false);
                        }}
                        className="block w-full rounded-lg px-3 py-2 text-left text-xs uppercase hover:bg-stone-100 disabled:opacity-40 dark:hover:bg-stone-800"
                      >
                        {format}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={() => setSettingsOpen(true)}
                aria-label="Open research settings"
                className="toolbar-button"
              >
                <Settings size={17} />
              </button>
              <button
                type="button"
                onClick={clearConversation}
                aria-label="Clear conversation"
                className="toolbar-button text-red-700"
              >
                <Trash2 size={17} />
                <span className="hidden lg:inline">Clear</span>
              </button>
            </div>
          </div>
        </header>

        <div
          className="flex-1 overflow-y-auto px-3 py-5 sm:px-6"
          aria-live="polite"
          aria-busy={chat.isGenerating}
        >
          <div className="mx-auto max-w-4xl space-y-6">
            {!chat.messages.length && !chat.isGenerating && (
              <EmptyChatState
                mode={chat.mode}
                setMode={chat.setMode}
                suggestions={suggestions}
                setDraft={(value) => {
                  chat.setDraft(value);
                  composerRef.current?.focus();
                }}
                scoped={Boolean(
                  initialScope.documentId || initialScope.publicationId,
                )}
                broaden={() => {
                  chat.setFilters({
                    ...chat.filters,
                    repositories: [],
                    universities: [],
                  });
                }}
              />
            )}
            {chat.messages.map((message, index) => (
              <ChatMessageView
                key={message.id}
                message={message}
                onCitation={chat.setSelectedCitation}
                setDraft={(value) => {
                  chat.setDraft(value);
                  composerRef.current?.focus();
                }}
                regenerate={() => {
                  const previous = [...chat.messages.slice(0, index)]
                    .reverse()
                    .find((item) => item.role === "user");
                  if (previous) void chat.send(previous.content);
                }}
              />
            ))}
            {chat.isGenerating && (
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-900 dark:bg-emerald-950/30">
                <div className="flex items-center gap-3">
                  <span className="size-4 animate-spin rounded-full border-2 border-emerald-700 border-t-transparent motion-reduce:animate-none" />
                  <div>
                    <p className="text-sm font-semibold">
                      {stages[chat.generationStage]}
                    </p>
                    <p className="text-xs text-stone-500">
                      Building a grounded answer without exposing private
                      reasoning.
                    </p>
                  </div>
                </div>
                <div className="mt-3 flex gap-1" aria-hidden>
                  {stages.map((_, index) => (
                    <span
                      key={index}
                      className={cn(
                        "h-1 flex-1 rounded",
                        index <= chat.generationStage
                          ? "bg-emerald-700"
                          : "bg-stone-200 dark:bg-stone-700",
                      )}
                    />
                  ))}
                </div>
              </div>
            )}
            {chat.error && (
              <div
                role="alert"
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200"
              >
                <span>{chat.error}</span>
                <button
                  type="button"
                  onClick={() => {
                    chat.setError(undefined);
                    const previous = [...chat.messages]
                      .reverse()
                      .find((item) => item.role === "user");
                    if (previous) void chat.send(previous.content);
                  }}
                  className="font-semibold underline"
                >
                  Retry
                </button>
              </div>
            )}
            <div ref={messageEndRef} />
          </div>
        </div>

        <ChatComposer
          draft={chat.draft}
          setDraft={chat.setDraft}
          mode={chat.mode}
          setMode={chat.setMode}
          isGenerating={chat.isGenerating}
          send={() => void chat.send()}
          stop={chat.stop}
          addAttachments={chat.addAttachments}
          attachments={chat.attachments}
          removeAttachment={chat.removeAttachment}
          inputRef={composerRef}
        />
      </section>
      <ResearchContextPanel
        open={contextOpen}
        desktopCollapsed={contextCollapsed}
        close={() => setContextOpen(false)}
        messages={chat.messages}
        filters={chat.filters}
        setFilters={chat.setFilters}
        attachments={chat.attachments}
        removeAttachment={chat.removeAttachment}
        excludedDocumentIds={chat.excludedDocumentIds}
        toggleDocument={chat.toggleDocument}
        pinnedChunkIds={chat.pinnedChunkIds}
        togglePinnedChunk={chat.togglePinnedChunk}
        selectCitation={chat.setSelectedCitation}
      />
      {settingsOpen && (
        <ChatSettingsDialog
          settings={chat.settings}
          setSettings={chat.setSettings}
          filters={chat.filters}
          setFilters={chat.setFilters}
          close={() => setSettingsOpen(false)}
        />
      )}
      {chat.selectedCitation && (
        <CitationPanel
          citation={chat.selectedCitation}
          close={() => chat.setSelectedCitation(undefined)}
        />
      )}
    </div>
  );
}

const ChatMessageView = memo(function ChatMessageView({
  message,
  onCitation,
  setDraft,
  regenerate,
}: {
  message: ResearchChatMessage;
  onCitation: (citation: ChatSource) => void;
  setDraft: (value: string) => void;
  regenerate: () => void;
}) {
  const [expanded, setExpanded] = useState(message.content.length < 1800);
  const assistant = message.role === "assistant";
  const shown = expanded
    ? message.content
    : `${message.content.slice(0, 1800)}…`;
  return (
    <article
      className={cn(
        "flex content-auto gap-3",
        assistant ? "justify-start" : "justify-end",
      )}
    >
      <div
        className={cn(
          "group max-w-[92%] rounded-2xl p-4 sm:max-w-[85%]",
          assistant
            ? "border border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900"
            : "bg-emerald-900 text-white",
        )}
      >
        <div className="mb-2 flex items-center justify-between gap-4 text-[11px] opacity-70">
          <span>
            {assistant
              ? "ResearchHub Assistant"
              : researchModes.find((item) => item.value === message.mode)
                  ?.label || "You"}
          </span>
          <time dateTime={message.createdAt}>
            {new Date(message.createdAt).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </time>
        </div>
        {assistant ? (
          <MarkdownContent
            content={shown}
            citations={message.citations}
            onCitation={onCitation}
          />
        ) : (
          <p className="whitespace-pre-wrap text-sm leading-6">
            {message.content}
          </p>
        )}
        {message.content.length >= 1800 && (
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="mt-3 text-xs font-semibold underline"
          >
            {expanded ? "Collapse response" : "Expand response"}
          </button>
        )}
        {assistant && message.grounding && (
          <div className="mt-4">
            <GroundingBadge status={message.grounding} />
            {message.grounding === "insufficient" && (
              <p className="mt-2 text-xs text-stone-500">
                I could not find enough evidence in the indexed research
                documents to answer this confidently.
              </p>
            )}
          </div>
        )}
        {assistant && message.citations.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {message.citations.map((citation) => (
              <button
                key={`${citation.index}-${citation.chunkId || citation.title}`}
                type="button"
                onClick={() => onCitation(citation)}
                className="rounded-lg border border-stone-200 px-2 py-1 text-xs hover:border-emerald-600 dark:border-stone-700"
              >
                [{citation.index}]{" "}
                {citation.title.length > 42
                  ? `${citation.title.slice(0, 42)}…`
                  : citation.title}
              </button>
            ))}
          </div>
        )}
        <div
          className={cn(
            "mt-4 flex flex-wrap items-center justify-between gap-3 border-t pt-3 text-xs",
            assistant
              ? "border-stone-200 text-stone-500 dark:border-stone-700"
              : "border-white/20 text-white/75",
          )}
        >
          <div>
            {assistant ? (
              <span>
                {message.grounding === "insufficient"
                  ? "No adequate grounding"
                  : [
                      `Grounded in ${message.retrievedDocumentCount ?? 0} documents`,
                      `${message.retrievedChunkCount ?? 0} excerpts`,
                      `${message.citations.length} citations`,
                      message.latencyMs == null
                        ? "response time unavailable"
                        : `${(message.latencyMs / 1000).toFixed(1)} s`,
                      message.modelName || "model unavailable",
                    ].join(" · ")}
              </span>
            ) : (
              <span>{message.mode?.replaceAll("_", " ")}</span>
            )}
          </div>
          <div className="flex gap-1">
            <IconButton
              label="Copy message"
              onClick={() =>
                void navigator.clipboard.writeText(message.content)
              }
            >
              <Clipboard size={14} />
            </IconButton>
            {assistant ? (
              <>
                <IconButton label="Regenerate response" onClick={regenerate}>
                  <RefreshCw size={14} />
                </IconButton>
                <IconButton
                  label="Read response aloud"
                  onClick={() => {
                    if ("speechSynthesis" in window) {
                      window.speechSynthesis.cancel();
                      window.speechSynthesis.speak(
                        new SpeechSynthesisUtterance(message.content),
                      );
                    }
                  }}
                >
                  <Volume2 size={14} />
                </IconButton>
                <IconButton
                  label="Helpful answer"
                  onClick={() => void submitChatFeedback(message.id, "helpful")}
                >
                  <ThumbsUp size={14} />
                </IconButton>
                <IconButton
                  label="Not helpful answer"
                  onClick={() =>
                    void submitChatFeedback(message.id, "not_helpful")
                  }
                >
                  <ThumbsDown size={14} />
                </IconButton>
              </>
            ) : (
              <IconButton
                label="Edit and resend"
                onClick={() => setDraft(message.content)}
              >
                <Pencil size={14} />
              </IconButton>
            )}
          </div>
        </div>
        {assistant &&
          message.warnings?.map((warning, index) => (
            <p
              key={index}
              className="mt-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200"
            >
              {warning}
            </p>
          ))}
        {assistant &&
          message.followUpQuestions &&
          message.followUpQuestions.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-bold uppercase tracking-wider text-stone-500">
                Continue exploring
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {message.followUpQuestions.map((question) => (
                  <button
                    key={question}
                    type="button"
                    onClick={() => setDraft(question)}
                    className="rounded-full border border-emerald-200 px-3 py-1.5 text-left text-xs text-emerald-800 hover:bg-emerald-50 dark:border-emerald-900 dark:text-emerald-200 dark:hover:bg-emerald-950"
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          )}
      </div>
    </article>
  );
});

function EmptyChatState({
  mode,
  setMode,
  suggestions,
  setDraft,
  scoped,
  broaden,
}: {
  mode: ResearchMode;
  setMode: (mode: ResearchMode) => void;
  suggestions: string[];
  setDraft: (value: string) => void;
  scoped: boolean;
  broaden: () => void;
}) {
  return (
    <div className="py-8 text-center sm:py-14">
      <span className="mx-auto grid size-16 place-items-center rounded-2xl bg-emerald-900 text-amber-300">
        <MessageSquareText size={30} />
      </span>
      <h2 className="mt-5 font-serif text-2xl font-bold">
        Explore Ethiopian research
      </h2>
      <p className="mx-auto mt-2 max-w-xl text-sm text-stone-500">
        Ask grounded questions across indexed theses, dissertations, articles,
        and full-text research documents.
      </p>
      {scoped && (
        <button
          type="button"
          onClick={broaden}
          className="mt-3 text-sm font-semibold text-emerald-700 underline"
        >
          Broaden search to all repositories
        </button>
      )}
      <div className="mx-auto mt-6 flex max-w-2xl flex-wrap justify-center gap-2">
        {researchModes.map((item) => (
          <button
            key={item.value}
            type="button"
            onClick={() => setMode(item.value)}
            aria-pressed={mode === item.value}
            className={cn(
              "rounded-full border px-3 py-2 text-xs font-semibold",
              mode === item.value
                ? "border-emerald-800 bg-emerald-800 text-white"
                : "border-stone-200 bg-white dark:border-stone-700 dark:bg-stone-900",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="mx-auto mt-7 grid max-w-3xl gap-3 sm:grid-cols-2">
        {suggestions.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            onClick={() => setDraft(suggestion)}
            className="rounded-2xl border border-stone-200 bg-white p-4 text-left text-sm leading-5 hover:border-emerald-600 hover:shadow-sm dark:border-stone-800 dark:bg-stone-900"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}

function CitationPanel({
  citation,
  close,
}: {
  citation: ChatSource;
  close: () => void;
}) {
  const external =
    safeHttpUrl(citation.documentUrl) || safeHttpUrl(citation.landingUrl);
  const preview =
    citation.previewUrl ||
    (citation.documentId
      ? `/documents/${encodeURIComponent(citation.documentId)}${citation.pageStart ? `?page=${citation.pageStart}` : ""}`
      : undefined);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => event.key === "Escape" && close();
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [close]);
  return (
    <div
      className="fixed inset-0 z-[70] grid place-items-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="citation-title"
    >
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl dark:bg-stone-900">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap gap-2">
              <SourceBadge code={citation.sourceCode || citation.repository} />
              <DocumentTypeBadge type={citation.documentType} />
            </div>
            <h2
              id="citation-title"
              className="mt-3 font-serif text-xl font-bold"
            >
              [{citation.index}] {citation.title}
            </h2>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label="Close citation details"
            className="grid size-10 place-items-center rounded-lg hover:bg-stone-100 dark:hover:bg-stone-800"
          >
            <X />
          </button>
        </div>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <Detail
            label="Authors"
            value={citation.authors.join(", ") || "Not reported"}
          />
          <Detail
            label="University"
            value={citation.university || "Not reported"}
          />
          <Detail
            label="Repository"
            value={citation.repository || citation.sourceCode || "Not reported"}
          />
          <Detail
            label="Year"
            value={citation.year?.toString() || "Not reported"}
          />
          <Detail
            label="Pages"
            value={
              citation.pageStart
                ? citation.pageEnd && citation.pageEnd !== citation.pageStart
                  ? `${citation.pageStart}–${citation.pageEnd}`
                  : `${citation.pageStart}`
                : "Unavailable"
            }
          />
          <Detail
            label="Relevance"
            value={
              citation.similarity !== undefined
                ? `${(citation.similarity * 100).toFixed(0)}%`
                : "Unavailable"
            }
          />
          <Detail
            label="Document ID"
            value={citation.documentId || "Unavailable"}
          />
          <Detail
            label="Publication ID"
            value={citation.publicationId || "Unavailable"}
          />
          <Detail label="Chunk ID" value={citation.chunkId || "Unavailable"} />
          <Detail label="Retrieval rank" value={String(citation.index)} />
        </dl>
        <div className="mt-5 rounded-xl bg-stone-50 p-4 dark:bg-stone-800">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-500">
            Retrieved excerpt
          </p>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-6">
            {citation.excerpt || "Citation excerpt is unavailable."}
          </p>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          {external && (
            <a
              href={external}
              target="_blank"
              rel="noopener noreferrer"
              className="toolbar-button bg-emerald-800 text-white"
            >
              Open source <ExternalLink size={14} />
            </a>
          )}
          {preview && (
            <a
              href={preview}
              target="_blank"
              rel="noopener noreferrer"
              className="toolbar-button"
            >
              Show in document <BookOpen size={14} />
              <span className="sr-only"> opens in a new tab</span>
            </a>
          )}
          <button
            type="button"
            onClick={() =>
              void navigator.clipboard.writeText(
                `${citation.authors.join(", ")} (${citation.year || "n.d."}). ${citation.title}.`,
              )
            }
            className="toolbar-button"
          >
            <Clipboard size={14} /> Copy citation
          </button>
          {citation.excerpt && (
            <button
              type="button"
              onClick={() =>
                void navigator.clipboard.writeText(citation.excerpt || "")
              }
              className="toolbar-button"
            >
              <Clipboard size={14} /> Copy excerpt
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function ChatSettingsDialog({
  settings,
  setSettings,
  filters,
  setFilters,
  close,
}: {
  settings: ChatSettings;
  setSettings: (settings: ChatSettings) => void;
  filters: ReturnType<typeof useResearchChat>["filters"];
  setFilters: ReturnType<typeof useResearchChat>["setFilters"];
  close: () => void;
}) {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => event.key === "Escape" && close();
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [close]);
  return (
    <div
      className="fixed inset-0 z-[70] grid place-items-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-title"
    >
      <div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl dark:bg-stone-900">
        <div className="flex items-center justify-between">
          <h2 id="settings-title" className="font-serif text-xl font-bold">
            Advanced research settings
          </h2>
          <button
            type="button"
            onClick={close}
            aria-label="Close settings"
            className="grid size-10 place-items-center"
          >
            <X />
          </button>
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <Range
            label="Top documents"
            value={filters.topDocuments}
            min={2}
            max={10}
            step={1}
            onChange={(topDocuments) =>
              setFilters({ ...filters, topDocuments })
            }
          />
          <Range
            label="Top chunks"
            value={filters.topChunks}
            min={3}
            max={30}
            step={1}
            onChange={(topChunks) => setFilters({ ...filters, topChunks })}
          />
          <Range
            label="Minimum similarity"
            value={filters.minimumSimilarity}
            min={0.1}
            max={0.9}
            step={0.05}
            onChange={(minimumSimilarity) =>
              setFilters({ ...filters, minimumSimilarity })
            }
          />
          <SelectSetting
            label="Citation strictness"
            value={settings.citationStrictness}
            options={["high", "balanced"]}
            onChange={(citationStrictness) =>
              setSettings({
                ...settings,
                citationStrictness:
                  citationStrictness as ChatSettings["citationStrictness"],
              })
            }
          />
          <SelectSetting
            label="Answer length"
            value={settings.answerLength}
            options={["concise", "balanced", "detailed"]}
            onChange={(answerLength) =>
              setSettings({
                ...settings,
                answerLength: answerLength as ChatSettings["answerLength"],
              })
            }
          />
          <SelectSetting
            label="Response language"
            value={settings.responseLanguage}
            options={["English", "Amharic", "Afaan Oromo"]}
            onChange={(responseLanguage) =>
              setSettings({ ...settings, responseLanguage })
            }
          />
        </div>
        <div className="mt-5 space-y-3">
          {(
            [
              ["hybridSearch", "Hybrid search"],
              ["reranking", "Rerank evidence"],
              ["includeFullText", "Include full-text chunks"],
              ["includeMetadata", "Include metadata-only results"],
            ] as const
          ).map(([key, label]) => (
            <label
              key={key}
              className="flex items-center justify-between text-sm"
            >
              <span>{label}</span>
              <input
                type="checkbox"
                checked={settings[key]}
                onChange={(event) =>
                  setSettings({ ...settings, [key]: event.target.checked })
                }
              />
            </label>
          ))}
        </div>
        <button
          type="button"
          onClick={close}
          className="mt-6 inline-flex h-10 items-center gap-2 rounded-lg bg-emerald-800 px-4 text-sm font-semibold text-white"
        >
          <Check size={16} /> Apply settings
        </button>
      </div>
    </div>
  );
}

function IconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="grid size-8 place-items-center rounded-lg hover:bg-black/5 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:hover:bg-white/10"
    >
      {children}
    </button>
  );
}
function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-bold uppercase tracking-wider text-stone-500">
        {label}
      </dt>
      <dd className="mt-1">{value}</dd>
    </div>
  );
}
function Range({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="text-sm font-semibold">
      {label}: {value}
      <input
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-2 w-full"
      />
    </label>
  );
}
function SelectSetting({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="text-sm font-semibold">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-lg border border-stone-300 bg-transparent px-3 py-2 font-normal capitalize dark:border-stone-700"
      >
        {options.map((option) => (
          <option key={option}>{option}</option>
        ))}
      </select>
    </label>
  );
}

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(query);
    const update = () => setMatches(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [query]);

  return matches;
}

function modeSuggestions(mode: ResearchMode): string[] {
  const common = [
    "Find studies related to machine learning in Ethiopian universities.",
    "Explain the service quality gaps identified in this research.",
  ];
  const modes: Record<ResearchMode, string[]> = {
    ask: ["What methodologies were used in these theses?", ...common],
    summarize: [
      "Summarize the main findings of this study.",
      "Summarize the methodology and limitations of the strongest matching thesis.",
      ...common,
    ],
    compare: [
      "Compare research on agricultural postharvest loss.",
      "Compare the methods, samples, and findings of the top three studies.",
      ...common,
    ],
    methodology: [
      "What methodologies were used in these theses?",
      "Extract the study design, sample, instruments, and analysis methods.",
      ...common,
    ],
    evidence: [
      "Show the evidence supporting the main conclusion.",
      "Find page-level evidence about the reported research gap.",
      ...common,
    ],
    literature_review: [
      "Create a literature review of agricultural postharvest loss research.",
      "Identify themes, contradictions, methods, and research gaps.",
      ...common,
    ],
    citation: [
      "Generate an APA citation for this publication.",
      "Generate references for the retrieved studies.",
      ...common,
    ],
    explain: [
      "Explain the service quality gaps identified in this research.",
      "Explain the findings in plain language and cite the evidence.",
      ...common,
    ],
  };
  return modes[mode].slice(0, 6);
}
