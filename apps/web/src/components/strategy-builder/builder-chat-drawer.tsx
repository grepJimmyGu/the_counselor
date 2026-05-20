"use client";

import { FormEvent, useMemo, useState } from "react";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  Loader2,
  MessageSquareText,
  Sparkles,
  Wand2,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { parseStrategy } from "@/lib/api";
import {
  researchTemplates,
  type BacktestResult,
  type StrategyJson,
} from "@/lib/contracts";
import { cn } from "@/lib/utils";

export type BuilderChatSourcePage = "home" | "stock_detail" | "templates" | "workspace";

export interface BuilderChatContext {
  source_page: BuilderChatSourcePage;
  current_ticker?: string;
  selected_template_id?: string;
  current_strategy_json?: StrategyJson | null;
  current_backtest_result?: BacktestResult | null;
}

export type BuilderChatAction =
  | { type: "draft_strategy"; strategyJson: StrategyJson; message: string }
  | { type: "open_builder_preview"; strategyJson: StrategyJson }
  | { type: "explain_backtest_result"; explanation: string }
  | { type: "suggest_strategy_edit"; patch: Partial<StrategyJson>; rationale: string }
  | { type: "apply_strategy_edit_to_preview"; patch: Partial<StrategyJson> };

type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
  action?: BuilderChatAction;
};

interface BuilderChatDrawerProps {
  context: BuilderChatContext;
  onPreviewStrategy: (strategyJson: StrategyJson) => void;
  triggerLabel?: string;
  triggerClassName?: string;
  triggerSize?: "sm" | "default" | "lg";
}

function createId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function templateFor(id?: string) {
  return id ? researchTemplates.find((template) => template.id === id) : undefined;
}

function templateForStrategy(strategy?: StrategyJson | null) {
  if (!strategy) return undefined;
  return researchTemplates.find(
    (template) =>
      template.strategy.strategy_type === strategy.strategy_type &&
      template.availability !== "unavailable",
  );
}

function sourceLabel(source: BuilderChatSourcePage) {
  if (source === "stock_detail") return "Stock Detail";
  if (source === "workspace") return "Strategy Results";
  if (source === "templates") return "Templates";
  return "Home";
}

function initialAssistantText(context: BuilderChatContext) {
  if (context.source_page === "workspace" && context.current_backtest_result) {
    return "I can explain this historical backtest or suggest an editable strategy iteration. I will only open changes in preview.";
  }
  if (context.current_ticker) {
    return `Tell me what kind of paper strategy you want to test for ${context.current_ticker}. I will draft it, then you can review it before running a backtest.`;
  }
  if (context.selected_template_id) {
    const template = templateFor(context.selected_template_id);
    return `I can help adapt ${template?.name ?? "this template"} into a structured paper strategy draft.`;
  }
  return "Describe a paper strategy idea in plain language. I will draft it and send it to preview before anything runs.";
}

function composeParserPrompt(input: string, context: BuilderChatContext) {
  const parts: string[] = [];
  const template = templateFor(context.selected_template_id);

  if (context.current_ticker) {
    parts.push(`Current ticker context: ${context.current_ticker}. Use this ticker as the default universe unless the user names other tickers.`);
  }

  if (template) {
    parts.push(`Selected template context: ${template.name}. Template seed: ${template.chatSeed || template.description}`);
  }

  if (context.current_strategy_json) {
    parts.push("The user may be modifying the current strategy. Preserve existing fields unless the message clearly changes them.");
  }

  parts.push(`User message: ${input}`);
  return parts.join("\n\n");
}

function describeResult(result: BacktestResult) {
  const metrics = result.metrics;
  const warningText = result.warnings.length
    ? `\nWarnings: ${result.warnings.slice(0, 3).join("; ")}`
    : "";

  return [
    `Historical result for ${result.strategy_json.strategy_name}:`,
    `Total return ${formatPercent(metrics.total_return)}, annualized return ${formatPercent(metrics.annualized_return)}, Sharpe ${metrics.sharpe_ratio.toFixed(2)}, max drawdown ${formatPercent(metrics.max_drawdown)}.`,
    `Benchmark comparison: ${formatPercent(metrics.excess_return_vs_benchmark)} excess return across ${metrics.number_of_trades} trades.`,
    `This is a backtest summary, not financial advice.${warningText}`,
  ].join("\n\n");
}

function buildEditSuggestion(strategy: StrategyJson, result: BacktestResult): {
  patch: Partial<StrategyJson>;
  rationale: string;
} {
  const metrics = result.metrics;

  if (metrics.max_drawdown < -0.25 && !strategy.risk_management.stop_loss_pct) {
    return {
      patch: {
        risk_management: {
          ...strategy.risk_management,
          stop_loss_pct: 0.08,
        },
      },
      rationale: "The drawdown was deep, so the first candidate edit is adding an 8% stop-loss for preview and retesting.",
    };
  }

  if (metrics.turnover > 6 && strategy.rebalance_frequency !== "monthly" && strategy.rebalance_frequency !== "quarterly") {
    return {
      patch: { rebalance_frequency: "monthly" },
      rationale: "Turnover is high, so the first candidate edit is switching the preview to monthly rebalancing to reduce trading friction.",
    };
  }

  const currentMax = strategy.position_sizing.max_positions ?? strategy.universe.length;
  if (currentMax < 20 && strategy.universe.length >= 20) {
    return {
      patch: {
        position_sizing: {
          ...strategy.position_sizing,
          max_positions: 20,
        },
      },
      rationale: "The strategy is fairly concentrated, so the first candidate edit is broadening the preview to 20 positions.",
    };
  }

  return {
    patch: {
      transaction_cost_bps: Math.max(strategy.transaction_cost_bps, 10),
      slippage_bps: Math.max(strategy.slippage_bps, 10),
    },
    rationale: "The first candidate edit is a more conservative cost assumption so the next preview stress-tests trading friction.",
  };
}

function applyPatchToStrategy(strategy: StrategyJson, patch: Partial<StrategyJson>): StrategyJson {
  return {
    ...strategy,
    ...patch,
    position_sizing: {
      ...strategy.position_sizing,
      ...(patch.position_sizing ?? {}),
    },
    risk_management: {
      ...strategy.risk_management,
      ...(patch.risk_management ?? {}),
    },
    cash_management: {
      ...strategy.cash_management,
      ...(patch.cash_management ?? {}),
    },
  };
}

export function BuilderChatDrawer({
  context,
  onPreviewStrategy,
  triggerLabel = "Builder Chat",
  triggerClassName,
  triggerSize = "sm",
}: BuilderChatDrawerProps) {
  const router = useRouter();
  const { data: session, status } = useSession();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    {
      id: "initial",
      role: "assistant",
      content: initialAssistantText(context),
    },
  ]);

  const selectedTemplate = templateFor(context.selected_template_id);
  const activeTemplate = selectedTemplate ?? templateForStrategy(context.current_strategy_json);
  const hasResult = Boolean(context.current_strategy_json && context.current_backtest_result);

  const placeholder = useMemo(() => {
    if (context.current_ticker) return `e.g. Test monthly momentum on ${context.current_ticker}`;
    if (activeTemplate) return `e.g. Adapt ${activeTemplate.name} for large-cap tech stocks`;
    return "e.g. Test a monthly momentum strategy on AAPL, MSFT, and NVDA";
  }, [activeTemplate, context.current_ticker]);

  function requireSignedInAndOpen() {
    if (status === "loading") return;
    if (!session?.user) {
      const callbackUrl =
        typeof window === "undefined"
          ? "/"
          : `${window.location.pathname}${window.location.search}`;
      router.push(`/login?callbackUrl=${encodeURIComponent(callbackUrl)}` as Route);
      return;
    }
    setMessages((prev) =>
      prev.length === 1 && prev[0]?.id === "initial"
        ? [{ ...prev[0], content: initialAssistantText(context) }]
        : prev,
    );
    setOpen(true);
  }

  function closeDrawer() {
    setOpen(false);
  }

  function addAssistant(content: string, action?: BuilderChatAction) {
    setMessages((prev) => [
      ...prev,
      {
        id: createId("assistant"),
        role: "assistant",
        content,
        action,
      },
    ]);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || loading) return;

    setInput("");
    setLoading(true);
    setMessages((prev) => [
      ...prev,
      { id: createId("user"), role: "user", content: trimmed },
    ]);

    try {
      const response = await parseStrategy(
        composeParserPrompt(trimmed, context),
        context.current_strategy_json ?? null,
      );

      if (response.strategy_json && response.validation_status === "valid") {
        const note = response.approximation_note ? `\n\nApproximation note: ${response.approximation_note}` : "";
        addAssistant(
          `${response.assistant_message}\n\nI prepared a paper strategy draft. Review it in the builder before running a backtest.${note}`,
          {
            type: "draft_strategy",
            strategyJson: response.strategy_json,
            message: response.assistant_message,
          },
        );
        return;
      }

      const questions = response.clarification_questions.length
        ? `\n\nClarifying questions:\n${response.clarification_questions.map((q) => `- ${q}`).join("\n")}`
        : "";
      const unsupported = response.unsupported_reason
        ? `\n\nUnsupported for V1: ${response.unsupported_reason}`
        : "";
      const reformulation = response.suggested_reformulation
        ? `\n\nSuggested reformulation: ${response.suggested_reformulation}`
        : "";

      addAssistant(`${response.assistant_message}${questions}${unsupported}${reformulation}`);
    } catch (error) {
      addAssistant(error instanceof Error ? error.message : "I could not draft that strategy yet. Please try a simpler description.");
    } finally {
      setLoading(false);
    }
  }

  function handleExplainResult() {
    if (!context.current_backtest_result) {
      addAssistant("Run a backtest first, then I can explain the historical result.");
      return;
    }

    const explanation = describeResult(context.current_backtest_result);
    addAssistant(explanation, {
      type: "explain_backtest_result",
      explanation,
    });
  }

  function handleSuggestEdit() {
    if (!context.current_strategy_json || !context.current_backtest_result) {
      addAssistant("I need a loaded strategy and completed backtest result before suggesting an edit.");
      return;
    }

    const suggestion = buildEditSuggestion(context.current_strategy_json, context.current_backtest_result);
    addAssistant(`Suggested preview edit: ${suggestion.rationale}`, {
      type: "suggest_strategy_edit",
      patch: suggestion.patch,
      rationale: suggestion.rationale,
    });
  }

  function handleAction(action: BuilderChatAction) {
    if (action.type === "draft_strategy" || action.type === "open_builder_preview") {
      onPreviewStrategy(action.type === "draft_strategy" ? action.strategyJson : action.strategyJson);
      closeDrawer();
      return;
    }

    if (action.type === "suggest_strategy_edit" && context.current_strategy_json) {
      onPreviewStrategy(applyPatchToStrategy(context.current_strategy_json, action.patch));
      closeDrawer();
    }
  }

  function actionLabel(action: BuilderChatAction) {
    if (action.type === "draft_strategy" || action.type === "open_builder_preview") return "Review in builder";
    if (action.type === "suggest_strategy_edit") return "Review suggested edit";
    return null;
  }

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size={triggerSize}
        onClick={requireSignedInAndOpen}
        className={cn("gap-1.5", triggerClassName)}
        disabled={status === "loading"}
      >
        {status === "loading" ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <MessageSquareText className="h-4 w-4" />
        )}
        {triggerLabel}
      </Button>

      {open && (
        <div className="fixed inset-0 z-[70]" role="dialog" aria-modal="true" aria-label="Builder Chat">
          <button
            type="button"
            aria-label="Close builder chat"
            onClick={closeDrawer}
            className="absolute inset-0 cursor-default bg-background/60 backdrop-blur-sm"
          />
          <aside className="absolute inset-y-0 right-0 flex w-full max-w-[440px] flex-col border-l border-border bg-background shadow-2xl">
            <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Bot className="h-4 w-4" />
                </div>
                <div>
                  <div className="text-sm font-semibold">Builder Chat</div>
                  <div className="text-[11px] text-muted-foreground">{sourceLabel(context.source_page)}</div>
                </div>
              </div>
              <button
                type="button"
                onClick={closeDrawer}
                aria-label="Close builder chat"
                className="cursor-pointer rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <X className="h-4 w-4" />
              </button>
            </header>

            <div className="border-b border-border bg-muted/20 px-4 py-3">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant="outline" className="text-[10px]">Signed-in V1</Badge>
                {context.current_ticker && <Badge variant="outline" className="font-mono text-[10px]">{context.current_ticker}</Badge>}
                {activeTemplate && <Badge variant="outline" className="text-[10px]">{activeTemplate.name}</Badge>}
              </div>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                Research tooling only. Outputs are paper strategies and historical backtests, not financial advice.
              </p>
            </div>

            <ScrollArea className="min-h-0 flex-1 px-4 py-4">
              <div className="space-y-3">
                {messages.map((message) => {
                  const label = message.action ? actionLabel(message.action) : null;
                  return (
                    <div
                      key={message.id}
                      className={cn(
                        "rounded-xl border px-3 py-2.5 text-sm leading-relaxed",
                        message.role === "user"
                          ? "ml-8 border-primary/20 bg-primary/8 text-foreground"
                          : "mr-8 border-border bg-card",
                      )}
                    >
                      <div className="whitespace-pre-wrap">{message.content}</div>
                      {message.action?.type === "draft_strategy" && (
                        <div className="mt-2 flex items-center gap-1.5 rounded-lg border border-emerald-500/20 bg-emerald-500/8 px-2 py-1.5 text-xs text-emerald-700">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Structured draft ready
                        </div>
                      )}
                      {label && (
                        <Button
                          type="button"
                          size="sm"
                          onClick={() => handleAction(message.action!)}
                          className="mt-3 gap-1.5"
                        >
                          {label}
                          <ArrowRight className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>
                  );
                })}
                {loading && (
                  <div className="mr-8 flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2.5 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Drafting from parser...
                  </div>
                )}
              </div>
            </ScrollArea>

            <div className="shrink-0 border-t border-border p-4">
              {hasResult && (
                <div className="mb-3 grid grid-cols-2 gap-2">
                  <Button type="button" variant="outline" size="sm" onClick={handleExplainResult} className="gap-1.5">
                    <Sparkles className="h-3.5 w-3.5" />
                    Explain result
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={handleSuggestEdit} className="gap-1.5">
                    <Wand2 className="h-3.5 w-3.5" />
                    Suggest edit
                  </Button>
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-2">
                <Textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  placeholder={placeholder}
                  rows={3}
                  className="max-h-32 resize-none text-sm"
                />
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-1.5 text-[11px] leading-snug text-muted-foreground">
                    <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-500" />
                    Preview required before any backtest.
                  </div>
                  <Button type="submit" disabled={loading || input.trim().length < 3} className="gap-1.5">
                    Draft
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </form>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
