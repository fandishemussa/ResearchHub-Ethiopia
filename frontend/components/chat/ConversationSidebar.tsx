"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Menu,
  MessageSquarePlus,
  Pencil,
  Pin,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import {
  deleteChatSession,
  fetchChatMessages,
  fetchChatSessions,
  updateChatSession,
} from "@/lib/chat-api";
import { api } from "@/lib/api";
import type { ChatSessionSummary, StoredChatMessage } from "@/lib/chat-types";
import { cn } from "@/lib/utils";

export function ConversationSidebar({
  open,
  desktopCollapsed,
  close,
  activeSessionId,
  newConversation,
  loadConversation,
}: {
  open: boolean;
  desktopCollapsed: boolean;
  close: () => void;
  activeSessionId?: string;
  newConversation: () => void;
  loadConversation: (id: string, messages: StoredChatMessage[]) => void;
}) {
  const client = useQueryClient();
  const [search, setSearch] = useState("");
  const [dateFilter, setDateFilter] = useState("all");
  const [universityFilter, setUniversityFilter] = useState("all");
  const [loadingId, setLoadingId] = useState<string>();
  const sessions = useQuery({
    queryKey: ["chat-sessions"],
    queryFn: ({ signal }) => fetchChatSessions(signal),
    staleTime: 15_000,
  });
  const universities = useQuery({
    queryKey: ["universities"],
    queryFn: ({ signal }) => api.universities(signal),
    staleTime: 60_000,
  });
  const mutate = useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: { title?: string; is_pinned?: boolean };
    }) => updateChatSession(id, payload),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ["chat-sessions"] }),
  });
  const remove = useMutation({
    mutationFn: deleteChatSession,
    onSuccess: (_data, deletedId) => {
      void client.invalidateQueries({ queryKey: ["chat-sessions"] });
      if (deletedId === activeSessionId) newConversation();
    },
  });
  const groups = useMemo(
    () =>
      groupSessions(
        (sessions.data || []).filter((item) =>
          matches(item, search, dateFilter, universityFilter),
        ),
      ),
    [dateFilter, search, sessions.data, universityFilter],
  );
  async function select(session: ChatSessionSummary) {
    setLoadingId(session.id);
    try {
      loadConversation(session.id, await fetchChatMessages(session.id));
      close();
    } finally {
      setLoadingId(undefined);
    }
  }
  return (
    <>
      {open && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/30 lg:hidden"
          aria-label="Close conversations"
          onClick={close}
        />
      )}
      <aside
        id="conversation-sidebar"
        aria-label="Conversation history"
        className={cn(
          "border-r border-stone-200 bg-white transition-[width,transform] duration-200 dark:border-stone-800 dark:bg-stone-900 lg:sticky lg:top-16 lg:h-[calc(100vh-4rem)]",
          desktopCollapsed ? "lg:hidden" : "lg:block lg:w-72",
          open
            ? "fixed inset-y-0 left-0 z-50 block w-[min(90vw,20rem)] shadow-2xl"
            : "hidden",
        )}
      >
        <div className="flex h-full flex-col p-3">
          <div className="flex items-center justify-between">
            <b className="font-serif text-lg">Conversations</b>
            <button
              type="button"
              onClick={close}
              aria-label="Close conversations"
              className="grid size-10 place-items-center lg:hidden"
            >
              <X size={18} />
            </button>
          </div>
          <button
            type="button"
            onClick={() => {
              newConversation();
              close();
            }}
            className="mt-3 inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-emerald-800 px-3 text-sm font-semibold text-white"
          >
            <MessageSquarePlus size={17} /> New conversation
          </button>
          <label className="relative mt-3">
            <span className="sr-only">Search conversations</span>
            <Search
              className="absolute left-3 top-3 text-stone-400"
              size={16}
            />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search conversations"
              className="w-full rounded-xl border border-stone-200 bg-transparent py-2.5 pl-9 pr-3 text-sm dark:border-stone-700"
            />
          </label>
          <select
            value={dateFilter}
            onChange={(event) => setDateFilter(event.target.value)}
            aria-label="Filter conversations by date"
            className="mt-2 rounded-lg border border-stone-200 bg-transparent px-2 py-2 text-xs dark:border-stone-700"
          >
            <option value="all">All dates</option>
            <option value="today">Today</option>
            <option value="week">Last 7 days</option>
            <option value="older">Older</option>
          </select>
          <select
            value={universityFilter}
            onChange={(event) => setUniversityFilter(event.target.value)}
            aria-label="Filter conversations by university"
            className="mt-2 rounded-lg border border-stone-200 bg-transparent px-2 py-2 text-xs dark:border-stone-700"
          >
            <option value="all">All universities</option>
            <option value="unscoped">All-repository conversations</option>
            {universities.data?.map((university) => (
              <option key={university.id} value={university.id}>
                {university.name}
              </option>
            ))}
          </select>
          <div className="mt-3 flex-1 space-y-4 overflow-y-auto">
            {sessions.isPending && (
              <p className="p-3 text-sm text-stone-500">
                Loading conversations…
              </p>
            )}
            {sessions.isError && (
              <button
                type="button"
                onClick={() => sessions.refetch()}
                className="p-3 text-left text-sm text-red-700"
              >
                Conversations could not be loaded. Retry
              </button>
            )}
            {Object.entries(groups).map(
              ([group, items]) =>
                items.length > 0 && (
                  <section key={group}>
                    <h2 className="mb-1 px-2 text-[11px] font-bold uppercase tracking-wider text-stone-400">
                      {group}
                    </h2>
                    <div className="space-y-1">
                      {items.map((session) => (
                        <article
                          key={session.id}
                          className={cn(
                            "group rounded-xl border p-2",
                            activeSessionId === session.id
                              ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-950/30"
                              : "border-transparent hover:bg-stone-50 dark:hover:bg-stone-800",
                          )}
                        >
                          <button
                            type="button"
                            onClick={() => void select(session)}
                            disabled={loadingId === session.id}
                            className="w-full text-left"
                          >
                            <span className="flex items-center gap-1 text-sm font-semibold">
                              {session.is_pinned && (
                                <Pin size={12} className="text-amber-600" />
                              )}
                              <span className="truncate">{session.title}</span>
                            </span>
                            <span className="mt-1 flex justify-between text-[11px] text-stone-500">
                              <span>
                                {session.last_model_name || "Model unavailable"}
                              </span>
                              <time dateTime={session.updated_at}>
                                {relativeDate(session.updated_at)}
                              </time>
                            </span>
                          </button>
                          <div className="mt-1 hidden justify-end gap-1 group-hover:flex group-focus-within:flex">
                            <button
                              type="button"
                              aria-label={`Rename ${session.title}`}
                              onClick={() => {
                                const title = window
                                  .prompt("Rename conversation", session.title)
                                  ?.trim();
                                if (title)
                                  mutate.mutate({
                                    id: session.id,
                                    payload: { title },
                                  });
                              }}
                              className="history-action"
                            >
                              <Pencil size={13} />
                            </button>
                            <button
                              type="button"
                              aria-label={`${session.is_pinned ? "Unpin" : "Pin"} ${session.title}`}
                              onClick={() =>
                                mutate.mutate({
                                  id: session.id,
                                  payload: { is_pinned: !session.is_pinned },
                                })
                              }
                              className="history-action"
                            >
                              <Pin size={13} />
                            </button>
                            <button
                              type="button"
                              aria-label={`Delete ${session.title}`}
                              onClick={() =>
                                window.confirm(`Delete “${session.title}”?`) &&
                                remove.mutate(session.id)
                              }
                              className="history-action text-red-700"
                            >
                              <Trash2 size={13} />
                            </button>
                          </div>
                        </article>
                      ))}
                    </div>
                  </section>
                ),
            )}
            {!sessions.isPending &&
              !Object.values(groups).some((items) => items.length) && (
                <p className="p-4 text-center text-sm text-stone-500">
                  No matching conversations.
                </p>
              )}
          </div>
        </div>
      </aside>
    </>
  );
}

export function ConversationMenuButton({
  open,
  expanded,
}: {
  open: () => void;
  expanded: boolean;
}) {
  return (
    <button
      type="button"
      onClick={open}
      aria-label={`${expanded ? "Hide" : "Show"} conversations`}
      aria-controls="conversation-sidebar"
      aria-expanded={expanded}
      className="toolbar-button"
    >
      <Menu size={17} />
    </button>
  );
}

function groupSessions(items: ChatSessionSummary[]) {
  const result: Record<
    "Pinned" | "Today" | "Yesterday" | "Last 7 days" | "Older",
    ChatSessionSummary[]
  > = { Pinned: [], Today: [], Yesterday: [], "Last 7 days": [], Older: [] };
  const now = new Date();
  for (const item of [...items].sort(
    (a, b) =>
      Number(b.is_pinned) - Number(a.is_pinned) ||
      Date.parse(b.updated_at) - Date.parse(a.updated_at),
  )) {
    if (item.is_pinned) {
      result.Pinned.push(item);
      continue;
    }
    const days = Math.floor(
      (startOfDay(now).getTime() -
        startOfDay(new Date(item.updated_at)).getTime()) /
        86_400_000,
    );
    result[
      days <= 0
        ? "Today"
        : days === 1
          ? "Yesterday"
          : days <= 7
            ? "Last 7 days"
            : "Older"
    ].push(item);
  }
  return result;
}

function matches(
  item: ChatSessionSummary,
  search: string,
  date: string,
  university: string,
) {
  if (!item.title.toLowerCase().includes(search.trim().toLowerCase()))
    return false;
  if (
    university !== "all" &&
    (university === "unscoped"
      ? item.university_id !== null
      : item.university_id !== university)
  )
    return false;
  const age = (Date.now() - Date.parse(item.updated_at)) / 86_400_000;
  return (
    date === "all" ||
    (date === "today" && age < 1) ||
    (date === "week" && age <= 7) ||
    (date === "older" && age > 7)
  );
}
function startOfDay(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}
function relativeDate(value: string) {
  const date = new Date(value);
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}
