"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, CheckCircle2, ChevronDown, ChevronUp, Lock, PencilIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { researchTemplates, type ResearchTemplate } from "@/lib/contracts";
import { StrategyBriefCard } from "../strategy-brief-card";
import {
  WIZARD_QUESTIONS,
  WIZARD_STRATEGIES,
  type AssetAnswer,
  type WizardAnswers,
  type WizardStrategy,
} from "./strategy-wizard-data";
import { buildWhy, isComplete, recommend } from "./strategy-wizard-recommend";

/**
 * Strategy-builder wizard — single-question-at-a-time flow with
 * animated transitions (PR-F, 2026-05-25). Replaces the all-questions-
 * on-one-page renderer from PR #87.
 *
 * Flow:
 *   - One question card visible at a time, animated in via Tailwind
 *     `animate-in fade-in slide-in-from-bottom-1 duration-300`.
 *   - Answered questions collapse into clickable summary chips above
 *     the current question (click → re-open that question).
 *   - Picking an answer auto-advances after 350ms (so the user sees
 *     their pick highlight before the next question fades in). A
 *     manual "Next →" button is always available for keyboard users.
 *   - After all 5 answers, the recommendations panel fades in. Each
 *     card has a "Compare details" toggle that expands inline to a
 *     full `<StrategyBriefCard />` for side-by-side comparison.
 *   - Clicking "Use this →" sets `pickedSlug`; the other cards fade +
 *     scale down ("bump out") for 400ms, then `onPickTemplate` fires.
 *
 * Pre-fill via `initialAsset` shows Q1 with the answer pre-selected;
 * no auto-advance until the user actually clicks something.
 */

export interface StrategyWizardProps {
  initialAsset?: AssetAnswer;
  onPickTemplate: (payload: { template: ResearchTemplate; answers: WizardAnswers; strategy: WizardStrategy }) => void;
  onPickCustom: (strategy: WizardStrategy, answers: WizardAnswers) => void;
  onDescribeIdea: () => void;
}

const TOTAL_QUESTIONS = WIZARD_QUESTIONS.length;

export function StrategyWizard({
  initialAsset,
  onPickTemplate,
  onPickCustom,
  onDescribeIdea,
}: StrategyWizardProps) {
  const [answers, setAnswers] = useState<WizardAnswers>({
    asset: initialAsset ?? null,
    goal: null,
    cadence: null,
    behavior: null,
    dd: null,
  });
  const [currentIdx, setCurrentIdx] = useState<number>(0);
  const [expandedSlugs, setExpandedSlugs] = useState<Set<string>>(new Set());
  const [pickedSlug, setPickedSlug] = useState<string | null>(null);
  const advanceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (advanceTimer.current) clearTimeout(advanceTimer.current);
    };
  }, []);

  const answeredCount = Object.values(answers).filter((v) => v !== null).length;
  const recs = useMemo(
    () => (isComplete(answers) ? recommend(WIZARD_STRATEGIES, answers, 3) : []),
    [answers],
  );
  const showRecs = currentIdx >= TOTAL_QUESTIONS && isComplete(answers) && recs.length > 0;
  const currentQ = currentIdx < TOTAL_QUESTIONS ? WIZARD_QUESTIONS[currentIdx] : null;
  const currentSelected = currentQ ? answers[currentQ.key] : null;

  function setAnswer<K extends keyof WizardAnswers>(key: K, value: WizardAnswers[K]): void {
    setAnswers((prev) => ({ ...prev, [key]: value }));
  }

  function handlePickAnswer(value: string): void {
    if (!currentQ) return;
    const updated: WizardAnswers = { ...answers, [currentQ.key]: value as WizardAnswers[typeof currentQ.key] };
    setAnswers(updated);
    if (advanceTimer.current) clearTimeout(advanceTimer.current);
    advanceTimer.current = setTimeout(() => {
      // If editing an earlier question while all 5 remain answered, jump
      // straight to the recommendations rather than re-walking each
      // already-answered question.
      const allAnswered = Object.values(updated).every((v) => v !== null);
      setCurrentIdx((prev) => (allAnswered ? TOTAL_QUESTIONS : Math.min(prev + 1, TOTAL_QUESTIONS)));
    }, 350);
  }

  function handleManualNext(): void {
    if (advanceTimer.current) clearTimeout(advanceTimer.current);
    setCurrentIdx((prev) => Math.min(prev + 1, TOTAL_QUESTIONS));
  }

  function handleBack(): void {
    if (advanceTimer.current) clearTimeout(advanceTimer.current);
    setCurrentIdx((prev) => Math.max(prev - 1, 0));
  }

  function handleChipClick(idx: number): void {
    if (advanceTimer.current) clearTimeout(advanceTimer.current);
    setCurrentIdx(idx);
  }

  function toggleExpand(slug: string): void {
    setExpandedSlugs((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  }

  function handlePick(strategy: WizardStrategy): void {
    if (pickedSlug) return;
    // Guard: an unavailable template would land on the summary step but
    // crash on Run (backend can't execute it without the fundamental /
    // sentiment data that isn't wired yet). Render the card locked
    // instead — see the `isLocked` derivation below.
    const template = strategy.templateId
      ? researchTemplates.find((t) => t.id === strategy.templateId)
      : null;
    if (strategy.templateId === null || !template) {
      // No template mapping at all — fall through to the custom flow.
      setPickedSlug(strategy.slug);
      setTimeout(() => onPickCustom(strategy, answers), 400);
      return;
    }
    if (template.availability !== "ready") {
      // Template exists but isn't runnable yet — no-op (the button is
      // disabled in render too; this is the belt-and-braces guard).
      return;
    }
    setPickedSlug(strategy.slug);
    setTimeout(() => onPickTemplate({ template, answers, strategy }), 400);
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      {/* Intro */}
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/8 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-primary">
          Strategy Builder
        </div>
        <h2 className="font-heading text-2xl font-bold tracking-tight">
          Find the right strategy in 5 questions
        </h2>
        <p className="text-sm text-muted-foreground">
          One question at a time. You can jump back to change any answer.
        </p>
      </div>

      {/* Progress */}
      <div className="mt-6 flex items-center justify-center gap-3">
        <span className="text-xs text-muted-foreground">
          {showRecs ? (
            <span className="font-semibold text-emerald-700">All 5 answered</span>
          ) : (
            <>
              <span className="font-mono font-semibold text-foreground">{Math.min(currentIdx + 1, TOTAL_QUESTIONS)}</span>
              <span className="ml-1">of {TOTAL_QUESTIONS}</span>
            </>
          )}
        </span>
        <div className="flex gap-1">
          {Array.from({ length: TOTAL_QUESTIONS }, (_, i) => (
            <div
              key={i}
              className={cn(
                "h-1.5 rounded-full transition-all duration-300",
                i < answeredCount ? "w-6 bg-primary" : i === currentIdx ? "w-6 bg-primary/40" : "w-4 bg-border",
              )}
            />
          ))}
        </div>
      </div>

      {/* Answered chips (above the current question) */}
      {currentIdx > 0 && (
        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          {WIZARD_QUESTIONS.slice(0, currentIdx).map((q, idx) => {
            const val = answers[q.key];
            if (val === null) return null;
            const opt = q.options.find((o) => o.val === val);
            return (
              <button
                key={q.key}
                type="button"
                onClick={() => handleChipClick(idx)}
                className="group inline-flex items-center gap-1.5 rounded-full border border-emerald-300/60 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-900 transition-colors hover:border-emerald-400 hover:bg-emerald-100"
                aria-label={`Edit question ${idx + 1}: ${q.title}`}
              >
                <CheckCircle2 className="h-3 w-3 text-emerald-600" aria-hidden="true" />
                <span className="text-emerald-700/70">Q{idx + 1}:</span>
                <span className="font-semibold">{opt?.label ?? val}</span>
                <PencilIcon className="h-2.5 w-2.5 text-emerald-700/40 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden="true" />
              </button>
            );
          })}
        </div>
      )}

      {/* Current question (single, animated) */}
      {currentQ && (
        <div
          key={currentIdx}
          className="mt-8 animate-in fade-in slide-in-from-bottom-1 duration-300 ease-out"
        >
          <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Question {currentIdx + 1} of {TOTAL_QUESTIONS}
            </div>
            <h3 className="mt-1 font-heading text-xl font-bold tracking-tight">{currentQ.title}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{currentQ.sub}</p>
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              {currentQ.options.map((o) => {
                const isSelected = currentSelected === o.val;
                return (
                  <button
                    key={o.val}
                    type="button"
                    onClick={() => handlePickAnswer(o.val)}
                    aria-pressed={isSelected}
                    className={cn(
                      "group rounded-xl border px-3 py-2.5 text-left transition-all duration-150",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                      isSelected
                        ? "border-primary bg-primary/8 ring-1 ring-primary"
                        : "border-border hover:border-primary/40 hover:bg-muted/30",
                    )}
                  >
                    <div className="flex items-start gap-2.5">
                      <div
                        className={cn(
                          "mt-0.5 h-4 w-4 rounded-full border-2 transition-colors shrink-0 flex items-center justify-center",
                          isSelected ? "border-primary bg-primary" : "border-muted-foreground/40",
                        )}
                        aria-hidden="true"
                      >
                        {isSelected && (
                          <CheckCircle2 className="h-3 w-3 text-primary-foreground" />
                        )}
                      </div>
                      <div className="min-w-0">
                        <div className={cn("text-sm font-semibold", isSelected ? "text-foreground" : "text-foreground/80")}>
                          {o.label}
                        </div>
                        <div className="mt-0.5 text-xs text-muted-foreground leading-snug">
                          {o.desc}
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Back / Next */}
          <div className="mt-4 flex items-center justify-between">
            <button
              type="button"
              onClick={handleBack}
              disabled={currentIdx === 0}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium transition-colors",
                currentIdx === 0
                  ? "cursor-not-allowed text-muted-foreground/40"
                  : "text-foreground/80 hover:border-primary/40 hover:bg-muted/30",
              )}
            >
              <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
              Back
            </button>
            <button
              type="button"
              onClick={handleManualNext}
              disabled={currentSelected === null}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-sm font-semibold transition-colors",
                currentSelected === null
                  ? "cursor-not-allowed bg-muted text-muted-foreground/60"
                  : "bg-primary text-primary-foreground hover:bg-primary/90",
              )}
            >
              {currentIdx === TOTAL_QUESTIONS - 1 ? "See recommendations" : "Next"}
              <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        </div>
      )}

      {/* Recommendations panel */}
      {showRecs && (
        <div className="mt-8 animate-in fade-in slide-in-from-bottom-2 duration-500 ease-out">
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3">
            <div className="text-xs font-semibold uppercase tracking-wider text-emerald-700">
              Your top {recs.length} {recs.length === 1 ? "match" : "matches"}
            </div>
            <p className="mt-0.5 text-xs text-emerald-900/70">
              Ranked by fit across all 5 of your answers. Expand any card to see the full
              strategy brief and compare side-by-side before you pick.
            </p>
          </div>
          <div className="mt-3 space-y-3">
            {recs.map((s, i) => {
              const reasons = buildWhy(s, answers);
              const template = s.templateId ? researchTemplates.find((t) => t.id === s.templateId) : null;
              // A card is "locked" when the user can't actually backtest it:
              // either no template mapping exists (`templateId === null`),
              // OR the mapped template is shipped in the UI but isn't
              // runnable yet (e.g. fundamentals/sentiment templates whose
              // backend providers are not wired). PR-H, 2026-05-26.
              const isUnavailable = template != null && template.availability !== "ready";
              const isLocked = s.templateId === null || isUnavailable;
              const isExpanded = expandedSlugs.has(s.slug);
              const isPicked = pickedSlug === s.slug;
              const isFading = pickedSlug !== null && !isPicked;
              return (
                <div
                  key={s.slug}
                  className={cn(
                    "rounded-2xl border bg-card p-5 transition-all duration-400 ease-out",
                    i === 0 ? "border-primary/40" : "border-border",
                    isFading && "scale-95 opacity-0",
                    isPicked && "ring-2 ring-primary/40",
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={cn(
                          "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
                          i === 0
                            ? "bg-primary/10 text-primary"
                            : "bg-muted text-muted-foreground",
                        )}>
                          {i === 0 ? "Top match" : `Alt ${i}`}
                        </span>
                        <span className="rounded-full border border-border bg-muted/30 px-2 py-0.5 text-[10px] font-medium text-foreground/70">
                          Evidence {s.evidence}
                        </span>
                        <span className="rounded-full border border-border bg-muted/30 px-2 py-0.5 text-[10px] font-medium text-foreground/70">
                          {s.cap}
                        </span>
                        <span className="rounded-full border border-border bg-muted/30 px-2 py-0.5 text-[10px] font-medium text-foreground/70">
                          Drawdown: {s.drawdown}
                        </span>
                      </div>
                      <h4 className="mt-2 font-heading text-base font-semibold">{s.name}</h4>
                      <p className="mt-1 text-sm leading-snug text-foreground/80">{s.blurb}</p>
                    </div>
                  </div>
                  {reasons.length > 0 && (
                    <ul className="mt-3 space-y-0.5 border-l-2 border-primary/30 pl-3 text-xs text-muted-foreground">
                      {reasons.map((r) => (
                        <li key={r}>· {r}</li>
                      ))}
                    </ul>
                  )}
                  <div className="mt-3 rounded-lg bg-muted/30 px-3 py-2 text-xs text-foreground/80">
                    <span className="font-semibold">Example:</span> {s.example}
                  </div>

                  {/* Compare details toggle */}
                  <div className="mt-3 border-t border-border/60 pt-3">
                    <button
                      type="button"
                      onClick={() => toggleExpand(s.slug)}
                      disabled={pickedSlug !== null}
                      aria-expanded={isExpanded}
                      className={cn(
                        "inline-flex items-center gap-1.5 text-xs font-medium transition-colors",
                        pickedSlug !== null
                          ? "cursor-not-allowed text-muted-foreground/40"
                          : "text-muted-foreground hover:text-primary",
                      )}
                    >
                      {isExpanded ? (
                        <>
                          <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
                          Hide details
                        </>
                      ) : (
                        <>
                          <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                          Compare details
                        </>
                      )}
                    </button>
                    {isExpanded && (
                      <div className="mt-3 animate-in fade-in slide-in-from-top-1 duration-200">
                        {template ? (
                          <>
                            {isUnavailable && (
                              <div className="mb-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                                <span className="font-semibold">Backtest unavailable —</span>{" "}
                                this strategy needs data we haven&apos;t wired yet
                                (fundamentals or news sentiment). The strategy brief below is
                                accurate; running it is disabled until the data source ships.
                              </div>
                            )}
                            <StrategyBriefCard template={template} />
                          </>
                        ) : (
                          <div className="rounded-xl border border-dashed border-border bg-muted/20 px-4 py-6 text-center text-sm text-muted-foreground">
                            <Lock className="mx-auto h-4 w-4 text-muted-foreground/60" aria-hidden="true" />
                            <p className="mt-2 font-medium">Template details coming soon</p>
                            <p className="mt-0.5 text-xs">
                              This strategy isn&apos;t wired to a research template yet — the
                              custom flow will let you configure it manually.
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="mt-4">
                    {isLocked ? (
                      <button
                        type="button"
                        onClick={() => handlePick(s)}
                        disabled={pickedSlug !== null || isUnavailable}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted/40 px-3 py-1.5 text-xs font-medium text-muted-foreground disabled:cursor-not-allowed"
                      >
                        <Lock className="h-3 w-3" aria-hidden="true" />
                        {isUnavailable
                          ? "Coming soon — backtest disabled until data ships"
                          : "Template pending — use the custom flow"}
                        <ArrowRight className="h-3 w-3" aria-hidden="true" />
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handlePick(s)}
                        disabled={pickedSlug !== null}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-70"
                      >
                        Use this <ArrowRight className="h-4 w-4" aria-hidden="true" />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Empty-recs guard — extremely rare; only when scoring filters everything */}
      {currentIdx >= TOTAL_QUESTIONS && isComplete(answers) && recs.length === 0 && (
        <div className="mt-8 rounded-2xl border-2 border-dashed border-border bg-muted/20 px-6 py-8 text-center">
          <p className="text-sm text-muted-foreground">
            No clean matches for that combination. Try the custom flow below to describe
            what you have in mind.
          </p>
        </div>
      )}

      {/* Secondary: legacy free-text flow */}
      <div className="mt-8 border-t border-border pt-6 text-center">
        <button
          type="button"
          onClick={onDescribeIdea}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-primary"
        >
          <PencilIcon className="h-3 w-3" aria-hidden="true" />
          I already know what I want — describe my idea
          <ArrowRight className="h-3 w-3" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
