export type SearchEventName =
  | "semantic_search_submitted"
  | "semantic_result_opened"
  | "semantic_result_link_copied"
  | "semantic_filter_changed"
  | "semantic_no_results"
  | "semantic_search_error";

export function trackSearchEvent(
  name: SearchEventName,
  detail: Record<string, unknown> = {},
): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent("researchhub:analytics", { detail: { name, ...detail } }),
  );
}
