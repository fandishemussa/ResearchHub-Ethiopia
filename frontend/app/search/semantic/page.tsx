import { Suspense } from "react";
import { SemanticSearchPage } from "@/components/semantic-search-page";
import { Skeleton } from "@/components/ui";

export const metadata = {
  title: "Semantic Search",
  description:
    "Discover Ethiopian academic research using natural-language semantic search.",
};

export default function Page() {
  return (
    <Suspense
      fallback={
        <div className="space-y-5">
          <Skeleton className="h-24 w-3/4" />
          <Skeleton className="h-32" />
          <Skeleton className="h-80" />
        </div>
      }
    >
      <SemanticSearchPage />
    </Suspense>
  );
}
