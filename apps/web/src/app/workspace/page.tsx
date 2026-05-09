import { Suspense } from "react";
import { ResearchWorkspace } from "@/components/workspace/research-workspace";

export default function WorkspacePage() {
  return (
    <Suspense>
      <ResearchWorkspace />
    </Suspense>
  );
}
