/**
 * <NavHeader> — account-menu entry coverage.
 *
 * Adds a persistent "My Strategies → /account/strategies" entry to the
 * signed-in user dropdown so the saved-strategy repo is reachable from
 * anywhere, not just the home tile / post-save link.
 *
 * We passthrough-mock the Radix dropdown primitive so its (normally
 * portaled, open-on-interaction) content renders inline — that lets us
 * assert OUR menu item without driving Radix's pointer machinery, which
 * jsdom doesn't fully implement and which user-event (not installed) would
 * otherwise be needed for.
 */
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
vi.mock("@/lib/locale-context", () => ({
  useLocale: () => ({ t: { navHome: "Home" } }),
}));
vi.mock("@/components/QuotaBadge", () => ({ QuotaBadge: () => null }));
vi.mock("@/components/language-switcher", () => ({
  LanguageSwitcher: () => null,
}));

const useSessionMock = vi.fn();
vi.mock("next-auth/react", () => ({
  useSession: () => useSessionMock(),
  signIn: vi.fn(),
  signOut: vi.fn(),
}));

// Render the dropdown content inline (no portal, always mounted).
vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
}));

import { NavHeader } from "../nav-header";

beforeEach(() => {
  vi.clearAllMocks();
  useSessionMock.mockReturnValue({
    data: { user: { email: "a@b.com", name: "Mr Gu" } },
    status: "authenticated",
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("NavHeader — My Strategies account entry", () => {
  it("links 'My Strategies' to /account/strategies for a signed-in user", () => {
    render(<NavHeader />);
    // UserMenu mounts in both the desktop and mobile header layouts, so the
    // entry appears once per layout — every instance must point at the repo.
    const links = screen.getAllByTestId("user-menu-my-strategies");
    expect(links.length).toBeGreaterThanOrEqual(1);
    for (const link of links) {
      expect(link.getAttribute("href")).toBe("/account/strategies");
      expect(link.textContent).toContain("My Strategies");
    }
  });

  it("keeps the existing Account entry alongside it", () => {
    render(<NavHeader />);
    // Account link still present (we inserted, didn't replace).
    const account = screen
      .getAllByRole("link")
      .find((a) => a.getAttribute("href") === "/account");
    expect(account).toBeTruthy();
  });

  it("does not render the user menu when signed out", () => {
    useSessionMock.mockReturnValue({ data: null, status: "unauthenticated" });
    render(<NavHeader />);
    expect(screen.queryByTestId("user-menu-my-strategies")).toBeNull();
  });
});
