import { api } from "@/lib/api";
import type {
  ChatSessionSummary,
  ResearchChatRequest,
  ResearchChatResponse,
  StoredChatMessage,
} from "@/lib/chat-types";

export function sendResearchMessage(
  payload: ResearchChatRequest,
  signal?: AbortSignal,
): Promise<ResearchChatResponse> {
  return api.askChat(payload, signal);
}

export function fetchChatSessions(
  signal?: AbortSignal,
): Promise<ChatSessionSummary[]> {
  return api.chatSessions(signal);
}

export function fetchChatMessages(
  sessionId: string,
  signal?: AbortSignal,
): Promise<StoredChatMessage[]> {
  return api.chatMessages(sessionId, signal);
}

export function updateChatSession(
  sessionId: string,
  payload: { title?: string; is_pinned?: boolean },
) {
  return api.updateChatSession(sessionId, payload);
}

export function deleteChatSession(sessionId: string) {
  return api.deleteChatSession(sessionId);
}

export function cancelResearchMessage(controller: AbortController): void {
  controller.abort();
}

export function submitChatFeedback(
  messageId: string,
  rating: "helpful" | "not_helpful" | "inaccurate" | "missing_sources",
) {
  return api.chatFeedback(messageId, rating);
}

export function fetchDocumentPreview(
  documentId: string,
  page?: number,
): string {
  const suffix = page ? `?page=${page}` : "";
  return `/backend-api/ai/documents/${encodeURIComponent(documentId)}/view${suffix}`;
}
