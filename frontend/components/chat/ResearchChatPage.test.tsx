import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ResearchChatPage } from "./ResearchChatPage";
import * as chatApi from "@/lib/chat-api";

vi.mock("@/lib/chat-api", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/chat-api")>("@/lib/chat-api");
  return {
    ...actual,
    sendResearchMessage: vi.fn(),
    submitChatFeedback: vi.fn(),
    fetchChatSessions: vi.fn(),
    fetchChatMessages: vi.fn(),
    updateChatSession: vi.fn(),
    deleteChatSession: vi.fn(),
  };
});

function renderChat() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ResearchChatPage initialScope={{}} />
    </QueryClientProvider>,
  );
}

const response = {
  session_id: "temporary-session",
  message_id: "assistant-message",
  answer: "The strongest evidence reports reduced loss [1].",
  citations: [
    {
      index: 1,
      publication_id: "publication-1",
      document_id: "document-1",
      chunk_id: "chunk-1",
      title: "Postharvest loss study",
      authors: ["Abebe Kebede"],
      publication_year: 2023,
      source: "aau",
      page_start: 15,
      page_end: 16,
      excerpt: "Farm storage reduced measured loss.",
      similarity_score: 0.82,
      landing_url: "https://example.edu/item/1",
    },
  ],
  retrieved_publications: ["publication-1"],
  retrieved_document_count: 1,
  retrieved_chunk_count: 1,
  grounding_status: "strong" as const,
  confidence: 0.8,
  model: "grounded-local-v2",
  model_name: "grounded-local-v2",
  latency_ms: 800,
  usage: {},
  warnings: [],
  follow_up_questions: ["What methodology did the study use?"],
};

describe("ResearchChatPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(chatApi.fetchChatSessions).mockResolvedValue([]);
    localStorage.clear();
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn() },
    });
  });

  it("loads history without automatically restoring a previous session", async () => {
    renderChat();
    expect(screen.getByText("Explore Ethiopian research")).toBeInTheDocument();
    expect(screen.getByLabelText(/conversation history/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(chatApi.fetchChatSessions).toHaveBeenCalledOnce(),
    );
    expect(chatApi.fetchChatMessages).not.toHaveBeenCalled();
    expect(localStorage.getItem("researchhub:chat-preferences")).not.toContain(
      "messages",
    );
  });

  it("sends with Enter and opens page-level citation details", async () => {
    vi.mocked(chatApi.sendResearchMessage).mockResolvedValue(response);
    renderChat();
    const input = screen.getByLabelText("Research question");
    await userEvent.type(input, "What reduced postharvest loss?{enter}");
    await screen.findByText(/strongest evidence reports/i);
    expect(chatApi.sendResearchMessage).toHaveBeenCalledWith(
      expect.objectContaining({ session_id: undefined, mode: "ask" }),
      expect.any(AbortSignal),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /\[1\] Postharvest loss study/i }),
    );
    expect(
      screen.getByRole("dialog", { name: /postharvest loss study/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Farm storage reduced measured loss."),
    ).toBeInTheDocument();
  });

  it("stops an active generation request", async () => {
    vi.mocked(chatApi.sendResearchMessage).mockImplementation(
      (_payload, signal) =>
        new Promise((_resolve, reject) =>
          signal?.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError")),
          ),
        ),
    );
    renderChat();
    await userEvent.type(
      screen.getByLabelText("Research question"),
      "Long question",
    );
    await userEvent.click(screen.getByLabelText("Send question"));
    await userEvent.click(screen.getByLabelText("Stop generation"));
    expect(
      await screen.findByText("Generation cancelled."),
    ).toBeInTheDocument();
  });

  it("clears the current conversation view after confirmation", async () => {
    vi.mocked(chatApi.sendResearchMessage).mockResolvedValue(response);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderChat();
    await userEvent.type(
      screen.getByLabelText("Research question"),
      "Question{enter}",
    );
    await screen.findByText(/strongest evidence reports/i);
    await userEvent.click(screen.getByLabelText("Clear conversation"));
    expect(screen.getByText("Explore Ethiopian research")).toBeInTheDocument();
    expect(
      screen.queryByText(/strongest evidence reports/i),
    ).not.toBeInTheDocument();
  });

  it("provides accessible context drawer, filters, settings, and Shift+Enter", async () => {
    renderChat();
    await userEvent.click(
      screen.getByLabelText(/source filters and research context/),
    );
    expect(screen.getByLabelText("Research context")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("filters"));
    expect(screen.getByText("Document type")).toBeInTheDocument();
    await userEvent.click(
      screen.getAllByLabelText("Close research context").at(-1)!,
    );
    await userEvent.click(screen.getByLabelText("Open research settings"));
    expect(
      screen.getByRole("dialog", { name: "Advanced research settings" }),
    ).toBeInTheDocument();
    fireEvent.keyDown(screen.getByLabelText("Research question"), {
      key: "Enter",
      shiftKey: true,
    });
    expect(chatApi.sendResearchMessage).not.toHaveBeenCalled();
  });

  it("opens both responsive side drawers from their toggle controls", async () => {
    renderChat();

    const historyToggle = screen.getByLabelText("Show conversations");
    expect(historyToggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(historyToggle);
    expect(screen.getByLabelText("Hide conversations")).toHaveAttribute(
      "aria-expanded",
      "true",
    );

    const contextToggle = screen.getByLabelText(
      "Show source filters and research context",
    );
    expect(contextToggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(contextToggle);
    expect(
      screen.getByLabelText("Hide source filters and research context"),
    ).toHaveAttribute("aria-expanded", "true");
  });
});
