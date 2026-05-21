import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";
import { notFound } from "next/navigation";
import { ArrowRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  BreadcrumbListLd,
  FAQPageLd,
  HowToLd,
} from "@/components/StructuredData";
import { SEO_TEMPLATES, findSeoTemplate } from "@/lib/seo-templates";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://livermorealpha.com";

/**
 * Stage 5a Phase 5 — SEO template landing pages.
 *
 * Static-generated from SEO_TEMPLATES (3 seed entries; 50 planned).
 * Each page renders intro/explanation/FAQs + JSON-LD (FAQPage, HowTo,
 * BreadcrumbList) + a prominent "Try it free" CTA.
 *
 * The "live backtest result" embed from the spec is deferred to a follow-up
 * — first we ship the static SEO foundation. The CTA points anonymous
 * visitors at /signup which preserves any ?via attribution.
 */

export function generateStaticParams() {
  return SEO_TEMPLATES.map((t) => ({ slug: t.slug }));
}

export async function generateMetadata(
  { params }: { params: Promise<{ slug: string }> },
): Promise<Metadata> {
  const { slug } = await params;
  const t = findSeoTemplate(slug);
  if (!t) return { title: "Template not found" };
  const url = `${SITE_URL}/templates/${t.slug}`;
  return {
    title: t.title,
    description: t.intro.slice(0, 160),
    alternates: { canonical: url },
    openGraph: {
      type: "article",
      url,
      title: t.title,
      description: t.intro.slice(0, 160),
      siteName: "Livermore Alpha",
      images: ["/og-default.png"],
    },
    twitter: {
      card: "summary_large_image",
      title: t.title,
      description: t.intro.slice(0, 160),
      images: ["/og-default.png"],
    },
    keywords: [t.primaryKw, ...t.secondaryKw],
  };
}

export default async function SeoTemplatePage(
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;
  const t = findSeoTemplate(slug);
  if (!t) return notFound();

  const breadcrumbs = [
    { name: "Home", url: SITE_URL },
    { name: "Templates", url: `${SITE_URL}/templates` },
    { name: t.h1, url: `${SITE_URL}/templates/${t.slug}` },
  ];

  const howToSteps = [
    { name: "Open the template", text: "Click 'Run free' below to open this template in the Livermore workspace." },
    { name: "Choose a ticker", text: `Default universe: ${t.defaultUniverse.join(", ")}. Swap to any S&P 500 ticker for free.` },
    { name: "Click Run", text: "The backtest runs on real Alpha Vantage price data and shows results in seconds." },
  ];

  return (
    <main className="min-h-screen bg-background">
      <FAQPageLd faqs={t.faqs} />
      <HowToLd name={t.h1} description={t.intro.slice(0, 160)} steps={howToSteps} />
      <BreadcrumbListLd items={breadcrumbs} />

      <article className="mx-auto max-w-3xl px-4 py-10 md:px-6 md:py-14">
        {/* Breadcrumb visual */}
        <nav className="text-xs text-muted-foreground" aria-label="Breadcrumb">
          <Link href={"/" as Route} className="hover:text-foreground">Home</Link>
          <span className="mx-1.5">/</span>
          <Link href={"/templates" as Route} className="hover:text-foreground">Templates</Link>
        </nav>

        {/* H1 + intro */}
        <header className="mt-3 space-y-3">
          <h1 className="font-heading text-3xl font-bold leading-tight sm:text-4xl">
            {t.h1}
          </h1>
          <p className="text-base text-muted-foreground">{t.intro}</p>
          <div className="flex flex-wrap items-center gap-2 pt-2">
            <Button asChild size="lg">
              <Link href={`/signup?template=${encodeURIComponent(t.slug)}` as Route}>
                Run this strategy free
                <ArrowRight className="ml-1.5 h-4 w-4" />
              </Link>
            </Button>
            <Badge variant="outline" className="font-normal">
              Default universe: {t.defaultUniverse.join(", ")}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            No credit card. One backtest per anonymous visitor. Sign up free for 5 weekly custom runs + unlimited templates.
          </p>
        </header>

        {/* How it works */}
        <section className="mt-10">
          <h2 className="text-xl font-semibold">How the strategy works</h2>
          <div className="mt-3 space-y-3 text-sm leading-relaxed text-foreground/90">
            {t.explanation.split("\n\n").map((para, i) => (
              <p key={i}>{para}</p>
            ))}
          </div>
        </section>

        {/* How to run it */}
        <section className="mt-10">
          <h2 className="text-xl font-semibold">How to run this on Livermore</h2>
          <ol className="mt-3 space-y-2 text-sm">
            {howToSteps.map((step, i) => (
              <li key={i} className="flex gap-3">
                <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                  {i + 1}
                </span>
                <div>
                  <p className="font-medium">{step.name}</p>
                  <p className="text-muted-foreground">{step.text}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        {/* Results interpretation */}
        <section className="mt-10">
          <h2 className="text-xl font-semibold">Reading the results</h2>
          <p className="mt-3 text-sm leading-relaxed text-foreground/90">
            {t.resultsSummary}
          </p>
        </section>

        {/* FAQ */}
        <section className="mt-10">
          <h2 className="text-xl font-semibold">FAQ</h2>
          <div className="mt-4 space-y-4">
            {t.faqs.map((f, i) => (
              <div key={i} className="rounded-lg border border-border bg-card p-4">
                <p className="text-sm font-semibold">{f.q}</p>
                <p className="mt-2 text-sm text-muted-foreground">{f.a}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Bottom CTA */}
        <section className="mt-12 rounded-xl border border-primary/30 bg-primary/5 p-6 text-center">
          <p className="text-base font-semibold">Ready to run it?</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Free to try. No credit card. Real market data.
          </p>
          <Button asChild size="lg" className="mt-4">
            <Link href={`/signup?template=${encodeURIComponent(t.slug)}` as Route}>
              Run this strategy free
              <ArrowRight className="ml-1.5 h-4 w-4" />
            </Link>
          </Button>
        </section>

        {/* Related */}
        {SEO_TEMPLATES.length > 1 && (
          <section className="mt-12">
            <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
              Other strategy templates
            </h2>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {SEO_TEMPLATES.filter((x) => x.slug !== t.slug).slice(0, 4).map((rel) => (
                <Link
                  key={rel.slug}
                  href={`/templates/${rel.slug}` as Route}
                  className="block rounded-lg border border-border bg-card p-3 text-sm transition-colors hover:border-primary/50"
                >
                  {rel.h1}
                </Link>
              ))}
            </div>
          </section>
        )}
      </article>
    </main>
  );
}
