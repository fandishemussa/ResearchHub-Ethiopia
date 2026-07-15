import type { ResearchChatMessage } from "@/lib/chat-types";

export type ChatExportFormat = "markdown" | "text" | "bibtex" | "ris";

export function exportCurrentConversation(
  messages: ResearchChatMessage[],
  format: ChatExportFormat,
): void {
  const content = buildExport(messages, format);
  const extension =
    format === "markdown" ? "md" : format === "text" ? "txt" : format;
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `researchhub-conversation.${extension}`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function buildExport(
  messages: ResearchChatMessage[],
  format: ChatExportFormat,
): string {
  if (format === "bibtex") {
    return uniqueSources(messages)
      .map(
        (source, index) =>
          `@misc{researchhub${index + 1},\n  title = {${source.title}},\n  author = {${source.authors.join(" and ")}},\n  year = {${source.year ?? ""}},\n  url = {${source.landingUrl ?? source.documentUrl ?? ""}}\n}`,
      )
      .join("\n\n");
  }
  if (format === "ris") {
    return uniqueSources(messages)
      .map((source) =>
        [
          "TY  - GEN",
          `TI  - ${source.title}`,
          ...source.authors.map((author) => `AU  - ${author}`),
          source.year ? `PY  - ${source.year}` : "",
          `UR  - ${source.landingUrl ?? source.documentUrl ?? ""}`,
          "ER  -",
        ]
          .filter(Boolean)
          .join("\n"),
      )
      .join("\n\n");
  }
  return messages
    .map(
      (message) =>
        `${format === "markdown" ? `## ${message.role === "user" ? "Question" : "ResearchHub Assistant"}` : message.role.toUpperCase()}\n\n${message.content}`,
    )
    .join("\n\n");
}

function uniqueSources(messages: ResearchChatMessage[]) {
  const sources = messages.flatMap((message) => message.citations);
  return [
    ...new Map(
      sources.map((source) => [
        `${source.documentId}-${source.index}-${source.title}`,
        source,
      ]),
    ).values(),
  ];
}
