/**
 * Guards for the 2026-11-11 Vercel pause (Fluid Active CPU).
 *
 * Symptom: every path on livermorealpha.com returned
 * `402 Payment required / DEPLOYMENT_DISABLED`. Vercel had paused the project
 * for Active CPU.
 *
 * Root cause: almost no request was served without running compute.
 *   1. The auth middleware matcher ended in a catch-all, so Auth.js ran on
 *      every page, every `<Link>` prefetch, robots.txt and every bot probe.
 *      Measured on a production build: one first-time visit to the (fully
 *      static) home page = 1 document + 26 prefetch requests = 27 middleware
 *      runs.
 *   2. No link to a function-rendered route (`/stocks/[ticker]`, `/s/[slug]`,
 *      `/screen`, ...) opted out of prefetch, so a list of N tickers scrolling
 *      into view asked a function to render N routes nobody had clicked.
 *   3. `<SessionProvider>` re-read the session on every tab re-focus.
 *   4. `/stocks/[ticker]` re-rendered on every request although its server
 *      output is the same for every visitor.
 *
 * These are config-shaped invariants — nothing fails at runtime when one
 * regresses, the bill just climbs — so each is pinned here. Full write-up in
 * docs/KNOWN_ISSUES.md.
 */
import fs from "node:fs";
import path from "node:path";

import ts from "typescript";
import { describe, expect, it, vi } from "vitest";

// `@/middleware` imports `@/auth`, which boots NextAuth. Only the exported
// matcher config is under test.
vi.mock("@/auth", () => ({ auth: (handler: unknown) => handler }));

const SRC = path.resolve(__dirname, "..");

function tsxFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "__tests__" || entry.name === "node_modules") continue;
      tsxFiles(full, out);
    } else if (full.endsWith(".tsx") && !/\.(test|spec)\.tsx$/.test(full)) {
      out.push(full);
    }
  }
  return out;
}

function parse(file: string): ts.SourceFile {
  return ts.createSourceFile(
    file,
    fs.readFileSync(file, "utf8"),
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
}

type JsxTag = ts.JsxOpeningElement | ts.JsxSelfClosingElement;

function jsxTags(sf: ts.SourceFile, tagName: string): JsxTag[] {
  const found: JsxTag[] = [];
  const visit = (node: ts.Node) => {
    if (
      (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) &&
      node.tagName.getText(sf) === tagName
    ) {
      found.push(node);
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return found;
}

function attr(tag: JsxTag, sf: ts.SourceFile, name: string): ts.JsxAttribute | undefined {
  return tag.attributes.properties.find(
    (p): p is ts.JsxAttribute => ts.isJsxAttribute(p) && p.name.getText(sf) === name,
  );
}

// ── 1. Middleware ────────────────────────────────────────────────────────────

/**
 * Next compiles each matcher with path-to-regexp. `:path*` is the only
 * parameter syntax this file uses; anything else is treated as a raw pattern,
 * which is exactly how the old catch-all `/((?!api|...).*)` was written.
 */
function matcherToRegExp(source: string): RegExp {
  const pattern = source.replace(/\/:[A-Za-z_]+\*/g, "(?:/.*)?");
  return new RegExp(`^${pattern}$`);
}

describe("auth middleware", () => {
  const PUBLIC_PATHS = [
    "/",
    "/stocks",
    "/stocks/AAPL",
    "/stocks/screener",
    "/pricing",
    "/community",
    "/templates/backtest-rsi-mean-reversion-aapl",
    "/s/some-share",
    "/screen",
    "/login",
    "/signup",
    "/robots.txt",
    "/sitemap.xml",
    "/wp-login.php",
  ];
  const PROTECTED_PATHS = ["/profile", "/profile/settings", "/watchlist", "/watchlist/AAPL"];

  it("runs on the protected routes and on nothing else", async () => {
    const { config } = await import("@/middleware");
    const matchers = config.matcher.map(matcherToRegExp);
    const matches = (p: string) => matchers.some((re) => re.test(p));

    expect(PROTECTED_PATHS.filter((p) => !matches(p))).toEqual([]);
    // A public path that matches means Auth.js runs on it for every visitor,
    // every prefetch and every crawler. That is what got the project paused.
    expect(PUBLIC_PATHS.filter(matches)).toEqual([]);
  });
});

// ── 2. Link prefetch ─────────────────────────────────────────────────────────

/**
 * Routes a Vercel function renders (the `ƒ` rows of `next build`, plus
 * `/stocks/[ticker]`, which is generated on first visit). A default `<Link>`
 * prefetches when it scrolls into view, so each of these costs a function run
 * per link per visitor — for a navigation that usually never happens.
 */
const FUNCTION_RENDERED =
  /^\/(stocks\/(?!screener(?:$|[?/#]))|s\/|strategies\/|commodities\/|flow\/|screens\/.|account\/strategies\/.|screen(?:$|[?/#]))/;

/**
 * `<Link>`s whose `href` is not a literal, so the route can't be read off the
 * tag. Every one must be listed here with where it goes. Anything that can
 * reach a function-rendered route is NOT listed — it carries
 * `prefetch={false}` instead.
 */
const STATIC_VARIABLE_HREFS: Record<string, string> = {
  "app/s/[slug]/page.tsx :: signupHref": "/signup?…",
  "components/AnonymousCTA.tsx :: signupHref": "/signup?…",
  "components/PricingTierCard.tsx :: ctaHref": "/signup or checkout",
  "components/SoftPaywall.tsx :: resolvedHref": "/pricing or the upgrade URL",
  "components/UpgradeModal.tsx :: primaryHref": "/pricing or /signup",
  "components/home/home-your-livermore.tsx :: href": "/community, /account",
  "components/nav-header.tsx :: href": "NAV_LINKS — all prerendered",
};

function hrefLiteral(expr: ts.Expression): string | null {
  let e: ts.Expression = expr;
  while (ts.isAsExpression(e) || ts.isParenthesizedExpression(e)) e = e.expression;
  if (ts.isStringLiteral(e) || ts.isNoSubstitutionTemplateLiteral(e)) return e.text;
  if (ts.isTemplateExpression(e)) return `${e.head.text}\${…}`;
  return null;
}

function hrefIdentifier(expr: ts.Expression, sf: ts.SourceFile): string {
  let e: ts.Expression = expr;
  while (ts.isAsExpression(e) || ts.isParenthesizedExpression(e)) e = e.expression;
  return e.getText(sf).replace(/\s+/g, " ");
}

describe("<Link> prefetch", () => {
  const offenders: string[] = [];
  const undecided: string[] = [];

  for (const file of tsxFiles(SRC)) {
    const sf = parse(file);
    const rel = path.relative(SRC, file);
    for (const tag of jsxTags(sf, "Link")) {
      const href = attr(tag, sf, "href");
      if (!href?.initializer) continue;
      const prefetch = attr(tag, sf, "prefetch");
      const prefetchOff = !!prefetch && /\{\s*false\s*\}/.test(prefetch.getText(sf));
      const line = sf.getLineAndCharacterOfPosition(tag.getStart(sf)).line + 1;

      let literal: string | null = null;
      let identifier = "";
      if (ts.isStringLiteral(href.initializer)) {
        literal = href.initializer.text;
      } else if (ts.isJsxExpression(href.initializer) && href.initializer.expression) {
        literal = hrefLiteral(href.initializer.expression);
        identifier = hrefIdentifier(href.initializer.expression, sf);
      }

      if (literal !== null) {
        if (FUNCTION_RENDERED.test(literal) && !prefetchOff) {
          offenders.push(`${rel}:${line}  ${literal}`);
        }
      } else if (!prefetchOff && !(`${rel} :: ${identifier}` in STATIC_VARIABLE_HREFS)) {
        undecided.push(`${rel}:${line}  href={${identifier}}`);
      }
    }
  }

  it("never prefetches a function-rendered route", () => {
    // Fix: add `prefetch={false}` to the <Link>. The navigation still works;
    // the route is just fetched on click instead of on scroll.
    expect(offenders).toEqual([]);
  });

  it("makes an explicit decision for every non-literal href", () => {
    // A new <Link href={someVariable}>: if it can reach a function-rendered
    // route, add `prefetch={false}`; if it is always a prerendered page, add it
    // to STATIC_VARIABLE_HREFS with where it goes.
    expect(undecided).toEqual([]);
  });
});

// ── 3. Session provider ──────────────────────────────────────────────────────

describe("<SessionProvider>", () => {
  it("does not re-read the session on every tab focus, and still polls", () => {
    const sf = parse(path.join(SRC, "app/layout.tsx"));
    const [provider] = jsxTags(sf, "SessionProvider");
    expect(provider).toBeDefined();

    // next-auth defaults this to true: one /api/auth/session function run per
    // re-focus of every signed-in tab.
    expect(attr(provider, sf, "refetchOnWindowFocus")?.getText(sf)).toMatch(/\{\s*false\s*\}/);
    // The slow poll is what still re-mints an ageing backend token in a tab
    // left open (apps/api/CLAUDE.md trap #23). Removing it reopens that bug.
    expect(attr(provider, sf, "refetchInterval")).toBeDefined();
  });
});

// ── 4. Ticker page ───────────────────────────────────────────────────────────

describe("/stocks/[ticker]", () => {
  it("is generated on first visit and cached, for any ticker", async () => {
    const mod = (await import("@/app/stocks/[ticker]/layout")) as Record<string, unknown>;

    // An empty list is what flips the route from "render on every request" to
    // "render once per ticker, then serve the cached copy".
    expect(await (mod.generateStaticParams as () => unknown)()).toEqual([]);
    // `dynamicParams = false` would 404 every ticker not known at build time.
    expect(mod.dynamicParams).not.toBe(false);
  });
});
