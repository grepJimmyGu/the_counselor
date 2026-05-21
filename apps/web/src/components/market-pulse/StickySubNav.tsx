"use client";

/**
 * Mobile-only sticky sub-nav for Market Pulse v2.
 *
 * Sits below the global app nav header. Anchor chips scroll-to the
 * section IDs (`#brief`, `#indices`, `#sectors`, `#macro`, `#movers`).
 * Hides on `md` and above — desktop sections are short enough that
 * vertical scroll alone is fine.
 */

const ANCHORS: { id: string; label: string }[] = [
  { id: "brief", label: "Brief" },
  { id: "indices", label: "Indices" },
  { id: "sectors", label: "Sectors" },
  { id: "macro", label: "Macro" },
  { id: "movers", label: "Movers" },
];

export function StickySubNav() {
  return (
    <nav
      aria-label="Market Pulse sections"
      className="sticky top-0 z-30 md:hidden border-b border-border/60 bg-white/85 backdrop-blur-sm -mx-4 px-4"
    >
      <div className="flex gap-2 overflow-x-auto py-2 scrollbar-hide">
        {ANCHORS.map((a) => (
          <a
            key={a.id}
            href={`#${a.id}`}
            className="shrink-0 rounded-full border border-border bg-white px-3 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted/40"
          >
            {a.label}
          </a>
        ))}
      </div>
    </nav>
  );
}
