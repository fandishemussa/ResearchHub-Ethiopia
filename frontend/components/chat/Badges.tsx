import { cn } from "@/lib/utils";
import type { GroundingStatus } from "@/lib/chat-types";

export function SourceBadge({ code }: { code?: string }) {
  const normalized = (code || "Other").toUpperCase();
  return (
    <span className="inline-flex rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-bold text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
      {normalized}
    </span>
  );
}

export function DocumentTypeBadge({ type }: { type?: string }) {
  return (
    <span className="inline-flex rounded-full bg-stone-100 px-2 py-0.5 text-[11px] capitalize text-stone-600 dark:bg-stone-800 dark:text-stone-300">
      {(type || "Research document").replaceAll("_", " ")}
    </span>
  );
}

export function GroundingBadge({ status }: { status: GroundingStatus }) {
  const label = {
    strong: "Strongly grounded",
    partial: "Partially grounded",
    insufficient: "Insufficient evidence",
  }[status];
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2 py-1 text-[11px] font-semibold",
        status === "strong" &&
          "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
        status === "partial" &&
          "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
        status === "insufficient" &&
          "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
      )}
    >
      {label}
    </span>
  );
}
