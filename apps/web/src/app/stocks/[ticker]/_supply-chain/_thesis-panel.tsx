"use client";

import { TierBadge } from "@/components/stocks/tier-badge";
import type { BottleneckThesis, EvidenceTier, ThesisGate } from "@/lib/contracts";
import { cn } from "@/lib/utils";

/**
 * Phase 3d: the bottleneck-thesis panel. Renders the reasoning engine's graded
 * research artifact — architecture transition, chain map, chokepoint argument,
 * tiered evidence, forward-financial sensitivity, the 14-gate scorecard with its
 * vetoes, catalysts, and invalidation tests — with a "how it's built & how to
 * read it" guide. Never a recommendation.
 */

const TIERS = new Set(["A", "B", "C", "D", "E", "F"]);
const asTier = (t: string): EvidenceTier | null =>
  TIERS.has((t || "").toUpperCase()) ? ((t.toUpperCase() as EvidenceTier)) : null;

function bandMeta(band: string, veto: boolean): { label: string; cls: string } {
  if (veto) return { label: "Watch item · veto", cls: "text-red-700 border-red-300 bg-red-50" };
  if (band === "strong") return { label: "Strong archetype fit", cls: "text-emerald-700 border-emerald-300 bg-emerald-50" };
  if (band === "partial") return { label: "Partial fit", cls: "text-amber-700 border-amber-300 bg-amber-50" };
  return { label: "Watch item, not a thesis", cls: "text-muted-foreground border-border bg-muted/40" };
}

function statusCls(status: string): string {
  if (status === "constrained") return "text-amber-700 border-amber-400 bg-amber-50";
  if (status === "abundant") return "text-emerald-700 border-emerald-300 bg-emerald-50";
  return "text-muted-foreground border-border bg-muted/40";
}

function gateCls(g: ThesisGate): string {
  const s = (g.score || "").toUpperCase();
  if (s === "VETO") return "border-red-400 text-red-700";
  if (s === "PASS") return "border-emerald-300 text-emerald-700";
  return "border-border text-muted-foreground";
}

function Section({ n, title, help, children }: {
  n?: string; title: string; help: string; children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-border bg-white p-4 shadow-sm">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-foreground/80">
        {n ? `${n} · ` : ""}{title}
      </h4>
      <p className="mb-3 mt-0.5 text-[11.5px] leading-snug text-muted-foreground">{help}</p>
      {children}
    </section>
  );
}

export function ThesisPanel({ thesis }: { thesis: BottleneckThesis }) {
  if (thesis.message) {
    return (
      <section className="rounded-xl border border-border bg-white p-5 text-sm text-muted-foreground shadow-sm">
        <h3 className="mb-1 text-sm font-semibold text-foreground">Bottleneck thesis</h3>
        {thesis.message}
      </section>
    );
  }

  const t = thesis;
  const band = bandMeta(t.band, t.veto);
  const ff = t.forward_financials;

  return (
    <div className="space-y-3">
      {/* Header */}
      <section className="rounded-xl border border-border bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Supply-Chain Bottleneck Thesis
            </div>
            <div className="mt-0.5 text-lg font-semibold capitalize">
              {t.verdict.replace(/_/g, " ")}
            </div>
            {t.computed_at && (
              <div className="mt-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                As of {t.computed_at.slice(0, 10)}
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            <span className={cn("rounded-full border px-3 py-0.5 text-xs font-medium", band.cls)}>
              {band.label}
            </span>
            <div className="text-xs text-muted-foreground">
              <span className="text-xl font-bold text-foreground">{t.fit_score}</span>/{t.max_score} fit
            </div>
          </div>
        </div>
        <p className="mt-2 border-l-2 border-border pl-2 text-[11.5px] text-muted-foreground">
          Research artifact — structure &amp; evidence, never a recommendation, price target, or entry.
        </p>
      </section>

      {/* How it's built & how to read it */}
      <details open className="rounded-xl border border-border bg-muted/30 px-4 py-1 text-[12px]">
        <summary className="cursor-pointer py-2 text-xs font-semibold tracking-wide text-foreground/80">
          How this is built &amp; how to read it
        </summary>
        <div className="grid gap-x-6 gap-y-1 pb-2 sm:grid-cols-2">
          <div>
            <div className="mt-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Built from</div>
            <p className="leading-snug text-muted-foreground">
              SEC <b>10-K</b> + <b>8-K</b> filings, business-intelligence summaries, and FMP financials.
            </p>
            <div className="mt-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Method &amp; tech</div>
            <p className="leading-snug text-muted-foreground">
              Map the chain → test for a true chokepoint → grade every claim by evidence quality. LLM-reasoned — the <i>map</i> is inference, while every <i>hard claim must verify verbatim</i> in the filing (no invented facts).
            </p>
          </div>
          <div>
            <div className="mt-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Reading it</div>
            <p className="leading-snug text-muted-foreground">
              Tiers <b>A</b> filing (can prove <i>or kill</i>) → <b>D</b> inference (the map). The <b>/{t.max_score} fit score</b> = how well it matches the bottleneck archetype — <i>not</i> whether the stock rises. <b>unknown = 0</b>; under 8 or a veto → watch item.
            </p>
          </div>
        </div>
      </details>

      {/* 1 Architecture transition */}
      <Section n="1" title="Architecture transition" help="The tech shift that makes something newly scarce. No shift → a theme, not a bottleneck.">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">{t.architecture_transition.from_state || "—"}</span>
          <span className="text-muted-foreground">→</span>
          <span className="font-semibold">{t.architecture_transition.to_state || "—"}</span>
        </div>
        {t.architecture_transition.what_becomes_scarce && (
          <div className="mt-1.5 text-xs text-muted-foreground">
            Newly scarce: <b className="text-foreground">{t.architecture_transition.what_becomes_scarce}</b>
            {t.architecture_transition.transition_exists ? " · transition exists ✓" : " · no clear transition"}
          </div>
        )}
      </Section>

      {/* 2 Chain map */}
      {t.chain_map.length > 0 && (
        <Section n="2" title="Chain map" help="Where the company sits, raw material → finished system. Amber = potential bottleneck; unknown = not yet verified.">
          <ol className="space-y-1.5">
            {t.chain_map.map((h, i) => {
              const isTarget = h.named_players.some((p) => p.toUpperCase().includes(t.symbol));
              return (
                <li
                  key={i}
                  className={cn(
                    "flex items-center gap-2.5 rounded-lg border p-2 text-[13px]",
                    isTarget ? "border-amber-400 bg-amber-50/60" : "border-border bg-muted/30"
                  )}
                >
                  <span className="grid h-5 w-5 flex-none place-items-center rounded-full border border-border bg-white text-[11px] font-semibold text-muted-foreground">
                    {h.hop}
                  </span>
                  <span className="flex-1">
                    {h.layer}
                    {h.named_players.length > 0 && (
                      <span className="text-muted-foreground"> — {h.named_players.join(", ")}</span>
                    )}
                  </span>
                  <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase", statusCls(h.status))}>
                    {h.status}
                  </span>
                </li>
              );
            })}
          </ol>
        </Section>
      )}

      {/* 3 Chokepoint argument */}
      <Section n="3" title="Chokepoint argument" help="If it stops shipping, what breaks — and is there a substitute?">
        {t.chokepoint_argument.if_stops ? (
          <p className="text-[13px] leading-relaxed">
            If <b>{t.chokepoint_argument.if_stops}</b>, {t.chokepoint_argument.downstream_breaks} <b>breaks</b>
            {t.chokepoint_argument.mechanism ? ` — ${t.chokepoint_argument.mechanism}` : ""}.{" "}
            {t.chokepoint_argument.nearest_substitute && (
              <>Nearest substitute: <b>{t.chokepoint_argument.nearest_substitute}</b>
              {t.chokepoint_argument.substitute_status ? ` (${t.chokepoint_argument.substitute_status})` : ""}.</>
            )}
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">Not enough evidence to state the chokepoint mechanism.</p>
        )}
      </Section>

      {/* 4 Evidence table */}
      {t.evidence_table.length > 0 && (
        <Section n="4" title="Evidence table" help="Each claim's proof strength. A = a filing you can check; D = inference. Higher proof carries the thesis; the map only sketches it.">
          <div className="space-y-2">
            {t.evidence_table.map((r, i) => {
              const tier = asTier(r.tier);
              return (
                <div key={i} className="flex items-start gap-2 border-b border-border pb-2 text-[12px] last:border-0 last:pb-0">
                  {tier ? <TierBadge tier={tier} /> : <span className="text-[11px] text-muted-foreground">{r.tier || "—"}</span>}
                  <div className="flex-1">
                    <div>{r.claim}</div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">
                      {r.source}{r.date ? ` · ${r.date}` : ""}{r.falsifier ? ` · falsifier: ${r.falsifier}` : ""}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {/* 5 Forward financials */}
      {ff && (
        <Section n="5" title="Forward financials" help="A forward low/base/high sensitivity, never a point estimate or a price target.">
          {ff.trailing_note && <p className="mb-2 text-[11.5px] text-muted-foreground">{ff.trailing_note}</p>}
          {ff.drivers.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-[12px]">
                <thead>
                  <tr className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    <th className="border-b border-border pb-1 pr-2 text-left">Driver</th>
                    <th className="border-b border-border pb-1 px-2 text-right">Low</th>
                    <th className="border-b border-border pb-1 px-2 text-right">Base</th>
                    <th className="border-b border-border pb-1 px-2 text-right">High</th>
                  </tr>
                </thead>
                <tbody>
                  {ff.drivers.map((d, i) => (
                    <tr key={i}>
                      <td className="border-b border-border py-1.5 pr-2">{d.driver}</td>
                      <td className="border-b border-border px-2 text-right text-muted-foreground">{d.low || "—"}</td>
                      <td className="border-b border-border px-2 text-right font-medium">{d.base || "—"}</td>
                      <td className="border-b border-border px-2 text-right text-muted-foreground">{d.high || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-muted-foreground">
            {ff.market_cap && <span>Market cap <b className="text-foreground">{ff.market_cap}</b></span>}
            {ff.trailing_revenue && <span>Trailing rev <b className="text-foreground">{ff.trailing_revenue}</b></span>}
            {ff.gaap_gross_margin && <span>GAAP margin <b className="text-foreground">{ff.gaap_gross_margin}</b></span>}
            {ff.contracted_forward_revenue && ff.contracted_forward_revenue !== "unknown" && (
              <span>Contracted fwd rev <b className="text-foreground">{ff.contracted_forward_revenue}</b></span>
            )}
          </div>
        </Section>
      )}

      {/* 6 Gate scorecard */}
      {t.gates.length > 0 && (
        <Section n="6" title="Gate scorecard" help="14 archetype checks scored 0–2 (unknown = 0, never a guess). Two are vetoes (financing, factor-overlap). Under 8 → watch item.">
          <div className="flex flex-wrap gap-1.5">
            {t.gates.map((g) => (
              <span key={g.n} className={cn("rounded border bg-muted/30 px-2 py-0.5 text-[11px]", gateCls(g))} title={g.note}>
                {g.n} {g.name} <b>{g.score}</b>
              </span>
            ))}
          </div>
        </Section>
      )}

      {/* 7 Catalyst calendar */}
      {t.catalyst_calendar.length > 0 && (
        <Section n="7" title="Catalyst calendar" help="Dated events that would confirm or break the thesis.">
          <ul className="space-y-1 text-[12px]">
            {t.catalyst_calendar.map((c, i) => (
              <li key={i}>
                <b>{c.date || "—"}</b>: {c.event}
                {c.confirms_or_breaks ? <span className="text-muted-foreground"> → {c.confirms_or_breaks}</span> : null}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* 8 Invalidation tests */}
      {t.invalidation_tests.length > 0 && (
        <Section n="8" title="Invalidation tests" help="Specific things that, if they happen, would break the thesis. A price drop is not one of them.">
          <ul className="list-disc space-y-1 pl-5 text-[12.5px]">
            {t.invalidation_tests.map((x, i) => <li key={i}>{x}</li>)}
          </ul>
          <p className="mt-1.5 text-[11px] italic text-muted-foreground">
            A drawdown is not an invalidation; a rally is not a confirmation.
          </p>
        </Section>
      )}

      {/* Risk & gaps */}
      <Section title="Risk &amp; gaps" help="The honest holes — what the analysis could not verify, so you know where it's blind.">
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
          <span>Binariness <b className="text-foreground">{t.risk_profile.binariness}</b></span>
          <span>Liquidity <b className="text-foreground">{t.risk_profile.liquidity}</b></span>
          <span>Crowding <b className="text-foreground">{t.risk_profile.crowding}</b></span>
          <span>Factor overlap <b className="text-foreground">{t.risk_profile.factor_overlap}</b></span>
        </div>
        {t.could_not_verify.length > 0 && (
          <div className="mt-2 text-[11.5px] text-muted-foreground">
            Could not verify: {t.could_not_verify.join(" · ")}
          </div>
        )}
      </Section>
    </div>
  );
}
