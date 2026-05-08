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
    <html lang="en" className="dark h-full">
      <body className="min-h-full bg-background font-sans text-foreground antialiased">
        <LocaleProvider>
          <NavHeader />
          {children}
        </LocaleProvider>
      </body>
    </html>
  );
}
