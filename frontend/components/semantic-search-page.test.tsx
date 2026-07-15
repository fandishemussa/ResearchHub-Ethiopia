import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SemanticSearchPage } from "./semantic-search-page";
import { searchSemanticPublications } from "@/lib/api";

const push = vi.fn();
const replace = vi.fn();
let params = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace }),
  useSearchParams: () => params,
}));
vi.mock("@/lib/api", async (original) => {
  const actual = await original<typeof import("@/lib/api")>();
  return { ...actual, searchSemanticPublications: vi.fn() };
});

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SemanticSearchPage />
    </QueryClientProvider>,
  );
}

describe("SemanticSearchPage", () => {
  afterEach(() => vi.useRealTimers());
  beforeEach(() => {
    params = new URLSearchParams();
    push.mockReset();
    replace.mockReset();
    localStorage.clear();
    vi.mocked(searchSemanticPublications).mockResolvedValue({
      query: "test",
      model: "test-model",
      count: 0,
      results: [],
    });
  });

  it("renders an accessible initial state and suggested searches", () => {
    renderPage();
    expect(
      screen.getByRole("textbox", { name: /Research question or topic/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Try a suggested search" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Semantic search results" }),
    ).toHaveAttribute("aria-live", "polite");
  });

  it("submits immediately and synchronizes the URL", async () => {
    renderPage();
    const input = screen.getByRole("textbox", {
      name: /Research question or topic/,
    });
    await userEvent.type(input, "maternal health Ethiopia");
    await userEvent.click(screen.getByRole("button", { name: /^Search$/ }));
    expect(push).toHaveBeenCalledWith(
      expect.stringContaining("q=maternal+health+Ethiopia"),
    );
    expect(
      JSON.parse(
        localStorage.getItem("researchhub:semantic-search-history") ?? "[]",
      ),
    ).toContain("maternal health Ethiopia");
  });

  it("debounces typed queries", async () => {
    vi.useFakeTimers();
    renderPage();
    const input = screen.getByRole("textbox", {
      name: /Research question or topic/,
    });
    fireEvent.change(input, { target: { value: "soil" } });
    expect(replace).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(500));
    expect(replace).toHaveBeenCalledWith(expect.stringContaining("q=soil"));
  });

  it("restores controls from URL and clears recent history", async () => {
    params = new URLSearchParams(
      "q=groundwater&source=aau-etd&limit=20&minSimilarity=0.5",
    );
    localStorage.setItem(
      "researchhub:semantic-search-history",
      JSON.stringify(["older search"]),
    );
    renderPage();
    expect(screen.getByRole("textbox")).toHaveValue("groundwater");
    expect(screen.getAllByRole("combobox")[0]).toHaveValue("aau-etd");
    params = new URLSearchParams();
  });
});
