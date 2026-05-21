/**
 * Stage 5a — JSON-LD structured data renderer.
 *
 * Use sparingly. Each block emits a <script type="application/ld+json">
 * that Google + Bing parse for rich-result eligibility. Don't ship a block
 * that doesn't reflect actual page content — search engines penalize.
 *
 * Supported schemas:
 *   - SoftwareApplication: the Livermore app overall (only mount on `/`).
 *   - FAQPage: 3+ FAQ pairs (mount on landing pages with FAQ sections).
 *   - HowTo: stepwise instructions (mount on tutorial pages).
 *   - BreadcrumbList: navigation trail (mount on deep pages).
 */
import type { ReactElement } from "react";

interface FAQ {
  q: string;
  a: string;
}

interface BreadcrumbItem {
  name: string;
  url: string;
}

interface HowToStep {
  name: string;
  text: string;
}

export function SoftwareApplicationLd({
  name = "Livermore Alpha",
  url = "https://livermorealpha.com",
  description = "AI-powered investment strategy research and backtesting workspace.",
}: { name?: string; url?: string; description?: string } = {}): ReactElement {
  return (
    <script
      type="application/ld+json"
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{
        __html: JSON.stringify({
          "@context": "https://schema.org",
          "@type": "SoftwareApplication",
          name,
          url,
          description,
          applicationCategory: "FinanceApplication",
          operatingSystem: "Web",
          offers: {
            "@type": "Offer",
            price: "0",
            priceCurrency: "USD",
          },
        }),
      }}
    />
  );
}

export function FAQPageLd({ faqs }: { faqs: FAQ[] }): ReactElement {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{
        __html: JSON.stringify({
          "@context": "https://schema.org",
          "@type": "FAQPage",
          mainEntity: faqs.map((f) => ({
            "@type": "Question",
            name: f.q,
            acceptedAnswer: {
              "@type": "Answer",
              text: f.a,
            },
          })),
        }),
      }}
    />
  );
}

export function HowToLd({
  name,
  description,
  steps,
}: {
  name: string;
  description: string;
  steps: HowToStep[];
}): ReactElement {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{
        __html: JSON.stringify({
          "@context": "https://schema.org",
          "@type": "HowTo",
          name,
          description,
          step: steps.map((s, i) => ({
            "@type": "HowToStep",
            position: i + 1,
            name: s.name,
            text: s.text,
          })),
        }),
      }}
    />
  );
}

export function BreadcrumbListLd({ items }: { items: BreadcrumbItem[] }): ReactElement {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{
        __html: JSON.stringify({
          "@context": "https://schema.org",
          "@type": "BreadcrumbList",
          itemListElement: items.map((item, i) => ({
            "@type": "ListItem",
            position: i + 1,
            name: item.name,
            item: item.url,
          })),
        }),
      }}
    />
  );
}
