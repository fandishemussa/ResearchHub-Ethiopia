"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, FileText, Filter, Paperclip, Pin, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type {
  ChatFilters,
  ChatSource,
  ResearchChatMessage,
  WorkspaceAttachment,
} from "@/lib/chat-types";
import { cn } from "@/lib/utils";
import { DocumentTypeBadge, SourceBadge } from "./Badges";

type Tab = "sources" | "filters" | "evidence" | "attachments";

export function ResearchContextPanel({
  open,
  desktopCollapsed,
  close,
  messages,
  filters,
  setFilters,
  attachments,
  removeAttachment,
  excludedDocumentIds,
  toggleDocument,
  pinnedChunkIds,
  togglePinnedChunk,
  selectCitation,
}: {
  open: boolean;
  desktopCollapsed: boolean;
  close: () => void;
  messages: ResearchChatMessage[];
  filters: ChatFilters;
  setFilters: (filters: ChatFilters) => void;
  attachments: WorkspaceAttachment[];
  removeAttachment: (id: string) => void;
  excludedDocumentIds: string[];
  toggleDocument: (id: string) => void;
  pinnedChunkIds: string[];
  togglePinnedChunk: (id: string) => void;
  selectCitation: (citation: ChatSource) => void;
}) {
  const [tab, setTab] = useState<Tab>("sources");
  const citations =
    [...messages].reverse().find((item) => item.role === "assistant")
      ?.citations || [];
  useEffect(() => {
    if (!open) return;
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape") close();
    }
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [close, open]);
  return (
    <>
      {open && (
        <button
          type="button"
          aria-label="Close research context"
          className="fixed inset-0 z-40 bg-black/30 xl:hidden"
          onClick={close}
        />
      )}
      <aside
        id="research-context-panel"
        aria-label="Research context"
        className={cn(
          "border-l border-stone-200 bg-white transition-[width,transform] duration-200 dark:border-stone-800 dark:bg-stone-900 xl:sticky xl:top-16 xl:h-[calc(100vh-4rem)]",
          desktopCollapsed ? "xl:hidden" : "xl:block xl:w-80",
          open
            ? "fixed inset-y-0 right-0 z-50 block w-[min(90vw,24rem)] shadow-2xl"
            : "hidden",
        )}
      >
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between border-b border-stone-200 p-4 dark:border-stone-800">
            <div>
              <p className="font-serif text-lg font-bold">Research context</p>
              <p className="text-xs text-stone-500">Current workspace only</p>
            </div>
            <button
              type="button"
              onClick={close}
              aria-label="Close research context"
              className="grid size-10 place-items-center rounded-lg hover:bg-stone-100 xl:hidden dark:hover:bg-stone-800"
            >
              <X size={18} />
            </button>
          </div>
          <div className="grid grid-cols-4 border-b border-stone-200 dark:border-stone-800">
            {(
              [
                ["sources", BookOpen],
                ["filters", Filter],
                ["evidence", FileText],
                ["attachments", Paperclip],
              ] as const
            ).map(([value, Icon]) => (
              <button
                key={value}
                type="button"
                onClick={() => setTab(value)}
                aria-label={value}
                aria-pressed={tab === value}
                className={cn(
                  "grid min-h-12 place-items-center border-b-2",
                  tab === value
                    ? "border-emerald-700 text-emerald-700"
                    : "border-transparent text-stone-400",
                )}
              >
                <Icon size={17} />
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {tab === "sources" && (
              <SourceList
                citations={citations}
                excluded={excludedDocumentIds}
                toggle={toggleDocument}
                select={selectCitation}
              />
            )}
            {tab === "filters" && (
              <ChatFiltersPanel filters={filters} setFilters={setFilters} />
            )}
            {tab === "evidence" && (
              <EvidenceList
                citations={citations}
                pinned={pinnedChunkIds}
                togglePin={togglePinnedChunk}
                select={selectCitation}
              />
            )}
            {tab === "attachments" && (
              <AttachmentList
                attachments={attachments}
                remove={removeAttachment}
              />
            )}
          </div>
        </div>
      </aside>
    </>
  );
}

function SourceList({
  citations,
  excluded,
  toggle,
  select,
}: {
  citations: ChatSource[];
  excluded: string[];
  toggle: (id: string) => void;
  select: (citation: ChatSource) => void;
}) {
  const documents = [
    ...new Map(
      citations.map((item) => [
        item.documentId || item.publicationId || item.title,
        item,
      ]),
    ).values(),
  ];
  if (!documents.length)
    return (
      <ContextEmpty text="Retrieved documents will appear after an answer." />
    );
  return (
    <div className="space-y-3">
      {documents.map((source) => {
        const id = source.documentId || source.publicationId;
        const included = !id || !excluded.includes(id);
        return (
          <article
            key={id || source.title}
            className="rounded-xl border border-stone-200 p-3 dark:border-stone-700"
          >
            <div className="flex items-start justify-between gap-2">
              <button
                type="button"
                onClick={() => select(source)}
                className="text-left"
              >
                <span className="flex gap-1">
                  <SourceBadge code={source.sourceCode || source.repository} />
                  <DocumentTypeBadge type={source.documentType} />
                </span>
                <b className="mt-2 block text-sm leading-5">{source.title}</b>
                <span className="mt-1 block text-xs text-stone-500">
                  {[source.university, source.year]
                    .filter(Boolean)
                    .join(" · ") || "Indexed research"}
                </span>
              </button>
              {id && (
                <input
                  type="checkbox"
                  checked={included}
                  onChange={() => toggle(id)}
                  aria-label={`${included ? "Exclude" : "Include"} ${source.title}`}
                />
              )}
            </div>
            {source.similarity !== undefined && (
              <p className="mt-2 text-xs text-stone-500">
                Relevance {(source.similarity * 100).toFixed(0)}%
              </p>
            )}
          </article>
        );
      })}
    </div>
  );
}

function EvidenceList({
  citations,
  pinned,
  togglePin,
  select,
}: {
  citations: ChatSource[];
  pinned: string[];
  togglePin: (id: string) => void;
  select: (citation: ChatSource) => void;
}) {
  if (!citations.length)
    return <ContextEmpty text="Page-level evidence will appear here." />;
  return (
    <div className="space-y-3">
      {citations.map((source) => (
        <article
          key={`${source.index}-${source.chunkId || source.title}`}
          className="rounded-xl bg-stone-50 p-3 dark:bg-stone-800"
        >
          <button
            type="button"
            onClick={() => select(source)}
            className="w-full text-left"
          >
            <b className="text-xs">
              [{source.index}] {source.title}
            </b>
            <p className="mt-1 text-xs text-stone-500">{pageLabel(source)}</p>
            <p className="mt-2 line-clamp-5 text-xs leading-5">
              {source.excerpt || "Excerpt unavailable."}
            </p>
          </button>
          {source.chunkId && (
            <button
              type="button"
              onClick={() => togglePin(source.chunkId!)}
              aria-pressed={pinned.includes(source.chunkId)}
              className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-emerald-700"
            >
              <Pin size={13} />{" "}
              {pinned.includes(source.chunkId)
                ? "Pinned"
                : "Pin for next question"}
            </button>
          )}
        </article>
      ))}
    </div>
  );
}

const languageLabels: Record<string, string> = {
  en: "English",
  am: "Amharic",
  om: "Afaan Oromo",
};

function ChatFiltersPanel({
  filters,
  setFilters,
}: {
  filters: ChatFilters;
  setFilters: (filters: ChatFilters) => void;
}) {
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: ({ signal }) => api.sources(signal),
    staleTime: 60_000,
  });
  const universities = useQuery({
    queryKey: ["universities"],
    queryFn: ({ signal }) => api.universities(signal),
    staleTime: 60_000,
  });
  const toggle = (
    key: "repositories" | "universities" | "documentTypes" | "languages",
    value: string,
  ) =>
    setFilters({
      ...filters,
      [key]: filters[key].includes(value)
        ? filters[key].filter((item) => item !== value)
        : [...filters[key], value],
    });
  return (
    <div className="space-y-5">
      <FilterGroup title="Repository">
        {sources.data?.map((source) => (
          <Check
            key={source.slug}
            label={source.name}
            checked={filters.repositories.includes(source.slug)}
            onChange={() => toggle("repositories", source.slug)}
          />
        )) || <span className="text-xs text-stone-500">Loading sources…</span>}
      </FilterGroup>
      <FilterGroup title="University">
        {universities.data?.map((university) => (
          <Check
            key={university.id}
            label={university.name}
            checked={filters.universities.includes(university.id)}
            onChange={() => toggle("universities", university.id)}
          />
        )) || (
          <span className="text-xs text-stone-500">Loading universities…</span>
        )}
      </FilterGroup>
      <div className="grid grid-cols-2 gap-2">
        <NumberField
          label="Year from"
          value={filters.yearFrom}
          min={1800}
          max={3000}
          onChange={(yearFrom) => setFilters({ ...filters, yearFrom })}
        />
        <NumberField
          label="Year to"
          value={filters.yearTo}
          min={1800}
          max={3000}
          onChange={(yearTo) => setFilters({ ...filters, yearTo })}
        />
      </div>
      <FilterGroup title="Document type">
        {[
          "thesis",
          "dissertation",
          "journal article",
          "research report",
          "conference paper",
          "dataset",
        ].map((value) => (
          <Check
            key={value}
            label={value}
            checked={filters.documentTypes.includes(value)}
            onChange={() => toggle("documentTypes", value)}
          />
        ))}
      </FilterGroup>
      <FilterGroup title="Language">
        {["en", "am", "om"].map((value) => (
          <Check
            key={value}
            label={languageLabels[value]}
            checked={filters.languages.includes(value)}
            onChange={() => toggle("languages", value)}
          />
        ))}
      </FilterGroup>
    </div>
  );
}

function AttachmentList({
  attachments,
  remove,
}: {
  attachments: WorkspaceAttachment[];
  remove: (id: string) => void;
}) {
  if (!attachments.length)
    return (
      <ContextEmpty text="Attach temporary research files from the composer." />
    );
  return (
    <div className="space-y-2">
      {attachments.map((item) => (
        <div
          key={item.id}
          className="flex items-center justify-between rounded-xl border border-stone-200 p-3 text-xs dark:border-stone-700"
        >
          <div className="min-w-0">
            <b className="block truncate">{item.file.name}</b>
            <span
              className={
                item.status === "ready" ? "text-emerald-700" : "text-red-700"
              }
            >
              {item.status === "ready"
                ? "Ready in temporary workspace"
                : item.status === "too-large"
                  ? "File exceeds 20 MB"
                  : "Unsupported file type"}
            </span>
          </div>
          <button
            type="button"
            onClick={() => remove(item.id)}
            aria-label={`Remove ${item.file.name}`}
          >
            <X size={15} />
          </button>
        </div>
      ))}
    </div>
  );
}

function FilterGroup({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <fieldset>
      <legend className="mb-2 text-xs font-bold uppercase tracking-wider text-stone-500">
        {title}
      </legend>
      <div className="max-h-40 space-y-2 overflow-y-auto">{children}</div>
    </fieldset>
  );
}
function Check({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <label className="flex items-center gap-2 text-xs capitalize">
      <input type="checkbox" checked={checked} onChange={onChange} />
      {label}
    </label>
  );
}
function NumberField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value?: number;
  min: number;
  max: number;
  onChange: (value?: number) => void;
}) {
  return (
    <label className="text-xs font-semibold">
      {label}
      <input
        type="number"
        value={value ?? ""}
        min={min}
        max={max}
        onChange={(event) =>
          onChange(event.target.value ? Number(event.target.value) : undefined)
        }
        className="mt-1 w-full rounded-lg border border-stone-300 bg-transparent px-2 py-2 font-normal dark:border-stone-700"
      />
    </label>
  );
}
function ContextEmpty({ text }: { text: string }) {
  return <p className="py-8 text-center text-sm text-stone-500">{text}</p>;
}
function pageLabel(source: ChatSource) {
  if (!source.pageStart) return "Page unavailable";
  return source.pageEnd && source.pageEnd !== source.pageStart
    ? `Pages ${source.pageStart}–${source.pageEnd}`
    : `Page ${source.pageStart}`;
}
