import { Suspense } from "react";
import { ResearchWorkspace } from "@/components/workspace/research-workspace";
import { ChatWidget } from "@/components/ChatWidget";

export default function WorkspacePage() {
  return (
    <Suspense>
      <ResearchWorkspace />
      {/* Stage 7 ticket #7: chat widget on workspace surface */}
      <ChatWidget />
    </Suspense>
  );
}
