"use client";

import { useLocale } from "@/lib/locale-context";

export function LanguageSwitcher() {
  const { locale, setLocale } = useLocale();

  return (
    <button
      type="button"
      onClick={() => setLocale(locale === "en" ? "zh" : "en")}
      className="rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground transition hover:border-primary/40 hover:text-foreground"
    >
      {locale === "en" ? "中文" : "English"}
    </button>
  );
}
