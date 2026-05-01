"use client";

import { useEffect, useState } from "react";

import { getDataStatus } from "@/lib/api";
import type { DataStatusResponse } from "@/lib/contracts";
import { Badge } from "@/components/ui/badge";

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

  if (!status) return null;

  if (status.is_stale || status.bar_count === 0) {
    return (
      <Badge
        variant="destructive"
        title={`${status.bar_count} bars — stale or missing`}
        className="text-[10px]"
      >
        {symbol} stale
      </Badge>
    );
  }

  return (
    <Badge
      variant="outline"
      title={`${status.bar_count} bars through ${status.latest_date ?? "unknown"}`}
      className="text-[10px]"
    >
      {symbol} {status.bar_count}d
    </Badge>
  );
}
