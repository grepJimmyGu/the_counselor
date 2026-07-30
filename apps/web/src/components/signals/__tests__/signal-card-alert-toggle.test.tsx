/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  subscribeTickerAlert: vi.fn(),
  unsubscribeTickerAlert: vi.fn(),
}));

const useSessionMock = vi.fn(() => ({
  data: { backendToken: "tok" },
  status: "authenticated" as const,
}));
vi.mock("next-auth/react", () => ({ useSession: () => useSessionMock() }));

import { subscribeTickerAlert, unsubscribeTickerAlert } from "@/lib/api";
import { SignalCardAlertToggle } from "../signal-card-alert-toggle";

const subMock = subscribeTickerAlert as unknown as ReturnType<typeof vi.fn>;
const unsubMock = unsubscribeTickerAlert as unknown as ReturnType<typeof vi.fn>;

const SCREENS = [
  { id: "scr1", title: "Oversold semis" },
  { id: "scr2", title: "Breakouts" },
];

beforeEach(() => {
  vi.clearAllMocks();
  useSessionMock.mockReturnValue({
    data: { backendToken: "tok" },
    status: "authenticated",
  });
  subMock.mockResolvedValue({});
  unsubMock.mockResolvedValue(undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SignalCardAlertToggle", () => {
  it("subscribes the symbol against the chosen screen", async () => {
    render(<SignalCardAlertToggle symbol="NVDA" screens={SCREENS} />);
    fireEvent.change(screen.getByTestId("alert-toggle-screen"), {
      target: { value: "scr2" },
    });
    fireEvent.click(screen.getByTestId("alert-toggle"));

    await waitFor(() =>
      expect(subMock).toHaveBeenCalledWith(
        { symbol: "NVDA", saved_screen_id: "scr2" },
        "tok",
      ),
    );
    await waitFor(() =>
      expect(screen.getByTestId("alert-toggle").getAttribute("data-subscribed")).toBe(
        "true",
      ),
    );
  });

  it("states that it notifies in BOTH directions once active", async () => {
    render(
      <SignalCardAlertToggle symbol="NVDA" screens={SCREENS} initialScreenId="scr1" />,
    );
    const note = screen.getByTestId("alert-toggle-active");
    expect(note.textContent).toMatch(/enters or leaves/);
    expect(note.textContent).toMatch(/Oversold semis/);
  });

  it("unsubscribes when already alerting", async () => {
    render(
      <SignalCardAlertToggle symbol="NVDA" screens={SCREENS} initialScreenId="scr1" />,
    );
    fireEvent.click(screen.getByTestId("alert-toggle"));
    await waitFor(() =>
      expect(unsubMock).toHaveBeenCalledWith("NVDA", "scr1", "tok"),
    );
    await waitFor(() =>
      expect(screen.getByTestId("alert-toggle").getAttribute("data-subscribed")).toBe(
        "false",
      ),
    );
  });

  it("explains the prerequisite instead of rendering a dead button with no screens", () => {
    render(<SignalCardAlertToggle symbol="NVDA" screens={[]} />);
    expect(screen.getByTestId("alert-toggle-no-screens").textContent).toMatch(
      /Save a screen first/,
    );
    expect(screen.queryByTestId("alert-toggle")).toBeNull();
  });

  it("disables the toggle for anonymous visitors", () => {
    useSessionMock.mockReturnValue({ data: null, status: "unauthenticated" });
    render(<SignalCardAlertToggle symbol="NVDA" screens={SCREENS} />);
    expect(screen.getByTestId("alert-toggle").hasAttribute("disabled")).toBe(true);
  });

  it("never claims success when the request fails", async () => {
    subMock.mockRejectedValue(new Error("Upgrade to Strategist"));
    render(<SignalCardAlertToggle symbol="NVDA" screens={SCREENS} />);
    fireEvent.click(screen.getByTestId("alert-toggle"));

    await waitFor(() =>
      expect(screen.getByTestId("alert-toggle-error").textContent).toMatch(
        /Upgrade to Strategist/,
      ),
    );
    expect(screen.getByTestId("alert-toggle").getAttribute("data-subscribed")).toBe(
      "false",
    );
  });
});
