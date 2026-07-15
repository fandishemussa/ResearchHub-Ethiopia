"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  cancelResearchMessage,
  sendResearchMessage,
} from "@/lib/chat-api";
import type {
  ChatFilters,
  ChatSettings,
  ChatSource,
  ResearchChatMessage,
  ResearchMode,
  StoredChatMessage,
  WorkspaceAttachment,
} from "@/lib/chat-types";
import { defaultFilters, defaultSettings } from "@/lib/chat-types";

const SETTINGS_KEY = "researchhub:chat-preferences";
const MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024;
const SUPPORTED_EXTENSIONS = new Set(["pdf", "txt", "md", "docx"]);

export interface InitialChatScope {
  documentId?: string;
  publicationId?: string;
  repository?: string;
  university?: string;
}

export function useResearchChat(initialScope: InitialChatScope) {
  const [messages, setMessages] = useState<ResearchChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string>();
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState<ResearchMode>("ask");
  const [filters, setFilters] = useState<ChatFilters>(() => ({
    ...defaultFilters,
    repositories: initialScope.repository ? [initialScope.repository] : [],
    universities: initialScope.university ? [initialScope.university] : [],
  }));
  const [settings, setSettings] = useState<ChatSettings>(defaultSettings);
  const [attachments, setAttachments] = useState<WorkspaceAttachment[]>([]);
  const [selectedCitation, setSelectedCitation] = useState<ChatSource>();
  const [pinnedChunkIds, setPinnedChunkIds] = useState<string[]>([]);
  const [excludedDocumentIds, setExcludedDocumentIds] = useState<string[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationStage, setGenerationStage] = useState(0);
  const [error, setError] = useState<string>();
  const abortRef = useRef<AbortController | undefined>(undefined);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(SETTINGS_KEY);
      if (stored) {
        const preferences = { ...defaultSettings, ...JSON.parse(stored) };
        window.setTimeout(() => setSettings(preferences), 0);
      }
    } catch {
      // Preferences are optional; conversation state is never restored.
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    } catch {
      // Continue with in-memory preferences when storage is unavailable.
    }
  }, [settings]);

  useEffect(() => {
    if (!isGenerating) return;
    const timer = window.setInterval(
      () => setGenerationStage((current) => Math.min(current + 1, 4)),
      1100,
    );
    return () => window.clearInterval(timer);
  }, [isGenerating]);

  const send = useCallback(
    async (value = draft) => {
      const text = value.trim();
      if (!text || isGenerating) return;
      const userMessage: ResearchChatMessage = {
        id: localId(),
        role: "user",
        content: text,
        createdAt: new Date().toISOString(),
        status: "complete",
        citations: [],
        mode,
        filters: { ...filters },
      };
      setMessages((current) => [...current, userMessage]);
      setDraft("");
      setError(undefined);
      setIsGenerating(true);
      setGenerationStage(0);
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const includedDocumentIds = messages
          .flatMap((message) => message.citations)
          .map((citation) => citation.documentId)
          .filter(
            (id): id is string =>
              Boolean(id) && !excludedDocumentIds.includes(id as string),
          );
        const response = await sendResearchMessage(
          {
            message: text,
            session_id: sessionId,
            mode,
            filters: {
              repositories: filters.repositories,
              universities: filters.universities,
              document_types: filters.documentTypes,
              languages: filters.languages,
              year_from: filters.yearFrom,
              year_to: filters.yearTo,
              minimum_similarity: filters.minimumSimilarity,
            },
            retrieval: {
              top_documents: filters.topDocuments,
              top_chunks: filters.topChunks,
              hybrid_search: settings.hybridSearch,
              rerank: settings.reranking,
              include_full_text: settings.includeFullText,
              include_metadata: settings.includeMetadata,
              citation_strictness: settings.citationStrictness,
              answer_length: settings.answerLength,
              response_language: settings.responseLanguage,
            },
            publication_ids: initialScope.publicationId
              ? [initialScope.publicationId]
              : undefined,
            document_ids: initialScope.documentId
              ? [initialScope.documentId]
              : includedDocumentIds.length
                ? [...new Set(includedDocumentIds)]
                : undefined,
            pinned_chunk_ids: pinnedChunkIds,
          },
          controller.signal,
        );
        setSessionId(response.session_id);
        setMessages((current) => [
          ...current,
          {
            id: response.message_id,
            role: "assistant",
            content: response.answer,
            createdAt: new Date().toISOString(),
            status: "complete",
            citations: response.citations.map((citation) => ({
              index: citation.index,
              publicationId: citation.publication_id || undefined,
              documentId: citation.document_id || undefined,
              chunkId: citation.chunk_id || undefined,
              title: citation.title,
              authors: citation.authors || [],
              university: citation.university || undefined,
              repository: citation.repository || undefined,
              sourceCode: citation.source || undefined,
              year: citation.publication_year || undefined,
              pageStart: citation.page_start || undefined,
              pageEnd: citation.page_end || undefined,
              excerpt: citation.excerpt || undefined,
              similarity: citation.similarity_score ?? undefined,
              documentUrl: citation.document_url || undefined,
              landingUrl: citation.landing_url || undefined,
              previewUrl: citation.preview_url || undefined,
              documentType: citation.document_type || undefined,
            })),
            retrievedDocumentCount: response.retrieved_document_count,
            retrievedChunkCount: response.retrieved_chunk_count,
            latencyMs: response.latency_ms ?? undefined,
            modelName: response.model_name || response.model,
            grounding: response.grounding_status,
            warnings: response.warnings,
            followUpQuestions: response.follow_up_questions,
            mode,
          },
        ]);
      } catch (caught) {
        if (controller.signal.aborted) {
          setError("Generation cancelled.");
        } else {
          if (process.env.NODE_ENV === "development") console.error(caught);
          setError(friendlyError(caught));
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = undefined;
        setIsGenerating(false);
      }
    }, [
      draft,
      excludedDocumentIds,
      filters,
      initialScope.documentId,
      initialScope.publicationId,
      isGenerating,
      messages,
      mode,
      pinnedChunkIds,
      sessionId,
      settings,
    ],
  );

  const stop = useCallback(() => {
    if (abortRef.current) cancelResearchMessage(abortRef.current);
  }, []);

  const clear = useCallback(() => {
    stop();
    setMessages([]);
    setSessionId(undefined);
    setDraft("");
    setAttachments([]);
    setSelectedCitation(undefined);
    setPinnedChunkIds([]);
    setExcludedDocumentIds([]);
    setGenerationStage(0);
    setError(undefined);
  }, [stop]);

  const loadConversation = useCallback(
    (id: string, storedMessages: StoredChatMessage[]) => {
      stop();
      setSessionId(id);
      setMessages(
        storedMessages.map((message) => ({
          id: message.id,
          role: message.role,
          content: message.content,
          createdAt: message.created_at,
          status: "complete",
          citations: message.citations.map((citation) => ({
            index: citation.index,
            publicationId: citation.publication_id || undefined,
            documentId: citation.document_id || undefined,
            chunkId: citation.chunk_id || undefined,
            title: citation.title,
            authors: citation.authors || [],
            university: citation.university || undefined,
            repository: citation.repository || undefined,
            sourceCode: citation.source || undefined,
            year: citation.publication_year || undefined,
            pageStart: citation.page_start || undefined,
            pageEnd: citation.page_end || undefined,
            excerpt: citation.excerpt || undefined,
            similarity: citation.similarity_score ?? undefined,
            documentUrl: citation.document_url || undefined,
            landingUrl: citation.landing_url || undefined,
            previewUrl: citation.preview_url || undefined,
            documentType: citation.document_type || undefined,
          })),
          retrievedDocumentCount: new Set(
            message.citations.map((item) => item.document_id).filter(Boolean),
          ).size,
          retrievedChunkCount: message.citations.filter(
            (item) => item.source_type === "document_chunk",
          ).length,
          latencyMs: message.latency_ms || undefined,
          modelName: message.model_name || undefined,
          grounding: message.citations.length ? "partial" : "insufficient",
          warnings: message.warnings,
        })),
      );
      setDraft("");
      setAttachments([]);
      setSelectedCitation(undefined);
      setError(undefined);
    },
    [stop],
  );

  const addAttachments = useCallback((files: FileList | File[]) => {
    setAttachments((current) => [
      ...current,
      ...Array.from(files).map((file) => {
        const extension = file.name.split(".").pop()?.toLowerCase() || "";
        return {
          id: localId(),
          file,
          status: file.size > MAX_ATTACHMENT_BYTES
            ? "too-large" as const
            : SUPPORTED_EXTENSIONS.has(extension)
              ? "ready" as const
              : "unsupported" as const,
        };
      }),
    ]);
  }, []);

  return {
    messages,
    setMessages,
    sessionId,
    draft,
    setDraft,
    mode,
    setMode,
    filters,
    setFilters,
    settings,
    setSettings,
    attachments,
    addAttachments,
    removeAttachment: (id: string) =>
      setAttachments((current) => current.filter((item) => item.id !== id)),
    selectedCitation,
    setSelectedCitation,
    pinnedChunkIds,
    togglePinnedChunk: (id: string) =>
      setPinnedChunkIds((current) =>
        current.includes(id)
          ? current.filter((item) => item !== id)
          : [...current, id],
      ),
    excludedDocumentIds,
    toggleDocument: (id: string) =>
      setExcludedDocumentIds((current) =>
        current.includes(id)
          ? current.filter((item) => item !== id)
          : [...current, id],
      ),
    isGenerating,
    generationStage,
    error,
    setError,
    send,
    stop,
    clear,
    loadConversation,
  };
}

function localId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

function friendlyError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.kind === "network") return "ResearchHub is unavailable. Check the backend and try again.";
    if (error.kind === "timeout") return "The research request timed out. Narrow the filters and retry.";
    if (error.kind === "aborted") return "Generation cancelled.";
    if (error.status === 401) return "Your authentication has expired. Sign in again.";
    if (error.status === 404) return "No indexed research matched the selected scope.";
  }
  return "The assistant could not complete this request. Please retry.";
}
