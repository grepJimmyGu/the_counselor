"use client";

import { useMemo, useState } from "react";
import { ArrowRight, CheckCircle2, Lock, PencilIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { researchTemplates, type ResearchTemplate } from "@/lib/contracts";
import {
  WIZARD_QUESTIONS,
  WIZARD_STRATEGIES,
  type AssetAnswer,
  type WizardAnswers,
  type WizardStrategy,
} from "./strategy-wizard-data";
import { buildWhy, isComplete, recommend } from "./strategy-wizard-recommend";

/**
 * Strategy-builder wizard — all 5 questions on a single scrollable
 * page (per the 2026-05-24 rebuild spec). As soon as all 5 are
 * answered, a live recommendation panel appears at the bottom with
 * the top 3 ranked strategies and "Use this →" buttons.
 *
 * Per the framework: question order is asset → goal → cadence →
 * behavior → drawdown. Asset is question 1 so the stock-detail entry
 * path can pre-fill it.
 *
 * Callback contract:
 *   onPickTemplate({ template, answers }) — fired when the user picks
 *   one of the recommended strategies AND that strategy has a
 *   matching `researchTemplates` entry. Modal transitions into the
 *   template-brief step from there.
 *
 *   onPickCustom(strategy) — fired when the recommended strategy
 *   has no matching researchTemplate (`templateId === null`). Modal
 *   drops into the custom flow with the wizard's selected slug as a
 *   hint.
 *
 *   onDescribeIdea() — fired by the "I already know what I want →"
 *   secondary link at the bottom of the page, dropping the user
 *   into the legacy `custom-2` free-text flow.
 */

export interface StrategyWizardProps {
  /** Pre-fill asset answer when entering from a stock-detail page.
   *  When `single_stock` is pre-filled, the answer chip appears
   *  already selected so the user can scroll past or change. */
  initialAsset?: AssetAnswer;
  onPickTemplate: (payload: { template: ResearchTemplate; answers: WizardAnswers; strategy: WizardStrategy }) => void;
  onPickCustom: (strategy: WizardStrategy, answers: WizardAnswers) => void;
  onDescribeIdea: () => void;
}

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

  function setAnswer<K extends keyof WizardAnswers>(key: K, value: WizardAnswers[K]): void {
    setAnswers((prev) => ({ ...prev, [key]: value }));
  }

  const recs = useMemo(
    () => (isComplete(answers) ? recommend(WIZARD_STRATEGIES, answers, 3) : []),
    [answers],
  );
  const answeredCount = Object.values(answers).filter((v) => v !== null).length;
  const ready = isComplete(answers) && recs.length > 0;

  function handlePick(strategy: WizardStrategy): void {
    if (strategy.templateId === null) {
      onPickCustom(strategy, answers);
      return;
    }
    const template = researchTemplates.find((t) => t.id === strategy.templateId);
    if (!template) {
      // Slug map drifted — fall back to custom
      onPickCustom(strategy, answers);
      return;
    }
    onPickTemplate({ template, answers, strategy });
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
          Answer all 5 below. Your recommendations appear at the bottom — no
          wrong answers, no Next button to click.
        </p>
      </div>

      {/* Progress */}
      <div className="mt-6 flex items-center justify-center gap-2 text-xs text-muted-foreground">
        <span className="font-mono font-semibold text-foreground">{answeredCount}</span>
        <span>of 5 answered</span>
        <div className="ml-2 flex gap-1">
          {[0, 1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className={cn(
                "h-1.5 w-5 rounded-full transition-colors",
                i < answeredCount ? "bg-primary" : "bg-border",
              )}
            />
          ))}
        </div>
      </div>

      {/* Questions — all 5 on one page */}
      <div className="mt-8 space-y-6">
        {WIZARD_QUESTIONS.map((q, idx) => {
          const selected = answers[q.key];
          return (
            <fieldset
              key={q.key}
              className="rounded-2xl border border-border bg-card p-5"
            >
              <legend className="px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Question {idx + 1} of 5
              </legend>
              <h3 className="font-heading text-base font-semibold">{q.title}</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">{q.sub}</p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {q.options.map((o) => {
                  const isSelected = selected === o.val;
                  return (
                    <button
                      key={o.val}
                      type="button"
                      onClick={() => setAnswer(q.key, o.val as WizardAnswers[typeof q.key])}
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
                            "mt-0.5 h-4 w-4 rounded-full border-2 transition-colors shrink-0",
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
            </fieldset>
          );
        })}
      </div>

      {/* Recommendations panel */}
      <div className="mt-10">
        {!ready ? (
          <div className="rounded-2xl border-2 border-dashed border-border bg-muted/20 px-6 py-8 text-center">
            <p className="text-sm text-muted-foreground">
              Recommendations will appear here once you answer all 5 questions.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3">
              <div className="text-xs font-semibold uppercase tracking-wider text-emerald-700">
                Your top {recs.length} {recs.length === 1 ? "match" : "matches"}
              </div>
              <p className="mt-0.5 text-xs text-emerald-900/70">
                Ranked by fit across all 5 of your answers. Three close matches?
                Tie-breakers live in the Strategy Picker framework doc.
              </p>
            </div>
            {recs.map((s, i) => {
              const reasons = buildWhy(s, answers);
              const isLocked = s.templateId === null;
              return (
                <div
                  key={s.slug}
                  className={cn(
                    "rounded-2xl border bg-card p-5",
                    i === 0 ? "border-primary/40" : "border-border",
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
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
                  <div className="mt-4">
                    {isLocked ? (
                      <button
                        type="button"
                        onClick={() => handlePick(s)}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted/40 px-3 py-1.5 text-xs font-medium text-muted-foreground"
                      >
                        <Lock className="h-3 w-3" aria-hidden="true" />
                        Template pending — use the custom flow
                        <ArrowRight className="h-3 w-3" aria-hidden="true" />
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handlePick(s)}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                      >
                        Use this <ArrowRight className="h-4 w-4" aria-hidden="true" />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

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
