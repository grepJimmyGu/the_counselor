"use client";

/**
 * <OverlayDemo> — a compact *schematic* of how an overlay behaves.
 *
 * These are illustrative diagrams (not backtest data) keyed by overlay
 * kind, so the user can see the mechanic at a glance on the overlay-picker
 * card. Four shapes cover the six kinds:
 *   - trend  → defensive, defense_first  (in/out vs a long-term trend)
 *   - rank   → rotation, dual_momentum   (hold the top names, rest to cash)
 *   - snap   → rebalance                 (let weights drift, restore targets)
 *   - tilt   → stability_tilt            (shift weight toward steadier names)
 *
 * Colors come from the app CSS variables so they adapt to dark mode.
 */

import type { ReactElement } from "react";
import type { OverlayKind } from "@/lib/contracts";

type Schema = "trend" | "rank" | "snap" | "tilt";

const KIND_SCHEMA: Record<OverlayKind, Schema> = {
  defensive: "trend",
  defense_first: "trend",
  rotation: "rank",
  dual_momentum: "rank",
  rebalance: "snap",
  stability_tilt: "tilt",
};

const CAPTION: Record<Schema, string> = {
  trend:
    "Step out of a holding while it sits below its long-term trend; step back in when it reclaims it.",
  rank: "Hold the top names by momentum each period; the rest move to cash.",
  snap: "Let weights drift, then restore your targets on each rebalance.",
  tilt: "Shift weight toward your steadier, lower-volatility holdings.",
};

const C = {
  trend: "var(--border)",
  price: "var(--foreground)",
  primary: "var(--primary)",
  muted: "var(--muted-foreground)",
  out: "var(--destructive)",
  in: "#10b981",
};

function TrendDemo() {
  return (
    <svg
      viewBox="0 0 300 96"
      className="w-full"
      role="img"
      aria-label="A price line dips below its moving average — going to cash — then reclaims it and re-enters."
    >
      <rect x="138" y="18" width="70" height="62" fill={C.out} opacity="0.1" />
      <line x1="12" y1="50" x2="288" y2="50" stroke={C.trend} strokeWidth="1.5" strokeDasharray="4 4" />
      <polyline
        points="12,34 55,28 100,42 138,50 168,66 208,50 250,34 288,26"
        fill="none"
        stroke={C.price}
        strokeWidth="2"
      />
      <circle cx="138" cy="50" r="4" fill={C.out} />
      <circle cx="208" cy="50" r="4" fill={C.in} />
      <text x="173" y="76" textAnchor="middle" fontSize="11" fill={C.out}>in cash</text>
      <text x="285" y="44" textAnchor="end" fontSize="11" fill={C.muted}>trend</text>
    </svg>
  );
}

function RankDemo() {
  const bars = [
    { x: 18, h: 56, held: true },
    { x: 68, h: 46, held: true },
    { x: 118, h: 38, held: true },
    { x: 168, h: 24, held: false },
    { x: 218, h: 16, held: false },
  ];
  return (
    <svg
      viewBox="0 0 300 96"
      className="w-full"
      role="img"
      aria-label="Five ranked bars; the top three are held, the bottom two move to cash."
    >
      <line x1="12" y1="78" x2="288" y2="78" stroke={C.trend} strokeWidth="1.5" />
      {bars.map((b, i) => (
        <rect
          key={i}
          x={b.x}
          y={78 - b.h}
          width="34"
          height={b.h}
          rx="2"
          fill={b.held ? C.primary : C.muted}
          opacity={b.held ? 1 : 0.3}
        />
      ))}
      <text x="86" y="92" textAnchor="middle" fontSize="11" fill={C.primary}>held</text>
      <text x="219" y="92" textAnchor="middle" fontSize="11" fill={C.muted}>to cash</text>
    </svg>
  );
}

function SnapDemo() {
  // Drifted bars (solid) snapping down/up to a shared target line.
  const cols = [
    { x: 40, drift: 24 },
    { x: 130, drift: -18 },
    { x: 220, drift: 10 },
  ];
  const target = 50;
  return (
    <svg
      viewBox="0 0 300 96"
      className="w-full"
      role="img"
      aria-label="Three weights drifted away from a target line, with arrows restoring them to target."
    >
      <line x1="12" y1={target} x2="288" y2={target} stroke={C.primary} strokeWidth="1.5" strokeDasharray="4 4" />
      {cols.map((c, i) => {
        const top = target - c.drift;
        return (
          <g key={i}>
            <rect x={c.x} y={Math.min(top, target)} width="40" height={Math.abs(c.drift)} rx="2" fill={C.muted} opacity="0.35" />
            <line x1={c.x + 20} y1={top} x2={c.x + 20} y2={target} stroke={C.price} strokeWidth="1.5" />
            <polygon
              points={
                c.drift > 0
                  ? `${c.x + 16},${target - 6} ${c.x + 24},${target - 6} ${c.x + 20},${target}`
                  : `${c.x + 16},${target + 6} ${c.x + 24},${target + 6} ${c.x + 20},${target}`
              }
              fill={C.price}
            />
          </g>
        );
      })}
      <text x="285" y={target - 5} textAnchor="end" fontSize="11" fill={C.primary}>target</text>
    </svg>
  );
}

function TiltDemo() {
  return (
    <svg
      viewBox="0 0 300 96"
      className="w-full"
      role="img"
      aria-label="Weight shifts from a volatile holding down to a steadier, lower-volatility holding."
    >
      <line x1="12" y1="78" x2="288" y2="78" stroke={C.trend} strokeWidth="1.5" />
      <rect x="50" y="40" width="46" height="38" rx="2" fill={C.out} opacity="0.3" />
      <rect x="204" y="24" width="46" height="54" rx="2" fill={C.primary} />
      <polygon points="69,30 83,30 76,20" fill={C.out} transform="rotate(180 76 26)" />
      <polygon points="220,18 234,18 227,8" fill={C.primary} />
      <text x="73" y="92" textAnchor="middle" fontSize="11" fill={C.muted}>volatile</text>
      <text x="227" y="92" textAnchor="middle" fontSize="11" fill={C.primary}>steady</text>
    </svg>
  );
}

const RENDER: Record<Schema, () => ReactElement> = {
  trend: TrendDemo,
  rank: RankDemo,
  snap: SnapDemo,
  tilt: TiltDemo,
};

export function OverlayDemo({ kind }: { kind: OverlayKind }) {
  const schema = KIND_SCHEMA[kind];
  const Demo = RENDER[schema];
  return (
    <div data-testid={`overlay-demo-${kind}`}>
      <Demo />
      <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{CAPTION[schema]}</p>
    </div>
  );
}
