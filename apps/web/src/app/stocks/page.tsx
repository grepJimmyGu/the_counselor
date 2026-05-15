import { Suspense } from "react";
import { MarketPulsePage } from "./_market-pulse";

export default function StocksPage() {
  return (
    <Suspense>
      <MarketPulsePage />
    </Suspense>
  );
}
