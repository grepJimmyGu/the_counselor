import Foundation
import Testing

@testable import LivermoreKit

/// The options builder's numbers, end to end, on a real chain: REGN's
/// January 15, 2027 expiry at the close on 2026-11-23 (stock $942.24),
/// fetched through the backend's own chain service on 2026-11-24.
///
/// Jimmy, 2026-11-24: with the $950 call chosen, the chart said "If REGN is at
/// $995 on Jan 15, you lose $185", which read as wrong. It is right: the call
/// cost $46.85 a share and is worth $45 at $995. Every number a plan shows is
/// checked here against the textbook formula, for every strike of every
/// strategy, reached the way the strike slider reaches it.
@Suite("option math against a real chain")
struct OptionMathAuditTests {
    private func regn() throws -> OptionChain {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/option-chain-regn-2027-01-15.json")
        return try JSONDecoder().decode(OptionChain.self, from: Data(contentsOf: url))
    }

    /// Profit at expiry with the stock at `p`, straight from the definitions:
    /// strike `k`, premium `m` a share, stock price today `s`, `n` contracts.
    private func profit(_ strategy: OptionStrategy, k: Double, m: Double, s: Double, n: Double, at p: Double) -> Double {
        let shares = 100 * n
        switch strategy {
        case .longCall: return (max(p - k, 0) - m) * shares
        case .longPut: return (max(k - p, 0) - m) * shares
        case .coveredCall: return ((p - s) + m - max(p - k, 0)) * shares
        case .protectivePut: return ((p - s) + max(k - p, 0) - m) * shares
        }
    }

    private func maxLoss(_ strategy: OptionStrategy, k: Double, m: Double, s: Double, n: Double) -> Double {
        let shares = 100 * n
        switch strategy {
        case .longCall, .longPut: return m * shares
        case .coveredCall: return max(s - m, 0) * shares
        case .protectivePut: return max(s - k + m, 0) * shares
        }
    }

    /// Nil when there is no limit.
    private func maxGain(_ strategy: OptionStrategy, k: Double, m: Double, s: Double, n: Double) -> Double? {
        let shares = 100 * n
        switch strategy {
        case .longCall, .protectivePut: return nil
        case .longPut: return (k - m) * shares
        case .coveredCall: return (k - s + m) * shares
        }
    }

    /// The textbook breakeven, when the plan has one.
    private func breakeven(_ strategy: OptionStrategy, k: Double, m: Double, s: Double, n: Double) -> Double? {
        let candidate: Double
        switch strategy {
        case .longCall: candidate = k + m
        case .longPut: candidate = k - m
        case .coveredCall: candidate = s - m
        case .protectivePut: candidate = s + m
        }
        guard candidate > 0, abs(profit(strategy, k: k, m: m, s: s, n: n, at: candidate)) < 0.01 else { return nil }
        return candidate
    }

    @Test("the reported case: the $950 call at $995 loses $185, and says why")
    func reportedCase() throws {
        var draft = try #require(OptionPlanDraft(strategy: .longCall, chain: try regn()))
        draft.strikeIndex = try #require(draft.quotes.firstIndex { $0.strike == 950 })
        let plan = draft.plan
        #expect(plan.option.price == 46.85)
        #expect(plan.cashNow == 4_685)
        #expect(abs((plan.breakeven ?? 0) - 996.85) < 0.000_1)
        #expect(plan.payoff.profit(at: 995).rounded() == -185)
        #expect(plan.outcome(at: 995) == "If REGN is at $995.00 on Jan 15, the call is worth $4,500. You paid $4,685, so you lose $185.")
        #expect(plan.outcome(at: 1_000) == "If REGN is at $1,000.00 on Jan 15, the call is worth $5,000. You paid $4,685, so you make $315.")
        #expect(plan.outcome(at: 900) == "If REGN is at $900.00 on Jan 15, the call expires worthless. You paid $4,685, so you lose $4,685.")
    }

    @Test("the other strategies say what they come to, and why")
    func otherSentences() throws {
        let chain = try regn()
        // Worked by hand from the chain: the $940 put at $42.85, the $990 call
        // sold at $30.75, the $895 put at $24.90; REGN at $942.24.
        let put = try #require(OptionPlanDraft(strategy: .longPut, chain: chain)).plan
        #expect(put.outcome(at: 850) == "If REGN is at $850.00 on Jan 15, the put is worth $9,000. You paid $4,285, so you make $4,715.")
        #expect(put.outcome(at: 1_000) == "If REGN is at $1,000.00 on Jan 15, the put expires worthless. You paid $4,285, so you lose $4,285.")

        let covered = try #require(OptionPlanDraft(strategy: .coveredCall, chain: chain)).plan
        #expect(covered.outcome(at: 1_200) == "If REGN is at $1,200.00 on Jan 15, your shares are sold at $990, $4,776 above $942.24, and you keep the $3,075 you received, so you make $7,851.")
        #expect(covered.outcome(at: 900) == "If REGN is at $900.00 on Jan 15, the call expires worthless. Your shares are down $4,224 from $942.24 and you keep the $3,075 you received, so you lose $1,149.")

        let protective = try #require(OptionPlanDraft(strategy: .protectivePut, chain: chain)).plan
        #expect(protective.outcome(at: 700) == "If REGN is at $700.00 on Jan 15, the put lets you sell your shares at $895, $4,724 below $942.24. The put cost $2,490, so you lose $7,214.")
        #expect(protective.outcome(at: 1_000) == "If REGN is at $1,000.00 on Jan 15, the put expires worthless. Your shares are up $5,776 from $942.24 and the put cost $2,490, so you make $3,286.")
    }

    @Test("every strike of every strategy matches the formulas, as the slider reaches it")
    func everyStrike() throws {
        let chain = try regn()
        let s = chain.underlyingPrice
        var failures: [String] = []
        var checked = 0

        for strategy in [OptionStrategy.longCall, .longPut, .coveredCall, .protectivePut] {
            for contracts in [1, 3] {
                var draft = try #require(OptionPlanDraft(strategy: strategy, chain: chain, contracts: contracts))
                for index in draft.quotes.indices {
                    draft.strikeIndex = index
                    let quote = draft.quotes[index]
                    let plan = draft.plan
                    let k = quote.strike, m = quote.mid, n = Double(contracts)
                    let name = "\(strategy) \(OptionText.strike(k)) ×\(contracts)"
                    func fail(_ what: String) { failures.append("\(name): \(what)") }

                    // The slider moved to this strike's own contract and price.
                    if plan.strike != k || plan.option.price != m { fail("plan uses \(plan.strike) at \(plan.option.price)") }
                    if abs(plan.cashNow - m * 100 * n) > 0.001 { fail("cash now \(plan.cashNow)") }
                    if plan.paysNow == (strategy == .coveredCall) { fail("pays/receives backwards") }

                    let loss = maxLoss(strategy, k: k, m: m, s: s, n: n)
                    if abs((plan.maxLoss ?? .infinity) - loss) > 0.01 { fail("most you can lose \(String(describing: plan.maxLoss)) ≠ \(loss)") }
                    let gain = maxGain(strategy, k: k, m: m, s: s, n: n)
                    switch (plan.maxGain, gain) {
                    case (nil, nil): break
                    case let (got?, want?) where abs(got - want) <= 0.01: break
                    default: fail("most you can make \(String(describing: plan.maxGain)) ≠ \(String(describing: gain))")
                    }
                    let even = breakeven(strategy, k: k, m: m, s: s, n: n)
                    switch (plan.breakeven, even) {
                    case (nil, nil): break
                    case let (got?, want?) where abs(got - want) <= 0.001: break
                    default: fail("breakeven \(String(describing: plan.breakeven)) ≠ \(String(describing: even))")
                    }

                    // The figures the plan shows carry the same numbers.
                    let figures = Dictionary(uniqueKeysWithValues: plan.figures.map { ($0.label, $0.value) })
                    if figures["Most you can lose"] != OptionText.dollars(loss) { fail("figure \(figures["Most you can lose"] ?? "-")") }
                    if let even, figures["Breakeven"] != OptionText.price(even) { fail("figure breakeven \(figures["Breakeven"] ?? "-")") }

                    // Profit, the chart's line and the "what if" sentence, across prices.
                    var prices: [Double] = [0, k * 0.5, k - 5, k, k + 5, s, 995, 1_500]
                    if let even { prices += [even - 1, even + 1] }
                    for p in prices where p >= 0 {
                        let want = profit(strategy, k: k, m: m, s: s, n: n, at: p)
                        checked += 1
                        if abs(plan.payoff.profit(at: p) - want) > 0.01 { fail("profit at \(p) \(plan.payoff.profit(at: p)) ≠ \(want)") }
                        let sentence = plan.outcome(at: p)
                        let amount = want.rounded()
                        // The sentence's total may differ by $1 from the exact
                        // figure when a premium has a half cent: it adds up the
                        // whole-dollar parts it shows.
                        let candidates = [amount, amount - 1, amount + 1]
                        let says = candidates.contains { value in
                            value == 0 ? sentence.hasSuffix("you break even.")
                                : sentence.hasSuffix("you \(value > 0 ? "make" : "lose") \(OptionText.dollars(abs(value))).")
                        }
                        if !says { fail("at \(p) wants \(amount): \(sentence)") }
                    }
                    let range = plan.chartRange(including: chain.impliedRange)
                    for point in plan.payoff.curve(from: range.lowerBound, to: range.upperBound) {
                        let want = profit(strategy, k: k, m: m, s: s, n: n, at: point.price)
                        if abs(point.profit - want) > 0.01 { fail("chart at \(point.price)") }
                    }
                    if !range.contains(k) || !range.contains(s) { fail("chart range \(range) misses the strike or the price") }
                    if let even, !range.contains(even) { fail("chart range misses the breakeven") }
                }
            }
        }
        #expect(checked > 5_000)
        #expect(failures.isEmpty, "\(failures.count) failures, first: \(failures.prefix(8).joined(separator: " | "))")
    }
}
