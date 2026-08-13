"use client";

/**
 * Home block 4 — example queries (老股民都愛這麼問).
 *
 * Clicking a query does NOT navigate to results. It writes the text into the
 * search box, scrolls there, and submits. That's the whole point: the user
 * watches their question appear as a typed query, so next time they type their
 * own variant. Jumping straight to results answers one question and teaches
 * nothing.
 *
 * Every string here is verified to PARSE — `tests/test_home_example_queries.py`
 * runs each one through the same extractors the box uses on submit. An example
 * query that falls through to the LLM (which interrogates instead of screening)
 * is worse than no example at all, and three of the first four candidates did
 * exactly that.
 *
 * Tabs are a 4/3/2 grouping of our nine `IntentGroup`s rather than 問財's
 * 技術面/資金面/基本面. A literal translation would put six groups under
 * "technical" and exactly one under "money flow", so that tab would read empty.
 */

import { useState } from "react";
import { RUN_QUERY_EVENT } from "@/components/search/smart-search-box";

interface QueryTab {
  id: string;
  label: string;
  /** The `IntentGroup`s this tab covers — the mapping is the rationale. */
  intents: string[];
  queries: string[];
}

/**
 * DRAFT COPY — Jimmy owns these strings.
 *
 * These are placeholders chosen because they parse today, not because they're
 * how a trader would phrase it. 問財's equivalent block works because the
 * questions sound like someone talking; that voice has to come from Jimmy and
 * his users. Swapping a string is a one-line edit — but keep the contract test
 * passing, or the block will show a query that silently doesn't work.
 */
const TABS: QueryTab[] = [
  {
    id: "trend",
    label: "Trend & momentum",
    intents: ["trend", "momentum", "relative_strength", "breakout"],
    queries: [
      "above the 200-day moving average",
      "golden cross",
      "MACD crossing up",
      "strong trend and above the 50-day",
    ],
  },
  {
    id: "reversal",
    label: "Reversals & volatility",
    intents: ["overbought_oversold", "volatility", "volume"],
    queries: [
      "oversold",
      "overbought",
      "bollinger squeeze",
      "RSI below 30 and above the 200-day",
    ],
  },
  {
    id: "fundamentals",
    label: "Fundamentals & events",
    intents: ["value_quality", "sentiment_events"],
    queries: [
      "p/e under 15",
      "dividend yield above 4%",
      "healthcare small caps",
      "large caps with dividend yield above 3%",
      "insider buying",
    ],
  },
];

function runQuery(text: string) {
  window.dispatchEvent(new CustomEvent(RUN_QUERY_EVENT, { detail: text }));
}

export function HomeExampleQueries() {
  const [active, setActive] = useState(TABS[0].id);
  const tab = TABS.find((t) => t.id === active) ?? TABS[0];

  return (
    <section
      className="rounded-xl border border-border bg-white p-4"
      data-testid="home-example-queries"
    >
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-heading text-base font-semibold">Traders ask</h2>
        {/* Segmented control on the heading line rather than its own row —
            the block is four questions tall, so a row spent on tabs is
            expensive. */}
        <div className="flex flex-wrap items-center gap-0.5 rounded-full bg-muted/50 p-0.5">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setActive(t.id)}
              data-testid={`query-tab-${t.id}`}
              aria-pressed={t.id === active}
              className={
                t.id === active
                  ? "cursor-pointer rounded-full bg-white px-2.5 py-1 text-xs font-medium text-foreground shadow-sm"
                  : "cursor-pointer rounded-full px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
              }
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Chips sized to their text, wrapping — not full-width rows. Each row
          held ~30 characters in a ~568px column, so most of this block was
          empty background. */}
      <div className="flex flex-wrap gap-1.5">
        {tab.queries.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => runQuery(q)}
            data-testid="example-query"
            className="cursor-pointer rounded-full border border-border bg-muted/30 px-3 py-1.5 text-left text-xs transition-colors hover:border-primary/40 hover:bg-muted"
          >
            {q}
          </button>
        ))}
      </div>

      <p className="mt-2.5 text-[11px] text-muted-foreground">
        Runs in the search box above — edit it and try your own.
      </p>

    </section>
  );
}

/** Exported for the contract test, which asserts every string parses. */
export const EXAMPLE_QUERIES = TABS.flatMap((t) => t.queries);
