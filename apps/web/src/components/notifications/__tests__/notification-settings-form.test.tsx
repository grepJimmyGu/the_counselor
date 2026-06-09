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
  getEmailPreferences: vi.fn(),
  updateEmailPreferences: vi.fn(),
}));

const useSessionMock = vi.fn(() => ({
  data: { backendToken: "tok_abc" },
  status: "authenticated" as const,
}));
vi.mock("next-auth/react", () => ({
  useSession: () => useSessionMock(),
}));

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
  getEmailPreferences,
  updateEmailPreferences,
} from "@/lib/api";
import type { EmailPreferences } from "@/lib/contracts";
import { NotificationSettingsForm } from "../notification-settings-form";

const DEFAULTS: EmailPreferences = {
  transactional: true,
  weekly_digest: true,
  upsell_nudges: true,
  creator_program: true,
  signal_alerts_enabled: true,
  daily_digest_enabled: true,
  silent_days_enabled: false,
  unsubscribed_at: null,
};

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

describe("NotificationSettingsForm", () => {
  it("renders the 3 PRD-19 toggles with their default values", async () => {
    (getEmailPreferences as ReturnType<typeof vi.fn>).mockResolvedValue(DEFAULTS);
    render(<NotificationSettingsForm />);
    await waitFor(() => {
      expect(screen.getByTestId("toggle-signal_alerts_enabled")).toBeTruthy();
    });
    const sigBtn = screen.getByTestId("toggle-signal_alerts_enabled");
    const digestBtn = screen.getByTestId("toggle-daily_digest_enabled");
    const silentBtn = screen.getByTestId("toggle-silent_days_enabled");
    expect(sigBtn.getAttribute("aria-checked")).toBe("true");
    expect(digestBtn.getAttribute("aria-checked")).toBe("true");
    expect(silentBtn.getAttribute("aria-checked")).toBe("false");
  });

  it("flips a toggle optimistically and PATCHes the change", async () => {
    (getEmailPreferences as ReturnType<typeof vi.fn>).mockResolvedValue(DEFAULTS);
    (updateEmailPreferences as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...DEFAULTS,
      signal_alerts_enabled: false,
    });
    render(<NotificationSettingsForm />);
    await waitFor(() => {
      expect(screen.getByTestId("toggle-signal_alerts_enabled")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("toggle-signal_alerts_enabled"));
    await waitFor(() => {
      expect(updateEmailPreferences).toHaveBeenCalledWith(
        { signal_alerts_enabled: false },
        "tok_abc",
      );
    });
    expect(screen.getByTestId("toggle-signal_alerts_enabled").getAttribute("aria-checked")).toBe("false");
  });

  it("reverts an optimistic toggle when PATCH fails", async () => {
    (getEmailPreferences as ReturnType<typeof vi.fn>).mockResolvedValue(DEFAULTS);
    (updateEmailPreferences as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("Network down"),
    );
    render(<NotificationSettingsForm />);
    await waitFor(() => {
      expect(screen.getByTestId("toggle-daily_digest_enabled")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("toggle-daily_digest_enabled"));
    await waitFor(() => {
      expect(screen.getByText(/Network down/)).toBeTruthy();
    });
    // Toggle should have flipped back to ON.
    expect(
      screen
        .getByTestId("toggle-daily_digest_enabled")
        .getAttribute("aria-checked"),
    ).toBe("true");
  });

  it("hides legacy categories until 'Show other Livermore email categories' clicked", async () => {
    (getEmailPreferences as ReturnType<typeof vi.fn>).mockResolvedValue(DEFAULTS);
    render(<NotificationSettingsForm />);
    await waitFor(() => {
      expect(screen.getByText(/Show other Livermore/)).toBeTruthy();
    });
    expect(screen.queryByTestId("toggle-weekly_digest")).toBeNull();

    fireEvent.click(screen.getByText(/Show other Livermore/));
    await waitFor(() => {
      expect(screen.getByTestId("toggle-weekly_digest")).toBeTruthy();
    });
  });

  it("surfaces a 'globally unsubscribed' banner when prefs.unsubscribed_at is set", async () => {
    (getEmailPreferences as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...DEFAULTS,
      unsubscribed_at: "2026-06-01T12:00:00Z",
    });
    render(<NotificationSettingsForm />);
    await waitFor(() => {
      expect(screen.getByText(/globally unsubscribed/i)).toBeTruthy();
    });
  });

  it("prompts to sign in when user is unauthenticated", () => {
    useSessionMock.mockReturnValue({ data: null, status: "unauthenticated" });
    render(<NotificationSettingsForm />);
    expect(screen.getByText(/Sign in to manage/i)).toBeTruthy();
    // Form not rendered.
    expect(screen.queryByTestId("notification-settings-form")).toBeNull();
  });

  it("surfaces load error when GET throws", async () => {
    (getEmailPreferences as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("Server is down"),
    );
    render(<NotificationSettingsForm />);
    await waitFor(() => {
      expect(screen.getByText(/Server is down/)).toBeTruthy();
    });
  });
});
