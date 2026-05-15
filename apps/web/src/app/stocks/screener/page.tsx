import { Suspense } from "react";
import { StocksPageInner } from "../_page-inner";

export default function ScreenerPage() {
  return (
    <Suspense>
      <StocksPageInner />
    </Suspense>
  );
}
