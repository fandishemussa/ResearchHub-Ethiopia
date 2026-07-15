import type { ReactNode } from "react";
import type { ChatSource } from "@/lib/chat-types";
import { safeHttpUrl } from "@/lib/urls";

export function MarkdownContent({
  content,
  citations,
  onCitation,
}: {
  content: string;
  citations: ChatSource[];
  onCitation: (citation: ChatSource) => void;
}) {
  const lines = content.split("\n");
  const nodes: ReactNode[] = [];
  let code: string[] = [];
  let inCode = false;
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.startsWith("```")) {
      if (inCode) {
        nodes.push(
          <pre
            key={`code-${index}`}
            className="my-3 overflow-x-auto rounded-xl bg-stone-950 p-4 text-xs text-stone-100"
          >
            <code>{code.join("\n")}</code>
          </pre>,
        );
        code = [];
      }
      inCode = !inCode;
      continue;
    }
    if (inCode) {
      code.push(line);
      continue;
    }
    if (!line.trim()) {
      nodes.push(<div key={`space-${index}`} className="h-2" />);
    } else if (line.startsWith("### ")) {
      nodes.push(
        <h4 key={index} className="mt-4 font-serif text-base font-bold">
          {inline(line.slice(4), citations, onCitation)}
        </h4>,
      );
    } else if (line.startsWith("## ")) {
      nodes.push(
        <h3 key={index} className="mt-5 font-serif text-lg font-bold">
          {inline(line.slice(3), citations, onCitation)}
        </h3>,
      );
    } else if (line.startsWith("# ")) {
      nodes.push(
        <h2 key={index} className="mt-5 font-serif text-xl font-bold">
          {inline(line.slice(2), citations, onCitation)}
        </h2>,
      );
    } else if (/^[-*] /.test(line)) {
      nodes.push(
        <div key={index} className="ml-4 flex gap-2">
          <span aria-hidden>•</span>
          <span>{inline(line.slice(2), citations, onCitation)}</span>
        </div>,
      );
    } else if (/^\d+\. /.test(line)) {
      const marker = line.match(/^\d+\./)?.[0];
      nodes.push(
        <div key={index} className="ml-4 flex gap-2">
          <span>{marker}</span>
          <span>
            {inline(
              line.slice((marker?.length || 1) + 1),
              citations,
              onCitation,
            )}
          </span>
        </div>,
      );
    } else if (line.startsWith("> ")) {
      nodes.push(
        <blockquote
          key={index}
          className="my-3 border-l-4 border-emerald-600 pl-3 italic text-stone-600 dark:text-stone-300"
        >
          {inline(line.slice(2), citations, onCitation)}
        </blockquote>,
      );
    } else if (
      line.includes("|") &&
      index + 1 < lines.length &&
      /^\s*\|?[-: |]+\|?\s*$/.test(lines[index + 1])
    ) {
      const headers = cells(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].includes("|")) {
        rows.push(cells(lines[index]));
        index += 1;
      }
      index -= 1;
      nodes.push(
        <div key={`table-${index}`} className="my-3 overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr>
                {headers.map((cell, cellIndex) => (
                  <th
                    key={cellIndex}
                    className="border border-stone-300 p-2 dark:border-stone-700"
                  >
                    {inline(cell, citations, onCitation)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td
                      key={cellIndex}
                      className="border border-stone-300 p-2 align-top dark:border-stone-700"
                    >
                      {inline(cell, citations, onCitation)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
    } else {
      nodes.push(
        <p key={index} className="leading-7">
          {inline(line, citations, onCitation)}
        </p>,
      );
    }
  }
  return <div className="text-sm">{nodes}</div>;
}

function inline(
  text: string,
  citations: ChatSource[],
  onCitation: (citation: ChatSource) => void,
): ReactNode[] {
  return text
    .split(/(\[\d+\]|\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`)/g)
    .filter(Boolean)
    .map((part, index) => {
      const citationMatch = part.match(/^\[(\d+)\]$/);
      if (citationMatch) {
        const citation = citations.find(
          (item) => item.index === Number(citationMatch[1]),
        );
        return citation ? (
          <button
            key={index}
            type="button"
            onClick={() => onCitation(citation)}
            className="mx-0.5 rounded bg-emerald-100 px-1 font-semibold text-emerald-900 hover:bg-emerald-200 focus:outline-none focus:ring-2 focus:ring-emerald-600 dark:bg-emerald-950 dark:text-emerald-200"
          >
            {part}
          </button>
        ) : (
          part
        );
      }
      const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (link) {
        const url = safeHttpUrl(link[2]);
        return url ? (
          <a
            key={index}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-emerald-700 underline dark:text-emerald-300"
          >
            {link[1]}
            <span className="sr-only"> opens in a new tab</span>
          </a>
        ) : (
          link[1]
        );
      }
      if (part.startsWith("**") && part.endsWith("**"))
        return <strong key={index}>{part.slice(2, -2)}</strong>;
      if (part.startsWith("`") && part.endsWith("`"))
        return (
          <code
            key={index}
            className="rounded bg-stone-200 px-1 dark:bg-stone-700"
          >
            {part.slice(1, -1)}
          </code>
        );
      return part;
    });
}

function cells(line: string): string[] {
  return line
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((item) => item.trim());
}
