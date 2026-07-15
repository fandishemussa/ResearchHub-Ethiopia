import { afterEach, describe, expect, it, vi } from "vitest";
import { searchSemanticPublications } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("searchSemanticPublications", () => {
  it("builds the supported query string and passes the abort signal", async () => {
    const signal = new AbortController().signal;
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          query: "crop health",
          model: "model",
          count: 0,
          results: [],
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await searchSemanticPublications({
      query: "crop health",
      limit: 20,
      source: "aau-etd",
      minSimilarity: 0.55,
      signal,
    });

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("q=crop+health");
    expect(url).toContain("limit=20");
    expect(url).toContain("source=aau-etd");
    expect(url).toContain("min_similarity=0.55");
    expect(options.signal).toBeInstanceOf(AbortSignal);
    expect(options.signal?.aborted).toBe(false);
    expect(response.count).toBe(0);
  });

  it("omits undefined filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          query: "health",
          model: "model",
          count: 0,
          results: [],
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    await searchSemanticPublications({ query: "health" });
    expect(fetchMock.mock.calls[0][0]).toMatch(/semantic\?q=health$/);
  });

  it("classifies validation, server, network, and aborted errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Invalid query" }), {
          status: 422,
        }),
      ),
    );
    await expect(
      searchSemanticPublications({ query: "x" }),
    ).rejects.toMatchObject({ kind: "validation", status: 422 });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("", { status: 500 })),
    );
    await expect(
      searchSemanticPublications({ query: "x" }),
    ).rejects.toMatchObject({ kind: "server", status: 500 });

    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(
      searchSemanticPublications({ query: "x" }),
    ).rejects.toMatchObject({ kind: "network" });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError")),
    );
    await expect(
      searchSemanticPublications({ query: "x" }),
    ).rejects.toMatchObject({ kind: "aborted" });
  });
});

describe("similarPublications", () => {
  it("uses the AI endpoint with supported filters and an abort signal", async () => {
    const signal = new AbortController().signal;
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          publication_id: "publication-id",
          model: "model",
          count: 0,
          results: [],
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { api } = await import("./api");
    await api.similarPublications(
      "publication-id",
      { limit: 6, minimumScore: 0.35 },
      signal,
    );

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/ai/publications/publication-id/similar?");
    expect(url).toContain("limit=6");
    expect(url).toContain("minimum_score=0.35");
    expect(options.signal).toBeInstanceOf(AbortSignal);
    expect(options.signal?.aborted).toBe(false);
  });
});

describe("deleteSource", () => {
  it("accepts an empty 204 response", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const { api } = await import("./api");
    await expect(api.deleteSource("source-id")).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/sources/source-id"),
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
