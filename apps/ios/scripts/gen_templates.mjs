// Exports the website's strategy templates for the iOS app.
//
//   node apps/ios/scripts/gen_templates.mjs           # rewrite templates.json
//   node apps/ios/scripts/gen_templates.mjs --check   # exit 1 if it is stale
//
// The template catalogue is data in apps/web/src/lib/contracts.ts
// (`researchTemplates`), not something the backend serves, so the app carries
// a copy. Run this whenever that list changes; `--check` is what tells you it
// has.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const { researchTemplates } = await import(resolve(here, "../../web/src/lib/contracts.ts"));
const out = resolve(here, "../LivermoreKit/Sources/LivermoreKit/Builder/templates.json");

const KEEP = [
  "id", "name", "category", "description", "whatItCaptures", "whatItTests",
  "dataRequirement", "universeDescription", "defaultTickers", "multiTicker",
  "tickerLabel", "minTickers", "availability", "dataGapReason", "etfProxyCaveat",
  "evidenceTier", "horizonBadge", "caveats", "whenInCopy", "whenOutCopy",
  "perfContext", "academicRef", "comingSoon",
];

const templates = researchTemplates.map((t) => {
  const row = {};
  for (const key of KEEP) if (t[key] !== undefined) row[key] = t[key];
  // The web stamps start/end dates when the module loads. The app sets them
  // when the user runs the backtest, so fixed placeholders keep this file
  // from changing every day.
  row.strategy = { ...t.strategy, start_date: "2000-01-01", end_date: "2000-01-02" };
  return row;
});

const text = JSON.stringify({ source: "apps/web/src/lib/contracts.ts", templates }, null, 1) + "\n";

if (process.argv.includes("--check")) {
  const current = (() => { try { return readFileSync(out, "utf8"); } catch { return ""; } })();
  if (current !== text) {
    console.error("templates.json is out of date — run: node apps/ios/scripts/gen_templates.mjs");
    process.exit(1);
  }
  console.log(`templates.json is current (${templates.length} templates)`);
} else {
  writeFileSync(out, text);
  console.log(`${templates.length} templates -> ${out}`);
}
