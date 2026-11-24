import type { Metadata } from "next";
import "./globals.css";
import { SessionProvider } from "next-auth/react";
import { LocaleProvider } from "@/lib/locale-context";
import { Suspense } from "react";
import { AnalyticsProvider } from "@/components/AnalyticsProvider";
import { NavHeader } from "@/components/nav-header";
import { LiveTickerBar } from "@/components/LiveTickerBar";
import { TrialBanner } from "@/components/TrialBanner";
import { UpgradeModal } from "@/components/UpgradeModal";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://livermorealpha.com";

// How often an open, signed-in tab re-reads its session.
//
// next-auth's default is "on every tab re-focus", and each read is a Vercel
// function run. We turn that off (see <SessionProvider> below) and poll slowly
// instead, because the read is also what re-mints an ageing backend token
// (apps/api/CLAUDE.md trap #23) — a tab left open across the token's expiry
// must still get a fresh one without a reload. The token is re-minted once it
// is within 24h of `exp` (BACKEND_TOKEN_REFRESH_WINDOW_SECONDS), so 4h gives
// six chances inside that window. Anonymous visitors never poll: next-auth
// skips the read when there is no session.
const SESSION_REFETCH_INTERVAL_SECONDS = 4 * 60 * 60;
const SITE_DESCRIPTION =
  "AI-powered investment strategy research and backtesting workspace. " +
  "Run 22+ quant strategy templates on real market data. Free Scout tier.";

export const metadata: Metadata = {
  title: {
    default: "Livermore Alpha — AI investment strategy backtesting",
    template: "%s | Livermore Alpha",
  },
  description: SITE_DESCRIPTION,
  metadataBase: new URL(SITE_URL),
  applicationName: "Livermore Alpha",
  authors: [{ name: "Livermore" }],
  keywords: [
    "backtesting", "stock screener", "momentum strategy", "mean reversion",
    "factor investing", "quant research", "investment strategy", "trading",
  ],
  openGraph: {
    type: "website",
    url: SITE_URL,
    title: "Livermore Alpha — AI investment strategy backtesting",
    description: SITE_DESCRIPTION,
    siteName: "Livermore Alpha",
    images: ["/og-default.png"],
  },
  twitter: {
    card: "summary_large_image",
    title: "Livermore Alpha — AI investment strategy backtesting",
    description: SITE_DESCRIPTION,
    images: ["/og-default.png"],
  },
  robots: {
    index: true,
    follow: true,
  },
  viewport: {
    width: "device-width",
    initialScale: 1,
    maximumScale: 1,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full bg-background font-sans text-foreground antialiased overscroll-y-none">
        <SessionProvider
          refetchOnWindowFocus={false}
          refetchInterval={SESSION_REFETCH_INTERVAL_SECONDS}
        >
        <LocaleProvider>
          {/* Skip to main content — keyboard navigation accessibility */}
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-primary-foreground focus:shadow-lg"
          >
            Skip to main content
          </a>
          <NavHeader />
          <LiveTickerBar />
          <TrialBanner />
          <div id="main-content">{children}</div>
          {/* Stage 3: mounted once; subscribes to 402 events from fetchApi */}
          <UpgradeModal />
          {/* Stage 6a: subscribes to session + pathname; fires identify/page_view.
              Wrapped in Suspense because AnalyticsProvider uses useSearchParams
              and would otherwise bail Next.js prerender (KNOWN_ISSUES rule #7-ish). */}
          <Suspense fallback={null}>
            <AnalyticsProvider />
          </Suspense>
        </LocaleProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
