import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SemanticSearchResultCard } from "./semantic-result-card";

const result = {
  id: "publication-1",
  title: "Drought-resistant sorghum in Ethiopia",
  abstract_preview: "A study of resilient varieties.",
  publication_year: 2024,
  source: "aau-etd",
  article_url: "https://example.org/item/1",
  similarity: 0.834,
};

describe("SemanticSearchResultCard", () => {
  beforeEach(() =>
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    }),
  );

  it("renders publication metadata and accessible external-link behavior", () => {
    render(<SemanticSearchResultCard result={result} />);
    expect(
      screen.getByRole("heading", { name: result.title }),
    ).toBeInTheDocument();
    expect(screen.getByText("2024")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "83",
    );
    expect(
      screen.getByRole("link", { name: /View publication/ }),
    ).toHaveAttribute("target", "_blank");
  });

  it("copies the publication link", async () => {
    render(<SemanticSearchResultCard result={result} />);
    await userEvent.click(
      screen.getByRole("button", { name: /Copy link for/ }),
    );
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      result.article_url,
    );
    expect(screen.getByText("Copied")).toBeInTheDocument();
  });

  it("handles missing year and URL", () => {
    render(
      <SemanticSearchResultCard
        result={{ ...result, publication_year: null, article_url: null }}
      />,
    );
    expect(screen.getByText("Year unavailable")).toBeInTheDocument();
    expect(screen.getByText("Link unavailable")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Copy link for/ }),
    ).toBeDisabled();
  });

  it("rejects unsafe URLs and formats invalid similarity safely", () => {
    render(
      <SemanticSearchResultCard
        result={{
          ...result,
          article_url: "javascript:alert(1)",
          similarity: Number.NaN,
        }}
      />,
    );
    expect(
      screen.queryByRole("link", { name: /View publication/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "0",
    );
  });
});
