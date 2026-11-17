import Foundation

/// One thing the price is doing, stated plainly, and which way it leans.
public struct TechnicalSignal: Identifiable, Equatable, Sendable {
    public enum Lean: Equatable, Sendable { case up, down, neutral }

    public let id: String
    public let title: String
    /// A sentence a person can read without knowing the indicator.
    public let reading: String
    /// The number behind it, formatted: "−23.5%", "below", "18%".
    public let value: String
    public let lean: Lean
}

/// Where a stock's price stands: its trend, how stretched it is, and where it
/// sits in its range — computed from daily closes.
///
/// It describes; it does not recommend. "Downtrend, oversold" is a statement
/// about the last year of prices, and two reasonable people act on it in
/// opposite ways. That is why the app pairs it with strategies rather than a
/// verdict.
public struct TechnicalRead: Equatable, Sendable {
    public enum Trend: Equatable, Sendable { case up, down, mixed }
    public enum Stretch: Equatable, Sendable { case oversold, normal, overbought }

    public let asOf: Date
    public let price: Double
    /// Direction signals, in the order a reader would ask about them.
    public let signals: [TechnicalSignal]
    public let trend: Trend
    public let stretch: Stretch
    /// 14-day relative strength index, 0–100.
    public let rsi: Double?
    public let average50: Double?
    public let average200: Double?
    public let high52Week: Double
    public let low52Week: Double
    /// Annualised volatility over the last 20 trading days, as a fraction.
    public let volatility: Double?

    public var upCount: Int { signals.filter { $0.lean == .up }.count }
    public var downCount: Int { signals.filter { $0.lean == .down }.count }
    public var neutralCount: Int { signals.count - upCount - downCount }

    /// 0 at the 52-week low, 1 at the high.
    public var rangePosition: Double {
        high52Week > low52Week ? min(max((price - low52Week) / (high52Week - low52Week), 0), 1) : 0.5
    }

    /// How far below the 52-week high, as a negative fraction.
    public var fromHigh: Double { high52Week > 0 ? price / high52Week - 1 : 0 }

    /// "Downtrend, oversold" — the setup in two words.
    public var headline: String {
        let trendWord: String
        switch trend {
        case .up: trendWord = "Uptrend"
        case .down: trendWord = "Downtrend"
        case .mixed: trendWord = "No clear trend"
        }
        switch stretch {
        case .oversold: return "\(trendWord), oversold"
        case .overbought: return "\(trendWord), overbought"
        case .normal: return trendWord
        }
    }

    /// What that means, in a sentence, without telling anyone what to do.
    public var summary: String {
        let tally = "\(upCount) of \(signals.count) signals lean up, \(downCount) lean down."
        switch (trend, stretch) {
        case (.up, .overbought):
            return "\(tally) The trend is up, and the price has run far enough above its recent range that pullbacks are common from here."
        case (.up, _):
            return "\(tally) Price, averages and momentum agree: the trend is up."
        case (.down, .oversold):
            return "\(tally) The trend is down, and the fall has been sharp enough that rebounds are common from here — as are further drops."
        case (.down, _):
            return "\(tally) Price, averages and momentum agree: the trend is down."
        case (.mixed, .oversold):
            return "\(tally) The signals disagree, and the price is stretched to the downside."
        case (.mixed, .overbought):
            return "\(tally) The signals disagree, and the price is stretched to the upside."
        case (.mixed, .normal):
            return "\(tally) The signals disagree: there is no trend to follow or fade yet."
        }
    }

    // MARK: Building it

    static let tradingDaysPerYear = 252
    static let quarter = 63

    /// Needs at least 50 closes; signals that need more history are left out
    /// rather than estimated.
    public init?(closes: [DailyClose], benchmark: [DailyClose] = []) {
        let bars = closes.filter { $0.close > 0 }
        guard bars.count >= 50, let last = bars.last else { return nil }
        let prices = bars.map(\.close)
        let price = last.close
        asOf = last.date
        self.price = price

        // Prefix sums make every moving average an O(1) lookup.
        var prefix = [0.0]
        prefix.reserveCapacity(prices.count + 1)
        for value in prices { prefix.append(prefix[prefix.count - 1] + value) }
        func average(_ window: Int, endingAt end: Int) -> Double? {
            guard end + 1 >= window else { return nil }
            return (prefix[end + 1] - prefix[end + 1 - window]) / Double(window)
        }
        let lastIndex = prices.count - 1
        let ma50 = average(50, endingAt: lastIndex)
        let ma200 = average(200, endingAt: lastIndex)
        average50 = ma50
        average200 = ma200

        let yearWindow = prices.suffix(Self.tradingDaysPerYear)
        high52Week = yearWindow.max() ?? price
        low52Week = yearWindow.min() ?? price
        let position = high52Week > low52Week ? (price - low52Week) / (high52Week - low52Week) : 0.5

        var signals: [TechnicalSignal] = []

        func againstAverage(_ id: String, _ title: String, _ name: String, _ average: Double?) {
            guard let average, average > 0 else { return }
            let gap = price / average - 1
            let lean: TechnicalSignal.Lean = gap > 0.01 ? .up : gap < -0.01 ? .down : .neutral
            let where_ = lean == .neutral ? "right at" : "\(Self.percent(abs(gap))) \(gap > 0 ? "above" : "below")"
            signals.append(.init(
                id: id, title: title, reading: "The price is \(where_) its \(name) average.",
                value: Self.signedPercent(gap), lean: lean
            ))
        }
        againstAverage("trend200", "Long-term trend", "200-day", ma200)
        againstAverage("trend50", "Medium-term trend", "50-day", ma50)

        if let ma50, let ma200 {
            let above = ma50 > ma200
            // How long ago the two averages last crossed, if recently.
            var crossedAgo: Int?
            var back = 1
            while crossedAgo == nil, back <= 60,
                  let then50 = average(50, endingAt: lastIndex - back),
                  let then200 = average(200, endingAt: lastIndex - back) {
                if (then50 > then200) != above { crossedAgo = back }
                back += 1
            }
            let relation = "The 50-day average is \(above ? "above" : "below") the 200-day"
            // "Golden cross" and "death cross" name the crossing itself, so
            // the words are used only when it happened recently.
            let reading: String
            if let crossedAgo {
                reading = "\(relation): a \(above ? "golden" : "death") cross \(crossedAgo) trading day\(crossedAgo == 1 ? "" : "s") ago."
            } else if back > 60 {
                reading = "\(relation), and has been for at least three months."
            } else {
                reading = "\(relation)."
            }
            signals.append(.init(
                id: "cross", title: "50-day against 200-day",
                reading: reading, value: above ? "above" : "below", lean: above ? .up : .down
            ))
        }

        if prices.count > Self.quarter {
            let then = prices[lastIndex - Self.quarter]
            let change = price / then - 1
            let lean: TechnicalSignal.Lean = change > 0.05 ? .up : change < -0.05 ? .down : .neutral
            signals.append(.init(
                id: "momentum", title: "Three-month momentum",
                reading: "It is \(change >= 0 ? "up" : "down") \(Self.percent(abs(change))) over the last three months.",
                value: Self.signedPercent(change), lean: lean
            ))

            // Against the S&P 500 over the same days.
            let start = bars[lastIndex - Self.quarter].date
            let market = benchmark.filter { $0.close > 0 }
            if let base = market.last(where: { $0.date <= start }), let now = market.last(where: { $0.date <= last.date }),
               now.date > base.date {
                let excess = change - (now.close / base.close - 1)
                let lean: TechnicalSignal.Lean = excess > 0.03 ? .up : excess < -0.03 ? .down : .neutral
                signals.append(.init(
                    id: "relative", title: "Against the market",
                    reading: lean == .neutral
                        ? "It has moved in line with the S&P 500 over three months."
                        : "It has \(excess > 0 ? "beaten" : "lagged") the S&P 500 by \(String(format: "%.1f", abs(excess) * 100)) points over three months.",
                    value: Self.signedPercent(excess), lean: lean
                ))
            }
        }

        if bars.count >= 120 {
            let lean: TechnicalSignal.Lean = position >= 0.7 ? .up : position <= 0.3 ? .down : .neutral
            let place = position >= 0.7 ? "near the top" : position <= 0.3 ? "near the bottom" : "in the middle"
            signals.append(.init(
                id: "range", title: "52-week range",
                reading: "It is \(place) of its range for the past year, \(Self.percent(abs(price / high52Week - 1))) below the high.",
                value: "\(Int((position * 100).rounded()))%", lean: lean
            ))
        }
        self.signals = signals

        let net = signals.filter { $0.lean == .up }.count - signals.filter { $0.lean == .down }.count
        let needed = Int((Double(signals.count) / 2).rounded(.up))
        trend = signals.isEmpty ? .mixed : net >= needed ? .up : net <= -needed ? .down : .mixed

        let rsi = Self.rsi(prices, period: 14)
        self.rsi = rsi
        stretch = rsi.map { $0 < 30 ? .oversold : $0 > 70 ? .overbought : .normal } ?? .normal

        if prices.count > 20 {
            let recent = Array(prices.suffix(21))
            let returns = zip(recent.dropFirst(), recent).map { log($0 / $1) }
            let mean = returns.reduce(0, +) / Double(returns.count)
            let variance = returns.map { ($0 - mean) * ($0 - mean) }.reduce(0, +) / Double(returns.count - 1)
            volatility = sqrt(variance * Double(Self.tradingDaysPerYear))
        } else {
            volatility = nil
        }
    }

    /// Wilder's relative strength index.
    static func rsi(_ prices: [Double], period: Int) -> Double? {
        guard prices.count > period else { return nil }
        var gain = 0.0, loss = 0.0
        for index in 1...period {
            let change = prices[index] - prices[index - 1]
            if change > 0 { gain += change } else { loss -= change }
        }
        gain /= Double(period)
        loss /= Double(period)
        if prices.count > period + 1 {
            for index in (period + 1)..<prices.count {
                let change = prices[index] - prices[index - 1]
                gain = (gain * Double(period - 1) + max(change, 0)) / Double(period)
                loss = (loss * Double(period - 1) + max(-change, 0)) / Double(period)
            }
        }
        if loss == 0 { return gain == 0 ? 50 : 100 }
        return 100 - 100 / (1 + gain / loss)
    }

    private static func percent(_ fraction: Double) -> String {
        String(format: "%.1f%%", fraction * 100)
    }

    private static func signedPercent(_ fraction: Double) -> String {
        String(format: "%+.1f%%", fraction * 100)
    }
}
