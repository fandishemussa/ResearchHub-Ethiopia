import { ResearchChatPage } from "@/components/chat/ResearchChatPage";
import type { InitialChatScope } from "@/hooks/useResearchChat";

export function ResearchAssistant({
  initialScope,
}: {
  initialScope: InitialChatScope;
}) {
  return <ResearchChatPage initialScope={initialScope} />;
}
