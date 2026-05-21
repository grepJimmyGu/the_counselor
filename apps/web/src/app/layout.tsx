import type { Metadata } from "next";
import "./globals.css";
import { SessionProvider } from "next-auth/react";
import { LocaleProvider } from "@/lib/locale-context";
import { NavHeader } from "@/components/nav-header";
import { TrialBanner } from "@/components/TrialBanner";
import { UpgradeModal } from "@/components/UpgradeModal";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://livermorealpha.com";
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
        <SessionProvider>
        <LocaleProvider>
          {/* Skip to main content — keyboard navigation accessibility */}
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-primary-foreground focus:shadow-lg"
          >
            Skip to main content
          </a>
          <NavHeader />
          <TrialBanner />
          <div id="main-content">{children}</div>
          {/* Stage 3: mounted once; subscribes to 402 events from fetchApi */}
          <UpgradeModal />
        </LocaleProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
