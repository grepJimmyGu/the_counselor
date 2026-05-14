"use client";

import { CircleHelp } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface MetricLabelProps {
  label: string;
  tooltip: string;
  className?: string;
  labelClassName?: string;
}

/**
 * PRD-08c: Metric label with hover tooltip (ⓘ icon).
 * Usage: <MetricLabel label="Piotroski F-Score" tooltip="The Piotroski..." />
 * Renders: "Piotroski F-Score ⓘ" — ⓘ triggers tooltip on hover.
 */
export function MetricLabel({ label, tooltip, className, labelClassName }: MetricLabelProps) {
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={cn(
              "inline-flex cursor-help items-center gap-1",
              className
            )}
          >
            <span className={labelClassName}>{label}</span>
            <CircleHelp className="h-3 w-3 shrink-0 text-muted-foreground/60" />
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[260px] leading-relaxed">
          {tooltip}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
