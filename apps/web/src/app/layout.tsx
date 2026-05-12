import type { Metadata } from "next";
import "./globals.css";
import { LocaleProvider } from "@/lib/locale-context";
import { NavHeader } from "@/components/nav-header";

export const metadata: Metadata = {
  title: "Livermore",
  description: "AI-powered investment strategy research and backtesting workspace.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full bg-background font-sans text-foreground antialiased">
        <LocaleProvider>
          {/* Skip to main content — keyboard navigation accessibility */}
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-primary-foreground focus:shadow-lg"
          >
            Skip to main content
          </a>
          <NavHeader />
          <div id="main-content">{children}</div>
        </LocaleProvider>
      </body>
    </html>
  );
}
