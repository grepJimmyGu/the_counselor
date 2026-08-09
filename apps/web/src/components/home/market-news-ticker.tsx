"use client";

/**
 * Market news strip for the bottom of the "Traders ask" block (item B).
 *
 * Scrolls continuously via a CSS animation over a duplicated list — the usual
 * marquee trick, and the reason the content appears twice in the DOM. A
 * JS-driven scroll would fight the main thread on a page that is already
 * fetching four blocks.
 *
 * Three things this deliberately does:
 *
 * - **Pauses on hover and on focus.** Auto-scrolling text that can't be
 *   stopped is unreadable and unclickable; you can never quite land on the
 *   headline you wanted.
 * - **Honours `prefers-reduced-motion`.** Continuous motion is a genuine
 *   accessibility problem, not a preference. Reduced-motion users get a
 *   static, scrollable row with every headline still reachable.
 * - **Shows how old the feed is.** The server caches 15 minutes, so implying
 *   "live" would be a small lie told constantly.
 */

import { useEffect, useState } from "react";
import { getMarketNews } from "@/lib/api";
import type { MarketNewsArticle } from "@/lib/contracts";

/** Enough to fill the strip without making one loop take a minute. */
const ARTICLE_COUNT = 12;
/** Seconds for one full pass. Slow enough to read a headline as it goes by. */
const SCROLL_SECONDS = 90;

function freshness(ageSeconds: number): string {
  const m = Math.round(ageSeconds / 60);
  if (m < 1) return "just now";
  if (m === 1) return "1 min ago";
  return `${m} min ago`;
}

function Headline({ a }: { a: MarketNewsArticle }) {
  const body = (
    <>
      {a.source_name && (
        <span className="text-muted-foreground/70">{a.source_name} · </span>
      )}
      {a.title}
    </>
  );
  return (
    <span className="mx-4 inline-flex shrink-0 items-center text-xs" data-testid="news-headline">
      <span className="mr-3 text-muted-foreground/40" aria-hidden="true">
        •
      </span>
      {a.url ? (
        <a
          href={a.url}
          target="_blank"
          rel="noopener noreferrer"
          className="transition-colors hover:text-primary hover:underline"
        >
          {body}
        </a>
      ) : (
        <span>{body}</span>
      )}
    </span>
  );
}

export function MarketNewsTicker() {
  const [articles, setArticles] = useState<MarketNewsArticle[]>([]);
  const [age, setAge] = useState(0);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    // try/catch rather than a `.catch()` tail: the rejection is then handled
    // inside the same synchronous frame that awaited it, so there is no window
    // in which the promise looks unhandled.
    (async () => {
      try {
        const d = await getMarketNews(ARTICLE_COUNT);
        if (!live) return;
        setArticles(d.articles ?? []);
        setAge(d.age_seconds ?? 0);
      } catch {
        if (live) setFailed(true);
      }
    })();
    return () => {
      live = false;
    };
  }, []);

  // A strip that renders an empty bar is worse than no strip.
  if (failed || articles.length === 0) return null;

  return (
    <div className="mt-3 border-t border-border pt-2" data-testid="market-news-ticker">
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Market news
        </span>
        <span className="text-[11px] text-muted-foreground/70">{freshness(age)}</span>
      </div>

      {/* group/ticker so hover anywhere on the strip pauses it, not just on a
          headline — otherwise the text slides out from under the cursor. */}
      <div className="group/ticker relative overflow-x-auto whitespace-nowrap motion-safe:overflow-hidden">
        <div className="inline-flex motion-safe:animate-[ticker_var(--ticker-duration)_linear_infinite] motion-safe:group-hover/ticker:[animation-play-state:paused] motion-safe:group-focus-within/ticker:[animation-play-state:paused]"
             style={{ ["--ticker-duration" as string]: `${SCROLL_SECONDS}s` }}>
          {articles.map((a, i) => (
            <Headline key={`a-${i}`} a={a} />
          ))}
          {/* Second copy: the animation translates by exactly -50%, so the
              list appears seamless rather than snapping back at the end.
              Hidden from assistive tech — the headlines are already announced
              once, and a screen reader shouldn't read the feed twice. */}
          <span aria-hidden="true" className="inline-flex">
            {articles.map((a, i) => (
              <Headline key={`b-${i}`} a={a} />
            ))}
          </span>
        </div>
      </div>
    </div>
  );
}
