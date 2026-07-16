import type {
  DashboardSummary,
  AIKeyword,
  PublicationCitation,
  PublicationSummary,
  EmbeddingAdministrationStatus,
  KeywordPoint,
  Publication,
  PublicationSimilarityResponse,
  SemanticSearchParams,
  SemanticSearchResponse,
  TrendPoint,
  University,
  Source,
  SourceCreate,
  SourceUpdate,
  SourceConnectionTest,
  HarvestJob,
  HarvestEvent,
  HarvestFailure,
  ImportPreview,
  AuthorizationMatrix,
  QualityIssuePage,
  QualitySummary,
  Researcher,
  SystemHealth,
} from "./types";
import type {
  ChatSessionSummary,
  ResearchChatRequest,
  ResearchChatResponse,
  StoredChatMessage,
} from "./chat-types";
import type {
  DocumentChunkPage,
  ResearchDocument,
  ResearchDocumentPage,
} from "./document-types";
import {
  authorizationHeader,
  clearAuthTokens,
  readAuthTokens,
  storeAuthTokens,
  type AuthTokens,
  type AuthUser,
} from "./auth";

const baseUrl = (process.env.NEXT_PUBLIC_API_URL || "/backend-api").replace(
  /\/$/,
  "",
);
const requestTimeoutMs = Number(
  process.env.NEXT_PUBLIC_API_TIMEOUT_MS || 30000,
);
const chatRequestTimeoutMs = Number(
  process.env.NEXT_PUBLIC_AI_TIMEOUT_MS || 210000,
);

export type ApiErrorKind =
  | "network"
  | "server"
  | "validation"
  | "not-found"
  | "unauthorized"
  | "forbidden"
  | "aborted"
  | "timeout";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly kind: ApiErrorKind,
    public readonly status?: number,
    public readonly details?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetchWithTimeout(`${baseUrl}${path}`, {
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new ApiError("The ResearchHub API request timed out.", "timeout");
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("The request was cancelled.", "aborted");
    }
    throw new ApiError("Unable to reach the ResearchHub API.", "network");
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const detail = extractErrorDetail(payload);
    const kind: ApiErrorKind =
      response.status === 401
        ? "unauthorized"
        : response.status === 403
          ? "forbidden"
          : response.status === 404
            ? "not-found"
            : response.status === 400 || response.status === 422
              ? "validation"
              : "server";
    throw new ApiError(
      detail || `ResearchHub returned an error (${response.status}).`,
      kind,
      response.status,
      process.env.NODE_ENV === "development" ? detail : undefined,
    );
  }
  return response.json() as Promise<T>;
}

async function request<T>(
  path: string,
  options: RequestInit,
  timeoutMs = requestTimeoutMs,
): Promise<T> {
  let response: Response;
  try {
    response = await fetchWithTimeout(
      `${baseUrl}${path}`,
      {
        ...options,
        headers: {
          ...(options.body instanceof FormData
            ? {}
            : { "Content-Type": "application/json" }),
          Accept: "application/json",
          ...options.headers,
        },
      },
      timeoutMs,
    );
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError")
      throw new ApiError("The ResearchHub API request timed out.", "timeout");
    if (error instanceof DOMException && error.name === "AbortError")
      throw new ApiError("The request was cancelled.", "aborted");
    throw new ApiError("Unable to reach the ResearchHub API.", "network");
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const detail = extractErrorDetail(payload);
    throw new ApiError(
      detail || `ResearchHub returned an error (${response.status}).`,
      response.status === 404
        ? "not-found"
        : response.status === 401
          ? "unauthorized"
          : response.status === 403
            ? "forbidden"
            : response.status < 500
              ? "validation"
              : "server",
      response.status,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function getStatus<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetchWithTimeout(path, {
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError")
      throw new ApiError("The ResearchHub API request timed out.", "timeout");
    if (error instanceof DOMException && error.name === "AbortError")
      throw new ApiError("The request was cancelled.", "aborted");
    throw new ApiError("Unable to reach the ResearchHub API.", "network");
  }
  const payload: unknown = await response.json().catch(() => null);
  if ((response.ok || response.status === 503) && payload !== null)
    return payload as T;
  throw new ApiError(
    extractErrorDetail(payload) ||
      `ResearchHub returned an error (${response.status}).`,
    "server",
    response.status,
  );
}

async function fetchWithTimeout(
  input: RequestInfo | URL,
  options: RequestInit,
  timeoutMs = requestTimeoutMs,
): Promise<Response> {
  const controller = new AbortController();
  const parentSignal = options.signal;
  const abortFromParent = () => controller.abort(parentSignal?.reason);
  if (parentSignal?.aborted) abortFromParent();
  else parentSignal?.addEventListener("abort", abortFromParent, { once: true });
  const timeout = setTimeout(
    () =>
      controller.abort(new DOMException("Request timed out", "TimeoutError")),
    timeoutMs,
  );
  try {
    return await fetch(input, {
      ...options,
      headers: { ...authorizationHeader(), ...options.headers },
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
    parentSignal?.removeEventListener("abort", abortFromParent);
  }
}

function extractErrorDetail(payload: unknown): string | undefined {
  if (!payload || typeof payload !== "object" || !("detail" in payload))
    return undefined;
  const detail = payload.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        item && typeof item === "object" && "msg" in item
          ? String(item.msg)
          : "Invalid request",
      )
      .join("; ");
  }
  return undefined;
}

export const api = {
  login: async (identifier: string, password: string) => {
    const form = new URLSearchParams({ username: identifier, password });
    const tokens = await request<AuthTokens>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });
    storeAuthTokens(tokens);
    return tokens;
  },
  currentUser: (signal?: AbortSignal) => get<AuthUser>("/auth/me", signal),
  logout: async () => {
    const tokens = readAuthTokens();
    try {
      if (tokens) {
        await request<void>("/auth/logout", {
          method: "POST",
          body: JSON.stringify({ refresh_token: tokens.refresh_token }),
        });
      }
    } finally {
      clearAuthTokens();
    }
  },
  researchers: (signal?: AbortSignal) =>
    get<Researcher[]>("/authors?limit=200", signal),
  qualitySummary: (signal?: AbortSignal) =>
    get<QualitySummary>("/quality/summary", signal),
  qualityIssues: (signal?: AbortSignal) =>
    get<QualityIssuePage>("/quality/issues?limit=20", signal),
  systemHealth: (signal?: AbortSignal) =>
    getStatus<SystemHealth>("/backend-health/dependencies", signal),
  authorizationMatrix: (signal?: AbortSignal) =>
    get<AuthorizationMatrix>("/auth/authorization-matrix", signal),
  researchDocuments: (params: URLSearchParams, signal?: AbortSignal) =>
    get<ResearchDocumentPage>(`/documents?${params.toString()}`, signal),
  researchDocument: (id: string, signal?: AbortSignal) =>
    get<ResearchDocument>(`/documents/${encodeURIComponent(id)}`, signal),
  documentChunks: (id: string, params: URLSearchParams, signal?: AbortSignal) =>
    get<DocumentChunkPage>(
      `/documents/${encodeURIComponent(id)}/chunks?${params.toString()}`,
      signal,
    ),
  dashboard: (signal?: AbortSignal) =>
    get<DashboardSummary>("/dashboard/summary", signal),
  trends: (signal?: AbortSignal) =>
    get<TrendPoint[]>("/dashboard/publication-trends", signal),
  keywords: (signal?: AbortSignal) =>
    get<KeywordPoint[]>("/dashboard/keyword-trends?limit=8", signal),
  publications: (params: URLSearchParams, signal?: AbortSignal) =>
    get<Publication[]>(`/search/publications?${params}`, signal),
  publication: (id: string, signal?: AbortSignal) =>
    get<Publication>(`/publications/${encodeURIComponent(id)}`, signal),
  universities: (signal?: AbortSignal) =>
    get<University[]>("/universities?limit=200", signal),
  sources: (signal?: AbortSignal) => get<Source[]>("/sources", signal),
  createSource: (payload: SourceCreate, signal?: AbortSignal) =>
    request<Source>("/sources", {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    }),
  testSourceConfiguration: (payload: SourceCreate, signal?: AbortSignal) =>
    request<SourceConnectionTest>("/sources/test-configuration", {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    }),
  source: (id: string, signal?: AbortSignal) =>
    get<Source>(`/sources/${encodeURIComponent(id)}`, signal),
  updateSource: (id: string, payload: SourceUpdate) =>
    request<Source>(`/sources/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  testSource: (id: string) =>
    request<SourceConnectionTest>(`/sources/${encodeURIComponent(id)}/test`, {
      method: "POST",
    }),
  setSourceEnabled: (id: string, enabled: boolean) =>
    request<Source>(
      `/sources/${encodeURIComponent(id)}/${enabled ? "enable" : "disable"}`,
      { method: "POST" },
    ),
  runSourceHarvest: (id: string, mode: "full" | "incremental" | "dry-run") =>
    request<HarvestJob>(`/sources/${encodeURIComponent(id)}/harvest/${mode}`, {
      method: "POST",
    }),
  deleteSource: (id: string) =>
    request<void>(`/sources/${encodeURIComponent(id)}`, { method: "DELETE" }),
  harvestJobs: (sourceId?: string, signal?: AbortSignal) =>
    get<HarvestJob[]>(
      `/harvest/jobs${sourceId ? `?source_id=${encodeURIComponent(sourceId)}` : ""}`,
      signal,
    ),
  harvestJob: (id: string, signal?: AbortSignal) =>
    get<HarvestJob>(`/harvest/jobs/${encodeURIComponent(id)}`, signal),
  harvestEvents: (id: string, signal?: AbortSignal) =>
    get<HarvestEvent[]>(
      `/harvest/jobs/${encodeURIComponent(id)}/events`,
      signal,
    ),
  harvestFailures: (id: string, signal?: AbortSignal) =>
    get<HarvestFailure[]>(
      `/harvest/jobs/${encodeURIComponent(id)}/failures`,
      signal,
    ),
  cancelHarvest: (id: string) =>
    request<HarvestJob>(`/harvest/jobs/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
    }),
  retryHarvest: (id: string) =>
    request<HarvestJob>(`/harvest/jobs/${encodeURIComponent(id)}/retry`, {
      method: "POST",
    }),
  uploadImport: (
    sourceId: string,
    format: "xml" | "json" | "csv",
    file: File,
    onProgress?: (percent: number) => void,
  ) => {
    const body = new FormData();
    body.append("source_id", sourceId);
    body.append("file", file);
    return uploadFormData<HarvestJob>(`/import/${format}`, body, onProgress);
  },
  previewImport: (id: string) =>
    request<ImportPreview>(`/import/${encodeURIComponent(id)}/preview`, {
      method: "POST",
    }),
  confirmImport: (id: string) =>
    request<HarvestJob>(`/import/${encodeURIComponent(id)}/confirm`, {
      method: "POST",
    }),
  cancelImport: (id: string) =>
    request<HarvestJob>(`/import/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
    }),
  similarPublications: (
    id: string,
    options: { limit?: number; minimumScore?: number } = {},
    signal?: AbortSignal,
  ) => {
    const params = new URLSearchParams();
    if (options.limit !== undefined) params.set("limit", String(options.limit));
    if (options.minimumScore !== undefined)
      params.set("minimum_score", String(options.minimumScore));
    const query = params.size ? `?${params.toString()}` : "";
    return get<PublicationSimilarityResponse>(
      `/ai/publications/${encodeURIComponent(id)}/similar${query}`,
      signal,
    );
  },
  askChat: (payload: ResearchChatRequest, signal?: AbortSignal) =>
    request<ResearchChatResponse>(
      "/ai/chat/query",
      {
        method: "POST",
        body: JSON.stringify(payload),
        signal,
      },
      chatRequestTimeoutMs,
    ),
  chatSessions: (signal?: AbortSignal) =>
    get<ChatSessionSummary[]>("/ai/chat/sessions", signal),
  chatMessages: (sessionId: string, signal?: AbortSignal) =>
    get<StoredChatMessage[]>(
      `/ai/chat/sessions/${encodeURIComponent(sessionId)}/messages`,
      signal,
    ),
  updateChatSession: (
    sessionId: string,
    payload: { title?: string; is_pinned?: boolean },
  ) =>
    request<ChatSessionSummary>(
      `/ai/chat/sessions/${encodeURIComponent(sessionId)}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  deleteChatSession: (sessionId: string) =>
    request<void>(`/ai/chat/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    }),
  chatFeedback: (
    messageId: string,
    rating: "helpful" | "not_helpful" | "inaccurate" | "missing_sources",
  ) =>
    request<{ id: string; status: string }>("/ai/chat/feedback", {
      method: "POST",
      body: JSON.stringify({ message_id: messageId, rating }),
    }),
  summarizePublication: (
    id: string,
    summaryType = "structured",
    signal?: AbortSignal,
  ) =>
    request<PublicationSummary>(
      `/ai/publications/${encodeURIComponent(id)}/summary`,
      {
        method: "POST",
        body: JSON.stringify({
          summary_type: summaryType,
          summary_style: summaryType,
          summary_scope: "auto",
          max_length: 5000,
        }),
        signal,
      },
    ),
  embeddingAdministration: (signal?: AbortSignal) =>
    get<EmbeddingAdministrationStatus>("/admin/ai/embeddings", signal),
  generateEmbeddings: (mode: "missing" | "stale" | "failed", limit = 100) =>
    request<{ status: string; task_id: string }>(
      `/admin/ai/embeddings/generate?mode=${mode}&limit=${limit}`,
      { method: "POST" },
    ),
  extractPublicationKeywords: (id: string, signal?: AbortSignal) =>
    request<AIKeyword[]>(
      `/ai/publications/${encodeURIComponent(id)}/extract-keywords`,
      {
        method: "POST",
        signal,
      },
    ),
  publicationCitation: (id: string, style: string, signal?: AbortSignal) =>
    get<PublicationCitation>(
      `/ai/publications/${encodeURIComponent(id)}/citation?style=${encodeURIComponent(style)}`,
      signal,
    ),
};

function uploadFormData<T>(
  path: string,
  body: FormData,
  onProgress?: (percent: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${baseUrl}${path}`);
    xhr.setRequestHeader("Accept", "application/json");
    const auth = authorizationHeader().Authorization;
    if (auth) xhr.setRequestHeader("Authorization", auth);
    xhr.timeout = 120000;
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        onProgress?.(
          Math.min(100, Math.round((event.loaded / event.total) * 100)),
        );
      }
    });
    xhr.addEventListener("load", () => {
      const payload: unknown = xhr.responseText
        ? safelyParseJson(xhr.responseText)
        : null;
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload as T);
        return;
      }
      reject(
        new ApiError(
          extractErrorDetail(payload) ||
            `ResearchHub returned an error (${xhr.status}).`,
          xhr.status === 404
            ? "not-found"
            : xhr.status === 401
              ? "unauthorized"
              : xhr.status === 403
                ? "forbidden"
                : xhr.status < 500
                  ? "validation"
                  : "server",
          xhr.status,
        ),
      );
    });
    xhr.addEventListener("error", () =>
      reject(new ApiError("Unable to reach the ResearchHub API.", "network")),
    );
    xhr.addEventListener("timeout", () =>
      reject(new ApiError("The ResearchHub API request timed out.", "timeout")),
    );
    xhr.addEventListener("abort", () =>
      reject(new ApiError("The request was cancelled.", "aborted")),
    );
    xhr.send(body);
  });
}

function safelyParseJson(value: string): unknown {
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return null;
  }
}

export function searchSemanticPublications({
  query,
  limit,
  source,
  minSimilarity,
  signal,
}: SemanticSearchParams): Promise<SemanticSearchResponse> {
  const params = new URLSearchParams({ q: query });
  if (limit !== undefined) params.set("limit", String(limit));
  if (source) params.set("source", source);
  if (minSimilarity !== undefined)
    params.set("min_similarity", String(minSimilarity));
  return get<unknown>(`/search/semantic?${params.toString()}`, signal).then(
    (payload) => parseSemanticResponse(payload, query),
  );
}

function parseSemanticResponse(
  payload: unknown,
  requestedQuery: string,
): SemanticSearchResponse {
  if (!isRecord(payload) || !Array.isArray(payload.results)) {
    throw new ApiError("The semantic search response was invalid.", "server");
  }
  const results = payload.results
    .filter(isRecord)
    .filter(
      (item) => typeof item.id === "string" && typeof item.title === "string",
    )
    .map((item) => ({
      id: item.id as string,
      title: item.title as string,
      abstract_preview:
        typeof item.abstract_preview === "string"
          ? item.abstract_preview
          : null,
      publication_year:
        typeof item.publication_year === "number"
          ? item.publication_year
          : null,
      source: typeof item.source === "string" ? item.source : "unknown",
      article_url:
        typeof item.article_url === "string" ? item.article_url : null,
      similarity:
        typeof item.similarity === "number" && Number.isFinite(item.similarity)
          ? item.similarity
          : 0,
    }));
  return {
    query: typeof payload.query === "string" ? payload.query : requestedQuery,
    model: typeof payload.model === "string" ? payload.model : "Unknown model",
    count: results.length,
    results,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
