import Foundation
import LivermoreAPI
import Testing

@testable import LivermoreKit

private func template(_ id: String) -> StrategyTemplate {
    TemplateCatalog.all.first { $0.id == id }!
}

private func rule(_ strategy: StrategyJSON) -> Components.Schemas.StrategyRule {
    strategy.rules!.first!
}

@Suite("risk presets match the website")
struct RiskLevelParityTests {
    private struct Golden: Decodable {
        struct Case: Decodable {
            let template: String
            let level: String
            let position_sizing: Components.Schemas.PositionSizing
            let risk_management: Components.Schemas.RiskManagement
            let detected: String
        }

        let cases: [Case]
    }

    private func golden() throws -> Golden {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/risk-golden.json")
        return try JSONDecoder().decode(Golden.self, from: Data(contentsOf: url))
    }

    @Test("every template × level produces the web's sizing and risk blocks")
    func parity() throws {
        let cases = try golden().cases
        #expect(cases.count == TemplateCatalog.all.count * 3)
        for item in cases {
            let level = try #require(RiskLevel(rawValue: item.level))
            let applied = level.apply(to: template(item.template).strategy)
            #expect(applied.positionSizing == item.position_sizing, "\(item.template) \(item.level) sizing")
            #expect(applied.riskManagement == item.risk_management, "\(item.template) \(item.level) risk")
            // The web reports "high" for a strategy with no volatility
            // target; the app reports nil, meaning "as the template has it".
            #expect(RiskLevel.detect(in: applied) == (item.detected == "high" ? nil : level))
        }
    }

    @Test("applying a level twice is the same as applying it once")
    func idempotent() {
        let base = template("trend-following").strategy
        #expect(RiskLevel.low.apply(to: RiskLevel.low.apply(to: base)) == RiskLevel.low.apply(to: base))
    }
}

@Suite("ExitPlan")
struct ExitPlanTests {
    @Test("the standard plan is a stop, a half exit and a final exit, ascending")
    func standardTiers() {
        let tiers = ExitPlan.standard.tiers
        #expect(tiers.map(\.triggerPct) == [-0.08, 0.15, 0.30])
        #expect(tiers.map(\.action) == [.sellAll, .sellFraction, .sellAll])
        #expect(tiers.map(\.fraction) == [nil, 0.5, nil])
        #expect(tiers.map(\.label) == ["Stop · −8%", "Target 1 · +15%", "Target 2 · +30%"])
    }

    @Test("a stop alone is a valid plan, and a lone final target is Target 1")
    func partialPlans() {
        #expect(ExitPlan(stopPercent: 6.5).tiers.map(\.triggerPct) == [-0.065])
        #expect(ExitPlan(stopPercent: 6.5).problem == nil)
        let stopAndTarget = ExitPlan(stopPercent: 10, finalTargetPercent: 25).tiers
        #expect(stopAndTarget.map(\.label) == ["Stop · −10%", "Target 1 · +25%"])
    }

    @Test("percentages convert to exact fractions")
    func exactFractions() {
        // 0.07 * 100 style drift is what the rounding guards against.
        for percent in [7.0, 12.5, 33.33, 0.1] {
            let trigger = ExitPlan(stopPercent: percent).tiers[0].triggerPct
            #expect(trigger == -Double(String(format: "%.6f", percent / 100))!)
        }
    }

    @Test("plans the backend would refuse are caught first")
    func problems() {
        #expect(ExitPlan(stopPercent: 0).problem != nil)
        #expect(ExitPlan(stopPercent: 100).problem != nil)
        #expect(ExitPlan(stopPercent: 8, firstTargetPercent: 20, finalTargetPercent: 15).problem != nil)
        #expect(ExitPlan(stopPercent: 8, firstTargetPercent: 20, finalTargetPercent: 20).problem != nil)
        #expect(ExitPlan(stopPercent: 8, firstTargetPercent: 20, firstTargetFraction: 1).problem != nil)
        #expect(ExitPlan(stopPercent: 8, firstTargetPercent: -5).problem != nil)
        #expect(ExitPlan.standard.problem == nil)
    }

    @Test("a ladder reads back into the plan that made it")
    func roundTrip() {
        for plan in [ExitPlan.standard, ExitPlan(stopPercent: 5), ExitPlan(stopPercent: 12, finalTargetPercent: 40),
                     ExitPlan(stopPercent: 6, firstTargetPercent: 10, firstTargetFraction: 0.25)] {
            #expect(ExitPlan(tiers: plan.tiers) == plan)
        }
    }

    @Test("ladders with more tiers than the screen shows are not squeezed into it")
    func unrepresentable() {
        let three = [
            ExitTier(action: .sellAll, triggerPct: -0.1),
            ExitTier(action: .sellFraction, fraction: 0.33, triggerPct: 0.1),
            ExitTier(action: .sellFraction, fraction: 0.33, triggerPct: 0.2),
            ExitTier(action: .sellAll, triggerPct: 0.3),
        ]
        #expect(ExitPlan(tiers: three) == nil)
        #expect(ExitPlan(tiers: [ExitTier(action: .sellFraction, fraction: 0.5, triggerPct: 0.1)]) == nil)
    }
}

@Suite("StrategyCustomization")
struct StrategyCustomizationTests {
    @Test("applying a strategy's own settings changes nothing, for every template")
    func identity() {
        for template in TemplateCatalog.all {
            let custom = StrategyCustomization(strategy: template.strategy)
            #expect(custom.apply(to: template.strategy) == template.strategy, "\(template.id)")
            #expect(custom.changeCount(from: template.strategy) == 0, "\(template.id)")
            #expect(custom.problem == nil, "\(template.id)")
        }
    }

    @Test("each runnable template exposes the numbers its rule uses, with labels")
    func parameters() {
        let trend = StrategyCustomization(strategy: template("trend-following").strategy)
        #expect(trend.parameters.map(\.key) == [.entryWindow, .exitWindow])
        #expect(trend.parameters.map(\.label) == ["Buy on a new high over", "Sell on a new low over"])
        #expect(trend.parameters.map(\.formatted) == ["20 days", "10 days"])

        let lowVol = StrategyCustomization(strategy: template("low-volatility").strategy)
        #expect(lowVol.parameters.map(\.formatted) == ["63 days", "20%"])

        let bollinger = StrategyCustomization(strategy: template("bollinger-mean-reversion").strategy)
        #expect(bollinger.parameters.map(\.formatted) == ["20 days", "2.0×"])

        for template in TemplateCatalog.runnable {
            let custom = StrategyCustomization(strategy: template.strategy)
            #expect(!custom.parameters.isEmpty, "\(template.id) has nothing to tune")
            #expect(custom.parameters.allSatisfy { $0.range.contains($0.value) }, "\(template.id)")
        }
    }

    @Test("changed settings land in the strategy the backend receives")
    func applies() {
        let base = template("trend-following").strategy
        var custom = StrategyCustomization(strategy: base)
        custom.initialCapital = 25_000
        custom.transactionCostBps = 0
        custom.slippageBps = 2
        custom.parameters[0].value = 55
        custom.riskLevel = .low
        custom.setExitPlan(enabled: true)

        let built = custom.apply(to: base)
        #expect(built.initialCapital == 25_000)
        #expect(built.transactionCostBps == 0)
        #expect(built.slippageBps == 2)
        #expect(rule(built).entryWindow == 55)
        #expect(rule(built).exitWindow == 10)
        #expect(built.positionSizing.method == .volTarget)
        #expect(built.positionSizing.targetVolAnnual == 0.08)
        #expect(built.positionSizing.maxPositions == 1)
        #expect(built.riskManagement?.exitLadder == ExitPlan.standard.tiers)
        #expect(custom.changeCount(from: base) == 5)
        // Untouched parts of the strategy survive.
        #expect(built.universe == base.universe)
        #expect(built.strategyType == base.strategyType)
        #expect(built.rebalanceFrequency == base.rebalanceFrequency)
    }

    @Test("a customised result re-opens with the settings that produced it")
    func reopens() {
        let base = template("low-volatility").strategy
        var custom = StrategyCustomization(strategy: base)
        custom.riskLevel = .medium
        custom.exitPlan = ExitPlan(stopPercent: 10, finalTargetPercent: 25)
        custom.parameters[1].value = 0.3
        let built = custom.apply(to: base)

        let reopened = StrategyCustomization(strategy: built)
        #expect(reopened.riskLevel == .medium)
        #expect(reopened.exitPlan == ExitPlan(stopPercent: 10, finalTargetPercent: 25))
        #expect(reopened.parameters[1].value == 0.3)
        #expect(reopened.apply(to: built) == built)
    }

    @Test("raising the risk level removes a volatility target a lower one set")
    func raisesRisk() {
        let low = RiskLevel.low.apply(to: template("trend-following").strategy)
        var custom = StrategyCustomization(strategy: low)
        #expect(custom.riskLevel == .low)
        custom.riskLevel = .high
        let built = custom.apply(to: low)
        #expect(built.positionSizing.method == .equalWeight)
        #expect(built.positionSizing.targetVolAnnual == nil)
        #expect(built.riskManagement?.maxDrawdownStop == 0.40)
    }

    @Test("turning the exit plan off removes the ladder; a ladder the screen can't show is left alone")
    func ladderHandling() {
        var withPlan = template("trend-following").strategy
        withPlan.riskManagement?.exitLadder = ExitPlan.standard.tiers
        var custom = StrategyCustomization(strategy: withPlan)
        #expect(custom.exitPlan == .standard)
        custom.setExitPlan(enabled: false)
        #expect(custom.apply(to: withPlan).riskManagement?.exitLadder == nil)

        let complex = [
            ExitTier(action: .sellAll, triggerPct: -0.1),
            ExitTier(action: .sellFraction, fraction: 0.33, triggerPct: 0.1),
            ExitTier(action: .sellFraction, fraction: 0.33, triggerPct: 0.2),
        ]
        var odd = template("trend-following").strategy
        odd.riskManagement?.exitLadder = complex
        let untouched = StrategyCustomization(strategy: odd)
        #expect(untouched.exitPlan == nil)
        #expect(untouched.keepsOriginalLadder)
        #expect(untouched.apply(to: odd).riskManagement?.exitLadder == complex)
    }

    @Test("settings that can't run are named before the request is made")
    func problems() {
        let pairs = template("pairs-trading-long-only").strategy
        var custom = StrategyCustomization(strategy: pairs)
        let exit = custom.parameters.firstIndex { $0.key == .zscoreExit }!
        custom.parameters[exit].value = 2.5
        #expect(custom.problem?.contains("exit level") == true)

        var cheap = StrategyCustomization(strategy: template("trend-following").strategy)
        cheap.initialCapital = 50
        #expect(cheap.problem?.contains("capital") == true)

        var momentum = StrategyCustomization(strategy: template("cross-sectional-momentum-12-1").strategy)
        let skip = momentum.parameters.firstIndex { $0.key == .skipPeriodDays }!
        momentum.parameters[skip].value = 300
        #expect(momentum.problem?.contains("skipped") == true)

        var plan = StrategyCustomization(strategy: template("trend-following").strategy)
        plan.exitPlan = ExitPlan(stopPercent: 0)
        #expect(plan.problem != nil)
    }
}
