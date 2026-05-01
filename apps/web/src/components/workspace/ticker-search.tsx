"use client";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";

import { searchSymbols } from "@/lib/api";
import type { SymbolSearchItem } from "@/lib/contracts";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface TickerSearchProps {
  value: string[];
  onChange: (universe: string[]) => void;
  maxSymbols?: number;
  disabled?: boolean;
}

export function TickerSearch({
  value,
  onChange,
  maxSymbols = 10,
  disabled = false,
}: TickerSearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SymbolSearchItem[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.length < 1) {
      setResults([]);
      setIsOpen(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setIsLoading(true);
      try {
        const found = await searchSymbols(query);
        setResults(found);
        setIsOpen(found.length > 0);
      } catch {
        setResults([]);
        setIsOpen(false);
      } finally {
        setIsLoading(false);
      }
    }, 350);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  useEffect(() => {
    function handleOutsideClick(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  function addSymbol(symbol: string) {
    const upper = symbol.toUpperCase();
    if (!value.includes(upper) && value.length < maxSymbols) {
      onChange([...value, upper]);
    }
    setQuery("");
    setIsOpen(false);
  }

  function removeSymbol(symbol: string) {
    onChange(value.filter((s) => s !== symbol));
  }

  const atLimit = value.length >= maxSymbols;

  return (
    <div ref={containerRef} className="relative space-y-2">
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {value.map((sym) => (
            <Badge key={sym} variant="secondary" className="gap-1 pr-1">
              {sym}
              <button
                type="button"
                onClick={() => removeSymbol(sym)}
                disabled={disabled}
                className="ml-0.5 rounded-sm opacity-60 transition hover:opacity-100 disabled:pointer-events-none"
                aria-label={`Remove ${sym}`}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
      <Input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={atLimit ? `Max ${maxSymbols} symbols` : "Search ticker or company name..."}
        disabled={disabled || atLimit}
        autoComplete="off"
      />
      {isLoading && (
        <p className="text-xs text-muted-foreground">Searching…</p>
      )}
      {isOpen && results.length > 0 && (
        <div className="absolute z-50 w-full overflow-hidden rounded-lg border border-border bg-background shadow-lg">
          {results.map((item) => {
            const already = value.includes(item.symbol);
            return (
              <button
                key={item.symbol}
                type="button"
                onClick={() => addSymbol(item.symbol)}
                disabled={already || atLimit}
                className={cn(
                  "flex w-full items-center justify-between px-3 py-2 text-sm transition hover:bg-muted",
                  (already || atLimit) && "pointer-events-none opacity-40",
                )}
              >
                <div className="flex min-w-0 items-center gap-2">
                  <span className="font-medium">{item.symbol}</span>
                  <span className="truncate text-muted-foreground">{item.name}</span>
                </div>
                <div className="ml-2 flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
                  {item.instrument_type && <span>{item.instrument_type}</span>}
                  {item.region && <span>{item.region}</span>}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
