import Foundation
import LivermoreAPI

public typealias ExitTier = Components.Schemas.ExitTier

// MARK: - Risk level

/// The website's three risk presets (`lib/strategy-picker/risk-presets.ts`).
///
/// Of the three numbers a preset writes, the backtester acts on one: the
/// volatility target, which scales positions down when the strategy's recent
/// swings run above it. `max_drawdown_stop` and `stop_loss_pct` are stored on
/// the strategy — so one saved here reads the same on the website — but the
/// engine does not enforce them. A stop the backtest honours is an
/// ``ExitPlan``.
public enum RiskLevel: String, CaseIterable, Identifiable, Sendable {
    case low, medium, high

    public var id: String { rawValue }

    /// Annualised volatility the strategy is scaled towards, or nil for none.
    public var targetVolatility: Double? {
        switch self {
        case .low: 0.08
        case .medium: 0.12
        case .high: nil
        }
    }

    var maxDrawdownStop: Double {
        switch self {
        case .low: 0.15
        case .medium: 0.25
        case .high: 0.40
        }
    }

    var stopLoss: Double? {
        switch self {
        case .low: 0.08
        case .medium: 0.12
        case .high: nil
        }
    }

    /// The web's `applyRiskLevel`: additive, never removes what the strategy
    /// already carries.
    public func apply(to strategy: StrategyJSON) -> StrategyJSON {
        var next = strategy
        if let targetVolatility {
            next.positionSizing.method = .volTarget
            next.positionSizing.targetVolAnnual = targetVolatility
        }
        var risk = next.riskManagement ?? .init()
        risk.maxDrawdownStop = maxDrawdownStop
        if let stopLoss { risk.stopLossPct = stopLoss }
        next.riskManagement = risk
        return next
    }

    /// The web's `detectRiskPreset`, except that a strategy with no volatility
    /// target reports nil ("as the template has it") rather than `high`, so
    /// opening the customise screen and changing nothing changes nothing.
    public static func detect(in strategy: StrategyJSON) -> RiskLevel? {
        guard strategy.positionSizing.method == .volTarget,
              let target = strategy.positionSizing.targetVolAnnual
        else { return nil }
        if target <= 0.09 { return .low }
        if target <= 0.13 { return .medium }
        return .high
    }
}

// MARK: - Exit plan

/// A stop and up to two targets, as percentages from the entry price.
///
/// This is the strategy's `exit_ladder`. The backtester sells on these levels,
/// and a saved strategy that has one is tracked: Livermore watches the user's
/// positions against it and raises an action when a level is reached.
public struct ExitPlan: Equatable, Sendable {
    /// How far below entry the whole position is sold, as a positive
    /// percentage: 8 means "sell everything at −8%".
    public var stopPercent: Double
    /// Gain at which part of the position is sold, or nil for no partial exit.
    public var firstTargetPercent: Double?
    /// Share of the original position sold at the first target (0–1).
    public var firstTargetFraction: Double
    /// Gain at which the rest is sold, or nil to let the strategy's own
    /// rules close the position.
    public var finalTargetPercent: Double?

    public init(
        stopPercent: Double,
        firstTargetPercent: Double? = nil,
        firstTargetFraction: Double = 0.5,
        finalTargetPercent: Double? = nil
    ) {
        self.stopPercent = stopPercent
        self.firstTargetPercent = firstTargetPercent
        self.firstTargetFraction = firstTargetFraction
        self.finalTargetPercent = finalTargetPercent
    }

    /// A common shape: out at −8%, half off at +15%, the rest at +30%.
    public static let standard = ExitPlan(
        stopPercent: 8, firstTargetPercent: 15, firstTargetFraction: 0.5, finalTargetPercent: 30
    )

    /// Why the backend would refuse this plan, or nil when it is sound.
    public var problem: String? {
        if !(stopPercent > 0 && stopPercent < 100) { return "The stop must be between 0% and 100% below entry." }
        if let first = firstTargetPercent {
            if first <= 0 { return "The first target must be above entry." }
            if !(firstTargetFraction > 0 && firstTargetFraction < 1) {
                return "The first target must sell part of the position — to sell all of it, use the final target."
            }
            if let final = finalTargetPercent, final <= first {
                return "The final target must be higher than the first."
            }
        }
        if let final = finalTargetPercent, final <= 0 { return "The final target must be above entry." }
        return nil
    }

    /// Rounded in percent space before converting, as the web does, so −8%
    /// is exactly −0.08 and not a float with a tail.
    private static func fraction(_ percent: Double) -> Double {
        ((percent * 100).rounded() / 100 * 10_000).rounded() / 1_000_000
    }

    private static func percentLabel(_ percent: Double) -> String {
        percent == percent.rounded() ? String(Int(percent)) : String(format: "%.1f", percent)
    }

    /// The ladder the backend takes: ascending by trigger, the stop first.
    public var tiers: [ExitTier] {
        var tiers = [
            ExitTier(action: .sellAll, label: "Stop · −\(Self.percentLabel(stopPercent))%",
                     triggerPct: -Self.fraction(stopPercent)),
        ]
        if let first = firstTargetPercent {
            tiers.append(ExitTier(
                action: .sellFraction, fraction: firstTargetFraction,
                label: "Target 1 · +\(Self.percentLabel(first))%", triggerPct: Self.fraction(first)
            ))
        }
        if let final = finalTargetPercent {
            tiers.append(ExitTier(
                action: .sellAll,
                label: "Target \(firstTargetPercent == nil ? 1 : 2) · +\(Self.percentLabel(final))%",
                triggerPct: Self.fraction(final)
            ))
        }
        return tiers
    }

    /// Reads a ladder back into a plan. Ladders this screen can't represent
    /// (more than one partial exit, several stops) return nil, and the caller
    /// keeps the original ladder untouched.
    public init?(tiers: [ExitTier]) {
        let stops = tiers.filter { $0.triggerPct < 0 }
        let targets = tiers.filter { $0.triggerPct > 0 }
        guard stops.count == 1, stops[0].action == .sellAll, targets.count <= 2 else { return nil }
        let partials = targets.filter { $0.action == .sellFraction }
        let finals = targets.filter { $0.action == .sellAll }
        guard partials.count <= 1, finals.count <= 1 else { return nil }
        if let partial = partials.first, let final = finals.first, final.triggerPct <= partial.triggerPct {
            return nil
        }
        // 0.08 × 100 is 8.000000000000002 in floating point; a plan read back
        // from a ladder must equal the plan that wrote it.
        func percent(_ fraction: Double) -> Double { (fraction * 1_000_000).rounded() / 10_000 }
        self.init(
            stopPercent: percent(-stops[0].triggerPct),
            firstTargetPercent: partials.first.map { percent($0.triggerPct) },
            firstTargetFraction: partials.first?.fraction ?? 0.5,
            finalTargetPercent: finals.first.map { percent($0.triggerPct) }
        )
    }
}

// MARK: - Rule parameters

/// One number in a strategy's rule that a user can change: the breakout
/// window, how many names to hold, how many standard deviations.
public struct RuleParameter: Identifiable, Equatable, Sendable {
    public enum Key: String, CaseIterable, Sendable {
        case entryWindow, exitWindow, fastWindow, slowWindow
        case lookbackDays, rankingLookbackDays, formationPeriodDays, skipPeriodDays, holdingWindowDays
        case topN, topPct, numStd, zscoreEntry, zscoreExit, zscoreStop
    }

    public enum Unit: Equatable, Sendable {
        /// Trading days, whole numbers.
        case days
        /// A count of holdings, whole numbers.
        case count
        /// Stored as a fraction (0.2), shown as a percentage (20%).
        case percent
        /// A multiple such as standard deviations.
        case multiple
    }

    public let key: Key
    public let label: String
    public let unit: Unit
    public let range: ClosedRange<Double>
    public let step: Double
    public var value: Double

    public var id: String { key.rawValue }

    /// "20 days", "top 2", "20%", "2.0×".
    public var formatted: String {
        switch unit {
        case .days: "\(Int(value)) day\(Int(value) == 1 ? "" : "s")"
        case .count: "\(Int(value))"
        case .percent: "\(Int((value * 100).rounded()))%"
        case .multiple: String(format: "%.1f×", value)
        }
    }
}

extension RuleParameter.Key {
    var unit: RuleParameter.Unit {
        switch self {
        case .topN: .count
        case .topPct: .percent
        case .numStd, .zscoreEntry, .zscoreExit, .zscoreStop: .multiple
        default: .days
        }
    }

    var range: ClosedRange<Double> {
        switch self {
        case .topN: 1...20
        case .topPct: 0.05...1
        case .numStd: 0.5...4
        case .zscoreEntry, .zscoreStop: 0.5...5
        case .zscoreExit: 0...3
        case .skipPeriodDays: 0...63
        case .holdingWindowDays: 1...252
        default: 2...504
        }
    }

    var step: Double {
        switch self {
        case .topN: 1
        case .topPct: 0.05
        case .numStd, .zscoreEntry, .zscoreExit, .zscoreStop: 0.25
        case .skipPeriodDays, .holdingWindowDays: 1
        default: 1
        }
    }

    func read(_ rule: Components.Schemas.StrategyRule) -> Double? {
        switch self {
        case .entryWindow: rule.entryWindow.map(Double.init)
        case .exitWindow: rule.exitWindow.map(Double.init)
        case .fastWindow: rule.fastWindow.map(Double.init)
        case .slowWindow: rule.slowWindow.map(Double.init)
        case .lookbackDays: rule.lookbackDays.map(Double.init)
        case .rankingLookbackDays: rule.rankingLookbackDays.map(Double.init)
        case .formationPeriodDays: rule.formationPeriodDays.map(Double.init)
        case .skipPeriodDays: rule.skipPeriodDays.map(Double.init)
        case .holdingWindowDays: rule.holdingWindowDays.map(Double.init)
        case .topN: rule.topN.map(Double.init)
        case .topPct: rule.topPct
        case .numStd: rule.numStd
        case .zscoreEntry: rule.zscoreEntry
        case .zscoreExit: rule.zscoreExit
        case .zscoreStop: rule.zscoreStop
        }
    }

    func write(_ value: Double, to rule: inout Components.Schemas.StrategyRule) {
        let whole = Int(value.rounded())
        switch self {
        case .entryWindow: rule.entryWindow = whole
        case .exitWindow: rule.exitWindow = whole
        case .fastWindow: rule.fastWindow = whole
        case .slowWindow: rule.slowWindow = whole
        case .lookbackDays: rule.lookbackDays = whole
        case .rankingLookbackDays: rule.rankingLookbackDays = whole
        case .formationPeriodDays: rule.formationPeriodDays = whole
        case .skipPeriodDays: rule.skipPeriodDays = whole
        case .holdingWindowDays: rule.holdingWindowDays = whole
        case .topN: rule.topN = whole
        case .topPct: rule.topPct = (value * 100).rounded() / 100
        case .numStd: rule.numStd = value
        case .zscoreEntry: rule.zscoreEntry = value
        case .zscoreExit: rule.zscoreExit = value
        case .zscoreStop: rule.zscoreStop = value
        }
    }

    /// What the number means for this kind of strategy, in the words the
    /// template's own explanation uses.
    func label(for type: StrategyJSON.StrategyTypePayload) -> String {
        switch (type, self) {
        case (.breakout, .entryWindow): "Buy on a new high over"
        case (.breakout, .exitWindow): "Sell on a new low over"
        case (_, .entryWindow): "Entry window"
        case (_, .exitWindow): "Exit window"
        case (_, .fastWindow): "Fast average"
        case (_, .slowWindow): "Slow average"
        case (.bollingerMeanReversion, .lookbackDays): "Average price over"
        case (.lowVolatility, .lookbackDays): "Measure volatility over"
        case (.pairsTrading, .lookbackDays): "Measure the spread over"
        case (.timeSeriesMomentum, .lookbackDays): "Trend measured over"
        case (.movingAverageFilter, .lookbackDays): "Moving average length"
        case (.rsiMeanReversion, .lookbackDays): "RSI length"
        case (_, .lookbackDays): "Look back over"
        case (_, .rankingLookbackDays): "Rank by return over"
        case (.shortTermReversal, .formationPeriodDays): "Rank by loss over"
        case (_, .formationPeriodDays): "Rank by return over"
        case (_, .skipPeriodDays): "Skip the most recent"
        case (_, .holdingWindowDays): "Hold for"
        case (_, .topN): "Holdings at a time"
        case (.shortTermReversal, .topPct): "Buy the weakest"
        case (.lowVolatility, .topPct): "Buy the calmest"
        case (_, .topPct): "Buy the strongest"
        case (.bollingerMeanReversion, .numStd): "Band width (standard deviations)"
        case (_, .numStd): "Standard deviations"
        case (_, .zscoreEntry): "Enter when the spread stretches to"
        case (_, .zscoreExit): "Exit when it narrows to"
        case (_, .zscoreStop): "Give up if it widens to"
        }
    }
}

// MARK: - Customisation

/// Everything a user can change about a strategy before running it, beyond
/// the tickers and the period.
public struct StrategyCustomization: Equatable, Sendable {
    public var initialCapital: Double
    /// Commission and fees per trade, in basis points (10 = 0.10%).
    public var transactionCostBps: Double
    /// Price given up to the market on each trade, in basis points.
    public var slippageBps: Double
    public var parameters: [RuleParameter]
    /// nil leaves position sizing as the strategy has it.
    public var riskLevel: RiskLevel?
    /// nil means no exit plan — unless ``keepsOriginalLadder`` is set.
    public var exitPlan: ExitPlan?
    /// The strategy came with a ladder this screen can't represent; leave it
    /// exactly as it is unless the user sets a plan of their own.
    public private(set) var keepsOriginalLadder: Bool

    public static let capitalRange: ClosedRange<Double> = 1_000...100_000_000
    public static let costRange: ClosedRange<Double> = 0...100

    /// The settings a strategy already has.
    public init(strategy: StrategyJSON) {
        initialCapital = strategy.initialCapital
        transactionCostBps = strategy.transactionCostBps ?? 5
        slippageBps = strategy.slippageBps ?? 5
        riskLevel = RiskLevel.detect(in: strategy)
        if let rule = strategy.rules?.first {
            parameters = RuleParameter.Key.allCases.compactMap { key in
                guard let value = key.read(rule) else { return nil }
                return RuleParameter(
                    key: key, label: key.label(for: strategy.strategyType), unit: key.unit,
                    range: min(key.range.lowerBound, value)...max(key.range.upperBound, value),
                    step: key.step, value: value
                )
            }
        } else {
            parameters = []
        }
        if let ladder = strategy.riskManagement?.exitLadder, !ladder.isEmpty {
            exitPlan = ExitPlan(tiers: ladder)
            keepsOriginalLadder = exitPlan == nil
        } else {
            exitPlan = nil
            keepsOriginalLadder = false
        }
    }

    /// Turns the exit plan on (with the standard shape) or off.
    public mutating func setExitPlan(enabled: Bool) {
        keepsOriginalLadder = false
        exitPlan = enabled ? (exitPlan ?? .standard) : nil
    }

    /// Why this can't run, or nil when it can.
    public var problem: String? {
        if !Self.capitalRange.contains(initialCapital) { return "Starting capital must be at least $1,000." }
        if !Self.costRange.contains(transactionCostBps) || !Self.costRange.contains(slippageBps) {
            return "Trading costs must be between 0% and 1% per trade."
        }
        func value(_ key: RuleParameter.Key) -> Double? { parameters.first { $0.key == key }?.value }
        if let fast = value(.fastWindow), let slow = value(.slowWindow), fast >= slow {
            return "The fast average must be shorter than the slow one."
        }
        if let entry = value(.zscoreEntry) {
            if let exit = value(.zscoreExit), exit >= entry {
                return "The spread must narrow to exit: the exit level has to be below the entry level."
            }
            if let stop = value(.zscoreStop), stop <= entry {
                return "The give-up level has to be beyond the entry level."
            }
        }
        if let formation = value(.formationPeriodDays), let skip = value(.skipPeriodDays), skip >= formation {
            return "The skipped days must be fewer than the ranking period."
        }
        return exitPlan?.problem
    }

    /// The strategy with these settings written into it. Applying the
    /// settings a strategy already has returns it unchanged.
    public func apply(to strategy: StrategyJSON) -> StrategyJSON {
        var next = strategy
        next.initialCapital = initialCapital
        next.transactionCostBps = transactionCostBps
        next.slippageBps = slippageBps

        if var rules = next.rules, !rules.isEmpty {
            for parameter in parameters { parameter.key.write(parameter.value, to: &rules[0]) }
            next.rules = rules
        }

        if let riskLevel, riskLevel != RiskLevel.detect(in: strategy) {
            if riskLevel.targetVolatility == nil, next.positionSizing.method == .volTarget {
                // "High" means no volatility scaling; the web's helper only
                // ever adds, so undo a target a lower level put there.
                next.positionSizing.method = .equalWeight
                next.positionSizing.targetVolAnnual = nil
            }
            next = riskLevel.apply(to: next)
        }

        // The ladder is rewritten only when the plan differs from the one the
        // strategy came with. Rewriting an unchanged plan would still replace
        // its tier labels with this screen's wording, which is a change the
        // user did not make.
        let existing = strategy.riskManagement?.exitLadder ?? []
        let existingPlan = existing.isEmpty ? nil : ExitPlan(tiers: existing)
        let unrepresentable = !existing.isEmpty && existingPlan == nil
        if !keepsOriginalLadder, unrepresentable || exitPlan != existingPlan {
            var risk = next.riskManagement ?? .init()
            risk.exitLadder = exitPlan?.tiers
            next.riskManagement = risk
        }
        return next
    }

    /// How many settings differ from `strategy` — "3 changes".
    public func changeCount(from strategy: StrategyJSON) -> Int {
        let original = StrategyCustomization(strategy: strategy)
        var count = 0
        if initialCapital != original.initialCapital { count += 1 }
        if transactionCostBps != original.transactionCostBps || slippageBps != original.slippageBps { count += 1 }
        count += zip(parameters, original.parameters).filter { $0.value != $1.value }.count
        if riskLevel != original.riskLevel { count += 1 }
        if exitPlan != original.exitPlan || keepsOriginalLadder != original.keepsOriginalLadder { count += 1 }
        return count
    }
}
