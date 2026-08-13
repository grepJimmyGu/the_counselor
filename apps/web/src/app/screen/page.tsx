import { Suspense } from "react";
import { QueryResults } from "@/components/screen/query-results";

/**
 * `/screen?q=...&universe=...` — where a query lands.
 *
 * Deliberately a separate route from `/stocks`, which stays the browse
 * surface (and the top nav's "Market Pulse" destination). Both lead to
 * `/stocks/[ticker]`; they answer different questions on the way there.
 */
export default async function ScreenPage({
  searchParams,
}: {
  // Next 16: searchParams is a Promise in server components.
  searchParams: Promise<{ q?: string; universe?: string; add?: string; template?: string }>;
}) {
  const { q, universe, add, template } = await searchParams;
  const query = (q ?? "").trim();
  const templateId = (template ?? "").trim();

  // A picked starting point carries its own rules, so it needs no query text.
  if (!query && !templateId) {
    return (
      <main className="mx-auto max-w-[1200px] px-6 py-12">
        <p className="text-sm text-muted-foreground">
          Nothing to screen — start from the search box on the home page.
        </p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background">
      <Suspense fallback={null}>
        <QueryResults
          query={query}
          universeId={universe || "sp500"}
          addParam={add ?? ""}
          templateId={templateId}
        />
      </Suspense>
    </main>
  );
}
