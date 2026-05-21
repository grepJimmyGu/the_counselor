import type { MetadataRoute } from "next";

import { SEO_TEMPLATES } from "@/lib/seo-templates";

/**
 * Stage 5a — sitemap.
 *
 * Lists the public, indexable surfaces:
 *   - Marketing routes (/, /pricing, /community)
 *   - SEO template landing pages (50 planned; 3 shipped in Stage 5a Phase 5)
 *
 * Private routes (/workspace, /account, /admin) are EXCLUDED here AND
 * disallowed in robots.txt — belt + suspenders.
 */
const BASE = process.env.NEXT_PUBLIC_SITE_URL ?? "https://livermorealpha.com";


export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return [
    { url: `${BASE}/`,           lastModified: now, changeFrequency: "weekly",  priority: 1.0 },
    { url: `${BASE}/pricing`,    lastModified: now, changeFrequency: "monthly", priority: 0.9 },
    { url: `${BASE}/community`,  lastModified: now, changeFrequency: "daily",   priority: 0.8 },
    { url: `${BASE}/templates`,  lastModified: now, changeFrequency: "weekly",  priority: 0.8 },
    { url: `${BASE}/stocks`,     lastModified: now, changeFrequency: "daily",   priority: 0.7 },
    { url: `${BASE}/sentiment`,  lastModified: now, changeFrequency: "daily",   priority: 0.6 },
    ...SEO_TEMPLATES.map((t) => ({
      url: `${BASE}/templates/${t.slug}`,
      lastModified: new Date(t.lastModified),
      changeFrequency: "weekly" as const,
      priority: 0.6,
    })),
  ];
}
