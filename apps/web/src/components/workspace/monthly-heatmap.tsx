import type { BacktestResult } from "@/lib/contracts";
import { useLocale } from "@/lib/locale-context";

function colorForValue(value: number) {
  if (value > 0.08) return "bg-emerald-500/30 text-emerald-900 font-semibold";
  if (value > 0.02) return "bg-emerald-500/18 text-emerald-800";
  if (value > 0) return "bg-emerald-500/10 text-emerald-700";
  if (value > -0.05) return "bg-rose-500/12 text-rose-700";
  return "bg-rose-500/28 text-rose-900 font-semibold";
}

export function MonthlyHeatmap({ result }: { result: BacktestResult }) {
  const { t } = useLocale();
  const monthLabels = t.months;
  const grouped = new Map<number, Map<number, number>>();

  result.monthly_returns.forEach((item) => {
    if (!grouped.has(item.year)) {
      grouped.set(item.year, new Map<number, number>());
    }
    grouped.get(item.year)?.set(item.month, item.return_pct);
  });

  return (
    <div className="overflow-x-auto">
      <div className="grid min-w-[720px] grid-cols-[80px_repeat(12,minmax(0,1fr))] gap-2 text-sm font-medium">
        <div />
        {monthLabels.map((label) => (
          <div key={label} className="text-center text-muted-foreground">
            {label}
          </div>
        ))}
        {[...grouped.entries()].map(([year, values]) => (
          <div key={year} className="contents">
            <div className="flex items-center text-muted-foreground">{year}</div>
            {monthLabels.map((_, index) => {
              const value = values.get(index + 1);
              return (
                <div
                  key={`${year}-${index + 1}`}
                  className={`flex h-10 items-center justify-center rounded-md border border-border text-sm ${
                    value === undefined ? "bg-muted/40 text-muted-foreground" : colorForValue(value)
                  }`}
                >
                  {value === undefined ? "—" : `${(value * 100).toFixed(1)}%`}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

