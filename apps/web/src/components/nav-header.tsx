"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession, signIn, signOut } from "next-auth/react";
import type { Route } from "next";
import { LogIn, LogOut, User, Menu, X, BookmarkCheck } from "lucide-react";
import { LanguageSwitcher } from "@/components/language-switcher";
import { QuotaBadge } from "@/components/QuotaBadge";
import { useLocale } from "@/lib/locale-context";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const navLink = (active: boolean) =>
  cn(
    "rounded-md px-3 py-1.5 text-sm transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
    active
      ? "bg-primary/10 text-primary font-medium"
      : "text-muted-foreground hover:text-foreground hover:bg-accent",
  );

const mobileNavLink = (active: boolean) =>
  cn(
    "flex items-center rounded-lg px-4 py-3 text-sm font-medium transition-colors duration-200 min-h-[44px] touch-manipulation",
    active
      ? "bg-primary/10 text-primary"
      : "text-foreground hover:bg-accent hover:text-foreground",
  );

function UserMenu() {
  const { data: session, status } = useSession();

  if (status === "loading") {
    return <div className="h-8 w-8 animate-pulse rounded-full bg-muted" />;
  }

  if (!session?.user) {
    return (
      <Button
        variant="outline"
        size="sm"
        className="gap-1.5 text-xs min-h-[36px] touch-manipulation"
        onClick={() => signIn()}
      >
        <LogIn className="h-3.5 w-3.5" />
        Sign in
      </Button>
    );
  }

  const user = session.user;
  const initials = (user.name ?? user.email ?? "?")
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="flex h-9 w-9 cursor-pointer items-center justify-center overflow-hidden rounded-full border border-border bg-primary/10 text-xs font-semibold text-primary transition-colors hover:bg-primary/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring touch-manipulation"
          aria-label="User menu"
        >
          {user.image ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={user.image} alt={user.name ?? "avatar"} className="h-full w-full object-cover" />
          ) : (
            initials
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <div className="px-3 py-2">
          <p className="text-sm font-medium truncate">{user.name ?? "User"}</p>
          <p className="text-xs text-muted-foreground truncate">{user.email}</p>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href={"/account" as Route} className="cursor-pointer min-h-[44px]">
            <User className="mr-2 h-3.5 w-3.5" />
            Account
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link
            href={"/account/strategies" as Route}
            data-testid="user-menu-my-strategies"
            className="cursor-pointer min-h-[44px]"
          >
            <BookmarkCheck className="mr-2 h-3.5 w-3.5" />
            My Strategies
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={() => signOut({ callbackUrl: "/" })}
          className="cursor-pointer text-destructive focus:text-destructive min-h-[44px]"
        >
          <LogOut className="mr-2 h-3.5 w-3.5" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function NavHeader() {
  const pathname = usePathname();
  const { t } = useLocale();
  const [mobileOpen, setMobileOpen] = useState(false);

  const NAV_LINKS = [
    { href: "/",           label: t.navHome,          match: (p: string) => p === "/" },
    { href: "/stocks",     label: "Market Pulse",     match: (p: string) => p.startsWith("/stocks") || p.startsWith("/commodities") },
    { href: "/sentiment",  label: "Sentiment",        match: (p: string) => p.startsWith("/sentiment") },
    { href: "/community",  label: "Community",        match: (p: string) => p.startsWith("/community") },
    { href: "/templates",  label: "Strategy Builder", match: (p: string) => p.startsWith("/templates") || p.startsWith("/workspace") },
  ] as const;

  return (
    <>
      <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="mx-auto flex h-12 w-full max-w-[1600px] items-center justify-between px-4 md:px-6 lg:px-8">

          {/* Logo */}
          <Link
            href="/"
            className="text-base font-semibold tracking-tight text-foreground hover:text-primary transition-colors"
          >
            Livermore
          </Link>

          {/* Desktop nav */}
          <div className="hidden md:flex items-center gap-4">
            <nav aria-label="Main navigation" className="flex items-center gap-1">
              {NAV_LINKS.map(({ href, label, match }) => (
                <Link key={href} href={href as Route} className={navLink(match(pathname))}>
                  {label}
                </Link>
              ))}
            </nav>
            <div className="flex items-center gap-2">
              <QuotaBadge />
              <LanguageSwitcher />
              <UserMenu />
            </div>
          </div>

          {/* Mobile right: user + hamburger */}
          <div className="flex md:hidden items-center gap-2">
            <UserMenu />
            <button
              onClick={() => setMobileOpen((v) => !v)}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-background text-foreground transition-colors hover:bg-accent touch-manipulation cursor-pointer"
              aria-label={mobileOpen ? "Close menu" : "Open menu"}
              aria-expanded={mobileOpen}
            >
              {mobileOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>
          </div>

        </div>

        {/* Mobile drawer */}
        {mobileOpen && (
          <div className="md:hidden border-t border-border bg-background/98 backdrop-blur">
            <nav aria-label="Mobile navigation" className="flex flex-col px-3 py-3 gap-1">
              {NAV_LINKS.map(({ href, label, match }) => (
                <Link
                  key={href}
                  href={href as Route}
                  className={mobileNavLink(match(pathname))}
                  onClick={() => setMobileOpen(false)}
                >
                  {label}
                </Link>
              ))}
              <div className="pt-2 border-t border-border/60 mt-1">
                <LanguageSwitcher />
              </div>
            </nav>
          </div>
        )}
      </header>
    </>
  );
}
