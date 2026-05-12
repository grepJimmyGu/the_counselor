"use client";

import { useState } from "react";

interface UniverseInputProps {
  defaultValue: string[];
  minTickers?: number;
  placeholder?: string;
  onChange: (tickers: string[]) => void;
}

export function UniverseInput({
  defaultValue,
  minTickers = 2,
  placeholder,
  onChange,
}: UniverseInputProps) {
  const [raw, setRaw] = useState(defaultValue.join(", "));
  const [error, setError] = useState<string | null>(null);

  function parse(value: string): string[] {
    return value
      .split(",")
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);
  }

  function handleChange(value: string) {
    setRaw(value);
    const tickers = parse(value);
    if (tickers.length < minTickers) {
      setError(`Enter at least ${minTickers} tickers separated by commas`);
      onChange([]);
    } else {
      setError(null);
      onChange(tickers);
    }
  }

  return (
    <div className="space-y-1">
      <input
        type="text"
        value={raw}
        onChange={(e) => handleChange(e.target.value.toUpperCase())}
        placeholder={placeholder ?? defaultValue.join(", ")}
        inputMode="search"
        autoCapitalize="characters"
        autoCorrect="off"
        spellCheck={false}
        className="w-full rounded-md border border-border bg-input px-3 py-2 text-sm font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
      />
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
