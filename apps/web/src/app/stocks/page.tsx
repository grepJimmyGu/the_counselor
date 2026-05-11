import { Suspense } from "react";
import { StocksPageInner } from "./_page-inner";

export default function StocksPage() {
  return (
    <Suspense>
      <StocksPageInner />
    </Suspense>
  );
}
