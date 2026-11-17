import Foundation

/// A strategy worth testing on a stock, and why this one, now.
public struct StrategySuggestion: Identifiable, Equatable, Sendable {
    public let template: StrategyTemplate
    /// One or two sentences tying the strategy's rule to the stock's setup.
    public let why: String
    /// What to set it up on. One ticker for single-stock strategies; the
    /// stock and its rivals for ones that rank a group.
    public let tickers: [String]

    public var id: String { template.id }
}

/// Matches a stock's setup to the strategies whose rules are about that
/// setup. It suggests what to *test* — the backtest, not this list, says
/// whether the rule has worked on the stock.
public enum StrategyAdvisor {
    public static func suggestions(
        for read: TechnicalRead?, symbol: String, peers: [String],
        catalog: [StrategyTemplate] = TemplateCatalog.runnable
    ) -> [StrategySuggestion] {
        let symbol = symbol.uppercased()
        func template(_ id: String) -> StrategyTemplate? { catalog.first { $0.id == id } }
        var result: [StrategySuggestion] = []

        func add(_ id: String, _ why: String, tickers: [String]? = nil) {
            guard let template = template(id) else { return }
            result.append(.init(template: template, why: why, tickers: tickers ?? [symbol]))
        }

        let trendRule = "It buys a new 20-day high and steps aside on a 10-day low."
        let reversionRule = "It buys a close below the lower Bollinger band and sells the return to the average."

        switch (read?.trend, read?.stretch) {
        case (.up?, .overbought?):
            add("trend-following", "\(symbol) is in an uptrend. \(trendRule) Test how it handled earlier run-ups that reversed.")
            add("bollinger-mean-reversion", "\(symbol) is stretched above its usual range. \(reversionRule) It would be waiting for a pullback.")
        case (.up?, _):
            add("trend-following", "\(symbol) is in an uptrend, which is when this rule is invested. \(trendRule)")
            add("bollinger-mean-reversion", "The opposite approach, for comparison. \(reversionRule)")
        case (.down?, .oversold?):
            add("bollinger-mean-reversion", "\(symbol) is in a downtrend and oversold — the setup this rule looks for. \(reversionRule)")
            add("trend-following", "A trend rule would most likely be in cash now. \(trendRule) Test how much of past declines it avoided.")
        case (.down?, _):
            add("trend-following", "\(symbol) is in a downtrend, so this rule would most likely be in cash. \(trendRule) Test how much of past declines it avoided.")
            add("bollinger-mean-reversion", "\(reversionRule) It buys sharp drops, so see how it fared in earlier declines before relying on it.")
        default:
            add("trend-following", "\(trendRule) With no clear trend it trades rarely; test what that has cost or saved.")
            add("bollinger-mean-reversion", "\(reversionRule) Range-bound stretches are where it has tended to do its work.")
        }

        // A ranking strategy needs a group; the company's rivals are one.
        if let ranking = template("cross-sectional-momentum") {
            var seen: Set<String> = [symbol]
            let rivals = peers.map { $0.uppercased() }.filter { seen.insert($0).inserted }
            if rivals.count >= ranking.minimumTickers - 1 {
                let group = [symbol] + rivals.prefix(4)
                result.append(.init(
                    template: ranking,
                    why: "Instead of asking whether to own \(symbol), ask which to own out of \(symbol) and \(group.count - 1) rivals: it holds the strongest and rotates.",
                    tickers: group
                ))
            }
        }
        return result
    }
}
