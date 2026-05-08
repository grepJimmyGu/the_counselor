import { Suspense } from "react";
import { ResearchWorkspace } from "@/components/workspace/research-workspace";

export default function Home() {
  return (
    <Suspense>
      <ResearchWorkspace />
    </Suspense>
  );
}
