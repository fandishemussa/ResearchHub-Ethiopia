import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ResearchersPage from "./page";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: { researchers: vi.fn() },
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ResearchersPage />
    </QueryClientProvider>,
  );
}

describe("ResearchersPage", () => {
  beforeEach(() => {
    vi.mocked(api.researchers).mockResolvedValue([
      {
        id: "r1",
        full_name: "Demonstration Researcher",
        normalized_name: "demonstration researcher",
        affiliation: "Plant Sciences",
        orcid: null,
      },
      {
        id: "r2",
        full_name: "Sample Scholar",
        normalized_name: "sample scholar",
        affiliation: "Public Health",
        orcid: "0000-0000-0000-0001",
      },
    ]);
  });

  it("loads and filters normalized researcher records", async () => {
    renderPage();
    expect(
      await screen.findByRole("heading", { name: "Sample Scholar" }),
    ).toBeInTheDocument();
    await userEvent.type(
      screen.getByPlaceholderText(/search by name/i),
      "Plant Sciences",
    );
    expect(
      screen.getByRole("heading", { name: "Demonstration Researcher" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Sample Scholar" }),
    ).not.toBeInTheDocument();
  });
});
