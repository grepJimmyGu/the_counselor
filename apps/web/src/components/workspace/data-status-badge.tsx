"use client";

import { useEffect, useState } from "react";

import { getDataStatus } from "@/lib/api";
import type { DataStatusResponse } from "@/lib/contracts";
import { Badge } from "@/components/ui/badge";
import { useLocale } from "@/lib/locale-context";

interface DataStatusBadgeProps {
  symbol: string;
}

export function DataStatusBadge({ symbol }: DataStatusBadgeProps) {
  const [status, setStatus] = useState<DataStatusResponse | null>(null);

  useEffect(() => {
    if (!symbol) return;
    setStatus(null);
    getDataStatus(symbol)
      .then(setStatus)
      .catch(() => setStatus(null));
  }, [symbol]);

  const { t } = useLocale();

  if (!status) return null;

  if (status.is_stale || status.bar_count === 0) {
    return (
      <Badge
        variant="destructive"
        title={t.staleTitle(status.bar_count)}
        className="text-[10px]"
      >
        {t.stale(symbol)}
      </Badge>
    );
  }

  return (
    <Badge
      variant="outline"
      title={t.barsTitle(status.bar_count, status.latest_date ?? "unknown")}
      className="text-[10px]"
    >
      {t.bars(symbol, status.bar_count)}
    </Badge>
  );
}
