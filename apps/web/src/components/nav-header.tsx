"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Route } from "next";
import { LanguageSwitcher } from "@/components/language-switcher";
import { cn } from "@/lib/utils";

const navLink = (active: boolean) =>
  cn(
    "rounded-md px-3 py-1.5 text-sm transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
    active
      ? "bg-primary/10 text-primary font-medium"
      : "text-muted-foreground hover:text-foreground hover:bg-accent",
  );

export function NavHeader() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex h-12 w-full max-w-[1600px] items-center justify-between px-4 md:px-6 lg:px-8">

        <Link
          href="/"
          className="text-sm font-semibold tracking-tight text-foreground hover:text-primary transition-colors"
        >
          Livermore
        </Link>

        <div className="flex items-center gap-6">
          <nav aria-label="Main navigation" className="flex items-center gap-1">
            <Link href="/" className={navLink(pathname === "/")}>
              Workspace
            </Link>
            <Link href={"/templates" as Route} className={navLink(pathname.startsWith("/templates"))}>
              Research Templates
            </Link>
          </nav>
          <LanguageSwitcher />
        </div>

      </div>
    </header>
  );
}
