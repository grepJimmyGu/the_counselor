// Generates the parity fixture for LivermoreKit's Swift port of the risk
// presets, by running the web's own `applyRiskLevel` over every template the
// app ships.
//
//   node apps/ios/scripts/gen_risk_golden.mjs
//
// Re-run whenever apps/web/src/lib/strategy-picker/risk-presets.ts changes;
// the Swift test then fails until RiskLevel is changed to match.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const { applyRiskLevel, detectRiskPreset } = await import(
  resolve(here, "../../web/src/lib/strategy-picker/risk-presets.ts")
);
const { templates } = JSON.parse(
  readFileSync(resolve(here, "../LivermoreKit/Sources/LivermoreKit/Builder/templates.json"), "utf8"),
);
const out = resolve(here, "../LivermoreKit/Tests/LivermoreKitTests/Fixtures/risk-golden.json");

const cases = [];
for (const template of templates) {
  for (const level of ["low", "medium", "high"]) {
    const applied = applyRiskLevel(template.strategy, level);
    cases.push({
      template: template.id,
      level,
      position_sizing: applied.position_sizing,
      risk_management: applied.risk_management,
      detected: detectRiskPreset(applied),
    });
  }
}

writeFileSync(out, JSON.stringify({ cases }, null, 1) + "\n");
console.log(`wrote ${cases.length} cases to ${out}`);
