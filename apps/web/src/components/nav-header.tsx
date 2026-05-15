"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession, signIn, signOut } from "next-auth/react";
import type { Route } from "next";
import { LogIn, LogOut, User } from "lucide-react";
import { LanguageSwitcher } from "@/components/language-switcher";
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
        className="gap-1.5 text-xs"
        onClick={() => signIn("google")}
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
          className="flex h-8 w-8 cursor-pointer items-center justify-center overflow-hidden rounded-full border border-border bg-primary/10 text-xs font-semibold text-primary transition-colors hover:bg-primary/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
          <Link href={"/profile" as Route} className="cursor-pointer">
            <User className="mr-2 h-3.5 w-3.5" />
            Profile
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={() => signOut({ callbackUrl: "/" })}
          className="cursor-pointer text-destructive focus:text-destructive"
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

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex h-12 w-full max-w-[1600px] items-center justify-between px-4 md:px-6 lg:px-8">

        <Link
          href="/"
          className="text-sm font-semibold tracking-tight text-foreground hover:text-primary transition-colors"
        >
          Livermore
        </Link>

        <div className="flex items-center gap-4">
          <nav aria-label="Main navigation" className="flex items-center gap-1">
            <Link href="/" className={navLink(pathname === "/")}>{t.navHome}</Link>
            <Link href={"/workspace" as Route} className={navLink(pathname.startsWith("/workspace"))}>{t.navWorkspace}</Link>
            <Link href={"/stocks" as Route} className={navLink(pathname.startsWith("/stocks"))}>Market</Link>
            <Link href={"/commodities/GOLD" as Route} className={navLink(pathname.startsWith("/commodities"))}>Commodities</Link>
            <Link href={"/sentiment" as Route} className={navLink(pathname.startsWith("/sentiment"))}>Sentiment</Link>
            <Link href={"/community" as Route} className={navLink(pathname.startsWith("/community"))}>Community</Link>
            <Link href={"/templates" as Route} className={navLink(pathname.startsWith("/templates"))}>{t.navTemplates}</Link>
          </nav>
          <div className="flex items-center gap-2">
            <LanguageSwitcher />
            <UserMenu />
          </div>
        </div>

      </div>
    </header>
  );
}
