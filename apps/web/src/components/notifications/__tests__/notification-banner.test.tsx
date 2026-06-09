/** @vitest-environment jsdom */

import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  getPendingNotifications: vi.fn(),
  ackNotificationBanner: vi.fn(),
}));

const useSessionMock = vi.fn(() => ({
  data: { backendToken: "tok_abc" },
  status: "authenticated" as const,
}));
vi.mock("next-auth/react", () => ({
  useSession: () => useSessionMock(),
}));

// next/link returns its children with the href prop — the standard
// jsdom-friendly mock used by other component tests in this repo.
vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    className,
  }: {
    children: React.ReactNode;
    href: string;
    className?: string;
  }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));

import {
  ackNotificationBanner,
  getPendingNotifications,
} from "@/lib/api";
import { NotificationBanner } from "../notification-banner";

beforeEach(() => {
  vi.clearAllMocks();
  useSessionMock.mockReturnValue({
    data: { backendToken: "tok_abc" },
    status: "authenticated",
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function pending(id: number, overrides: Record<string, unknown> = {}) {
  return {
    id,
    title: `⚡ Strategy ${id}`,
    body: `Rule context for ${id}`,
    strategy_slug: `strat_${id}`,
    created_at: "2026-06-09T00:00:00Z",
    ...overrides,
  };
}

describe("NotificationBanner", () => {
  it("renders nothing for an unauthenticated user", async () => {
    useSessionMock.mockReturnValue({ data: null, status: "unauthenticated" });
    (getPendingNotifications as ReturnType<typeof vi.fn>).mockResolvedValue([
      pending(1),
    ]);
    const { container } = render(<NotificationBanner />);
    // Wait a microtask so any spurious fetch could complete.
    await waitFor(() => {
      // Nothing rendered + no fetch attempted.
      expect(container.querySelector("[data-testid='notification-banner']")).toBeNull();
    });
    expect(getPendingNotifications).not.toHaveBeenCalled();
  });

  it("renders rows for a signed-in user", async () => {
    (getPendingNotifications as ReturnType<typeof vi.fn>).mockResolvedValue([
      pending(1, { title: "⚡ NVDA flipped" }),
      pending(2, { title: "⚡ SPY moved" }),
    ]);
    render(<NotificationBanner />);
    await waitFor(() => {
      expect(screen.getByText(/NVDA flipped/)).toBeTruthy();
    });
    expect(screen.getByText(/SPY moved/)).toBeTruthy();
    expect(getPendingNotifications).toHaveBeenCalledWith("tok_abc");
  });

  it("caps display at maxShown and shows the overflow counter", async () => {
    (getPendingNotifications as ReturnType<typeof vi.fn>).mockResolvedValue([
      pending(1),
      pending(2),
      pending(3),
      pending(4),
      pending(5),
    ]);
    render(<NotificationBanner maxShown={2} />);
    await waitFor(() => {
      expect(screen.getByText(/\+3 more/)).toBeTruthy();
    });
  });

  it("optimistically removes a row on dismiss + posts ack", async () => {
    (getPendingNotifications as ReturnType<typeof vi.fn>).mockResolvedValue([
      pending(7, { title: "⚡ Solo flipped" }),
    ]);
    (ackNotificationBanner as ReturnType<typeof vi.fn>).mockResolvedValue(
      undefined,
    );
    render(<NotificationBanner />);
    await waitFor(() => {
      expect(screen.getByText(/Solo flipped/)).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("notification-dismiss-7"));
    await waitFor(() => {
      expect(screen.queryByText(/Solo flipped/)).toBeNull();
    });
    expect(ackNotificationBanner).toHaveBeenCalledWith(7, "tok_abc");
  });

  it("renders nothing when the fetch returns an empty list", async () => {
    (getPendingNotifications as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    const { container } = render(<NotificationBanner />);
    await waitFor(() => {
      expect(getPendingNotifications).toHaveBeenCalled();
    });
    expect(
      container.querySelector("[data-testid='notification-banner']"),
    ).toBeNull();
  });

  it("renders rows with no strategy_slug WITHOUT a link or inline mark-as-executed", async () => {
    (getPendingNotifications as ReturnType<typeof vi.fn>).mockResolvedValue([
      pending(9, { title: "⚡ No-link banner", strategy_slug: null }),
    ]);
    const { container } = render(<NotificationBanner />);
    await waitFor(() => {
      expect(screen.getByText(/No-link banner/)).toBeTruthy();
    });
    // No <a> ancestor on the title node — without a strategy_slug there's
    // nothing to deep-link to.
    const titleNode = screen.getByText(/No-link banner/);
    expect(titleNode.closest("a")).toBeNull();
    // And no mark-executed button for a banner that doesn't carry a strategy_id.
    expect(screen.queryByTestId("mark-as-executed-idle")).toBeNull();
    expect(container.querySelector("[data-testid='notification-banner']")).toBeTruthy();
  });

  it("renders an inline MarkAsExecutedButton when strategy_slug is present", async () => {
    (getPendingNotifications as ReturnType<typeof vi.fn>).mockResolvedValue([
      pending(11, { strategy_slug: "strat_11" }),
    ]);
    render(<NotificationBanner />);
    await waitFor(() => {
      expect(screen.getByTestId("mark-as-executed-idle")).toBeTruthy();
    });
    // Plus the "View strategy →" affordance.
    expect(screen.getByText(/View strategy/)).toBeTruthy();
  });
});
