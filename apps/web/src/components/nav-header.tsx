"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";
import type { Route } from "next";
import { LanguageSwitcher } from "@/components/language-switcher";
import { useLocale } from "@/lib/locale-context";
import { cn } from "@/lib/utils";

const navLink = (active: boolean) =>
  cn(
    "rounded-md px-3 py-1.5 text-sm transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
    active
      ? "bg-primary/10 text-primary font-medium"
      : "text-muted-foreground hover:text-foreground hover:bg-accent",
  );

const mobileNavLink = (active: boolean) =>
  cn(
    "block rounded-md px-3 py-2.5 text-sm font-medium transition-colors",
    active
      ? "bg-primary/10 text-primary"
      : "text-muted-foreground hover:text-foreground hover:bg-accent",
  );

export function NavHeader() {
  const pathname = usePathname();
  const { t } = useLocale();
  const [open, setOpen] = useState(false);

  const links = [
    { href: "/", label: t.navHome, exact: true },
    { href: "/workspace", label: t.navWorkspace },
    { href: "/stocks", label: t.navStocks },
    { href: "/sentiment", label: "Sentiment" },
    { href: "/templates", label: t.navTemplates },
  ];

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex h-12 w-full max-w-[1600px] items-center justify-between px-4 md:px-6 lg:px-8">

        <Link
          href="/"
          className="text-sm font-semibold tracking-tight text-foreground hover:text-primary transition-colors"
        >
          Livermore
        </Link>

        {/* Desktop nav */}
        <div className="hidden md:flex items-center gap-6">
          <nav aria-label="Main navigation" className="flex items-center gap-1">
            {links.map(({ href, label, exact }) => (
              <Link
                key={href}
                href={href as Route}
                className={navLink(exact ? pathname === href : pathname.startsWith(href))}
              >
                {label}
              </Link>
            ))}
          </nav>
          <LanguageSwitcher />
        </div>

        {/* Mobile hamburger */}
        <button
          className="md:hidden rounded-md p-1.5 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          onClick={() => setOpen((v) => !v)}
          aria-label="Toggle menu"
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {/* Mobile dropdown */}
      {open && (
        <div className="md:hidden border-t border-border bg-background/95 px-4 pb-4 pt-2 backdrop-blur">
          <nav className="flex flex-col gap-1">
            {links.map(({ href, label, exact }) => (
              <Link
                key={href}
                href={href as Route}
                className={mobileNavLink(exact ? pathname === href : pathname.startsWith(href))}
                onClick={() => setOpen(false)}
              >
                {label}
              </Link>
            ))}
          </nav>
          <div className="mt-3 border-t border-border pt-3">
            <LanguageSwitcher />
          </div>
        </div>
      )}
    </header>
  );
}
