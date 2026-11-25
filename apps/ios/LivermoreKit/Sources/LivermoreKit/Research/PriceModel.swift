import Foundation

// MARK: - Trend model

/// A straight line through the logarithm of the price over a window: how
/// fast the price has been moving, how well a line describes it, and how
/// far today's price is from that line.
///
/// It measures the past window. It is not a projection.
public struct TrendModel: Equatable, Sendable {
    public struct Point: Equatable, Sendable, Identifiable {
        public let date: Date
        public let middle: Double
        public let upper: Double
        public let lower: Double
        public var id: Date { date }
    }

    /// Trading days in the fit.
    public let window: Int
    /// The line's slope as a yearly rate of change: −0.45 is "falling 45% a year".
    public let annualRate: Double
    /// Share of the price's movement the line accounts for, 0–1.
    public let rSquared: Double
    /// How many standard deviations today's price is from the line.
    public let deviations: Double
    /// The line and a band two standard deviations either side.
    public let points: [Point]

    public static let bandWidth = 2.0

    public init?(closes: [DailyClose], window: Int) {
        let bars = Array(closes.filter { $0.close > 0 }.suffix(window))
        guard bars.count >= 20, bars.count == window || closes.count < window else { return nil }
        let n = Double(bars.count)
        let ys = bars.map { log($0.close) }
        let meanX = (n - 1) / 2
        let meanY = ys.reduce(0, +) / n
        var sxx = 0.0, sxy = 0.0, syy = 0.0
        for (index, y) in ys.enumerated() {
            let dx = Double(index) - meanX
            sxx += dx * dx
            sxy += dx * (y - meanY)
            syy += (y - meanY) * (y - meanY)
        }
        guard sxx > 0 else { return nil }
        let slope = sxy / sxx
        let intercept = meanY - slope * meanX
        var residual = 0.0
        for (index, y) in ys.enumerated() {
            let error = y - (intercept + slope * Double(index))
            residual += error * error
        }
        let sigma = sqrt(residual / max(n - 2, 1))

        self.window = bars.count
        annualRate = exp(slope * 252) - 1
        rSquared = syy > 0 ? max(0, 1 - residual / syy) : 0
        let lastFit = intercept + slope * (n - 1)
        // A perfectly straight series leaves only rounding error as its
        // scatter; dividing by that would report noise as a deviation.
        deviations = sigma > 1e-9 ? (ys[ys.count - 1] - lastFit) / sigma : 0
        points = bars.enumerated().map { index, bar in
            let fit = intercept + slope * Double(index)
            return Point(
                date: bar.date, middle: exp(fit),
                upper: exp(fit + Self.bandWidth * sigma), lower: exp(fit - Self.bandWidth * sigma)
            )
        }
    }

    /// What the fit says, in three plain facts.
    public var summary: String {
        let direction = annualRate >= 0 ? "risen" : "fallen"
        // One decimal for small rates, so the sentence agrees with the tile
        // beside it ("-2.5%" must not read as "2%").
        let rate = String(format: abs(annualRate) < 0.10 ? "%.1f%%" : "%.0f%%", abs(annualRate) * 100)
        let fit = String(format: "%.0f%%", rSquared * 100)
        let position: String
        if abs(deviations) < 0.25 {
            position = "Today's price is on that line."
        } else {
            position = String(format: "Today's price is %.1f standard deviations %@ that line.",
                              abs(deviations), deviations > 0 ? "above" : "below")
        }
        let quality = rSquared >= 0.6 ? "a steady move" : rSquared >= 0.3 ? "a move with wide swings around it" : "mostly swings, with little steady direction"
        return "Over the last \(window) trading days the price has \(direction) at a rate of \(rate) a year. "
            + "A straight line accounts for \(fit) of the movement: \(quality). \(position)"
    }
}

// MARK: - Levels

/// A price that has mattered: an average, the edge of a range, a recent turn.
public struct PriceLevel: Equatable, Sendable, Identifiable {
    public let name: String
    public let price: Double
    /// Where it sits against the current price, as a fraction.
    public let distance: Double

    public var id: String { name }
    public var isAbove: Bool { distance > 0 }
}

public struct PriceLevels: Equatable, Sendable {
    public let price: Double
    /// Average true range over 14 days: a typical day's travel, in dollars.
    public let averageRange: Double
    /// Levels above and below the price, highest first.
    public let levels: [PriceLevel]

    /// A typical day's travel as a share of the price.
    public var averageRangeShare: Double { price > 0 ? averageRange / price : 0 }
    public var nearestAbove: PriceLevel? { levels.last { $0.isAbove } }
    public var nearestBelow: PriceLevel? { levels.first { !$0.isAbove } }

    /// `price` is the live price when there is one; without it the levels are
    /// measured from the last close.
    public init?(closes: [DailyClose], price livePrice: Double? = nil) {
        let bars = closes.filter { $0.close > 0 }
        guard bars.count >= 30, let last = bars.last else { return nil }
        let anchor = livePrice.flatMap { $0 > 0 ? $0 : nil } ?? last.close
        price = anchor

        // True range: the day's span, or the gap from yesterday's close if wider.
        let recent = Array(bars.suffix(15))
        let ranges = zip(recent.dropFirst(), recent).map { today, yesterday in
            max(today.high - today.low, abs(today.high - yesterday.close), abs(today.low - yesterday.close))
        }
        averageRange = ranges.reduce(0, +) / Double(ranges.count)

        var found: [(String, Double)] = []
        func average(_ days: Int) -> Double? {
            bars.count >= days ? bars.suffix(days).map(\.close).reduce(0, +) / Double(days) : nil
        }
        if let value = average(200) { found.append(("200-day average", value)) }
        if let value = average(50) { found.append(("50-day average", value)) }
        let year = bars.suffix(252)
        if let high = year.map(\.high).max() { found.append(("52-week high", high)) }
        if let low = year.map(\.low).min() { found.append(("52-week low", low)) }
        // Excluding today, so "the 20-day high" is a level the price can break.
        let month = bars.dropLast().suffix(20)
        if let high = month.map(\.high).max() { found.append(("20-day high", high)) }
        if let low = month.map(\.low).min() { found.append(("20-day low", low)) }

        // The most recent turning points: a day whose high (or low) was not
        // exceeded for five days either side.
        let span = Array(bars.suffix(90))
        var swingHigh: Double?, swingLow: Double?
        if span.count > 11 {
            for index in stride(from: span.count - 6, through: 5, by: -1) {
                let neighbours = span[(index - 5)...(index + 5)]
                if swingHigh == nil, span[index].high == neighbours.map(\.high).max(), span[index].high > anchor {
                    swingHigh = span[index].high
                }
                if swingLow == nil, span[index].low == neighbours.map(\.low).min(), span[index].low < anchor {
                    swingLow = span[index].low
                }
                if swingHigh != nil, swingLow != nil { break }
            }
        }
        if let swingHigh { found.append(("Last swing high", swingHigh)) }
        if let swingLow { found.append(("Last swing low", swingLow)) }

        // Two names for one price (the 20-day low is often the 52-week low)
        // are one level.
        var kept: [PriceLevel] = []
        for (name, value) in found.sorted(by: { $0.1 > $1.1 }) {
            if let previous = kept.last, abs(previous.price / value - 1) < 0.002 {
                kept[kept.count - 1] = PriceLevel(
                    name: "\(previous.name) · \(name)", price: previous.price, distance: previous.distance
                )
            } else {
                kept.append(PriceLevel(name: name, price: value, distance: value / anchor - 1))
            }
        }
        levels = kept
    }
}

// MARK: - Entry / exit test

/// An entry, a stop and a target, to be tried against history.
public struct BracketPlan: Equatable, Sendable {
    /// How far below the day's close to bid, as a fraction. 0 buys at the close.
    public var entryDiscount: Double
    /// Stop, as a fraction below the entry price.
    public var stop: Double
    /// Target, as a fraction above the entry price.
    public var target: Double
    /// Trading days to wait for the stop or the target before giving up.
    public var maxDays: Int
    /// Trading days a bid below the close is left open.
    public var fillDays: Int

    public init(entryDiscount: Double = 0, stop: Double, target: Double, maxDays: Int = 60, fillDays: Int = 10) {
        self.entryDiscount = entryDiscount
        self.stop = stop
        self.target = target
        self.maxDays = maxDays
        self.fillDays = fillDays
    }

    /// The share of trades that must reach the target for the plan to break
    /// even, ignoring the ones that time out: arithmetic on the two distances.
    public var breakevenWinRate: Double { stop + target > 0 ? stop / (stop + target) : 0 }

    // MARK: Moving a price
    //
    // The plan keeps distances (below the close, below the entry, above the
    // entry), but the screen shows prices, and + must raise the price shown
    // whichever way its distance runs. Jimmy, 2026-11-24: + on "Buy at" and
    // "Stop" lowered the price, because it added to the distance below.

    public static let entryDiscountLimits = 0.0...0.20
    public static let stopLimits = 0.005...0.40
    public static let targetLimits = 0.01...1.00

    /// The buy price up or down by 1% of the reference price; never above it.
    public mutating func moveEntry(up: Bool) {
        entryDiscount = Self.stepped(entryDiscount + (up ? -0.01 : 0.01), per: 100, within: Self.entryDiscountLimits)
    }

    /// The stop up (closer to the entry) or down by half a percent.
    public mutating func moveStop(up: Bool) {
        stop = Self.stepped(stop + (up ? -0.005 : 0.005), per: 200, within: Self.stopLimits)
    }

    /// The target up (further from the entry) or down by 1%.
    public mutating func moveTarget(up: Bool) {
        target = Self.stepped(target + (up ? 0.01 : -0.01), per: 100, within: Self.targetLimits)
    }

    /// Whether each price can move further that way, so a button at its
    /// limit can be switched off rather than do nothing.
    public func canMoveEntry(up: Bool) -> Bool {
        up ? entryDiscount > Self.entryDiscountLimits.lowerBound + 1e-9 : entryDiscount < Self.entryDiscountLimits.upperBound - 1e-9
    }

    public func canMoveStop(up: Bool) -> Bool {
        up ? stop > Self.stopLimits.lowerBound + 1e-9 : stop < Self.stopLimits.upperBound - 1e-9
    }

    public func canMoveTarget(up: Bool) -> Bool {
        up ? target < Self.targetLimits.upperBound - 1e-9 : target > Self.targetLimits.lowerBound + 1e-9
    }

    /// Rounded to whole steps (`per` steps to 1) and kept within `limits`.
    private static func stepped(_ value: Double, per: Double, within limits: ClosedRange<Double>) -> Double {
        min(max((value * per).rounded() / per, limits.lowerBound), limits.upperBound)
    }

    /// A starting plan sized to how much the stock moves: a stop two typical
    /// days away, a target twice as far.
    public static func sized(to levels: PriceLevels?) -> BracketPlan {
        let range = levels?.averageRangeShare ?? 0.02
        let stop = min(max((range * 2 * 200).rounded() / 200, 0.02), 0.25)
        return BracketPlan(stop: stop, target: min(stop * 2, 0.60))
    }
}

/// What happened when a plan was tried on every past day.
public struct BracketResult: Equatable, Sendable {
    /// Days on which the plan was tried.
    public let tried: Int
    /// Tries on which the entry price was reached.
    public let entered: Int
    public let reachedTarget: Int
    public let stopped: Int
    public let timedOut: Int
    /// Mean return per entered trade, as a fraction.
    public let averageReturn: Double
    /// Median trading days from entry to exit.
    public let medianDays: Int
    public let from: Date?
    public let to: Date?

    public var fillRate: Double { tried > 0 ? Double(entered) / Double(tried) : 0 }
    public var targetRate: Double { entered > 0 ? Double(reachedTarget) / Double(entered) : 0 }
    public var stopRate: Double { entered > 0 ? Double(stopped) / Double(entered) : 0 }
    public var timeoutRate: Double { entered > 0 ? Double(timedOut) / Double(entered) : 0 }
}

/// The tries whose waiting period has not finished: the days so near the end
/// of the prices that the stop, the target or the time limit may still be
/// ahead. They are kept out of the main counts, where a trade that simply
/// has not had its time yet would read as "reached neither".
public struct BracketRecent: Equatable, Sendable {
    /// Days tried: every one of them whose bid, if it had one, has either
    /// filled or run out of time to.
    public let tried: Int
    public let entered: Int
    public let reachedTarget: Int
    public let stopped: Int
    /// Entered, with the time limit up and neither level reached.
    public let timedOut: Int
    /// Entered, and neither level reached by the last price.
    public let stillOpen: Int
    /// Mean return of the still-open trades, valued at the last price.
    public let openAverageReturn: Double
    public let from: Date?
    public let to: Date?
}

/// Tries an entry / stop / target plan on each day of a period.
///
/// A count of what happened, not a forecast of what will. Three things make
/// it conservative rather than flattering: a day that touches both the stop
/// and the target is counted as stopped; a bid below the close fills at the
/// bid, never better; and the main counts take only days with the full
/// waiting period after them, so no trade is cut short by the end of the
/// data. The days after that are counted on their own (`recent`).
///
/// The tries overlap — each day starts one — so they are not independent
/// trades, and the counts say how often, not how reliably.
public enum BracketTest {
    public struct Outcome: Equatable, Sendable {
        public let all: BracketResult
        /// The same test on days that resembled today, with what "resembled"
        /// meant. Nil when there are too few such days to count.
        public let similar: BracketResult?
        public let similarity: String?
        /// The days in the period whose waiting time is still running. Nil
        /// when there are none: a period that ended long enough ago.
        public let recent: BracketRecent?
    }

    /// The longest period there are prices for (`PriceHistory.yearsKept` is one more).
    public static let years = 5
    static let minimumSimilar = 60

    /// Tries `plan` on every day of `period`. The period is measured from
    /// `today`, or from the last day of prices when that is not given.
    public static func run(
        closes: [DailyClose], plan: BracketPlan, period: BacktestPeriod = .fiveYears, today: Date? = nil
    ) -> Outcome? {
        let bars = closes.filter { $0.close > 0 }
        guard bars.count > plan.maxDays + plan.fillDays + 60, plan.stop > 0, plan.target > 0, let last = bars.last else { return nil }
        let anchor = today ?? last.date
        let periodStart = period.start(today: anchor), periodEnd = period.end(today: anchor)
        guard let firstStart = bars.firstIndex(where: { $0.date >= periodStart }),
              let lastInPeriod = bars.lastIndex(where: { $0.date <= periodEnd }), lastInPeriod >= firstStart
        else { return nil }
        // The last day with the whole wait (to fill, then to finish) after it.
        let lastComplete = min(lastInPeriod, bars.count - 1 - plan.maxDays - plan.fillDays)

        // Which side of its 200-day average the price was on, each day.
        var prefix = [0.0]
        for bar in bars { prefix.append(prefix[prefix.count - 1] + bar.close) }
        func aboveAverage(_ index: Int) -> Bool? {
            guard index >= 199 else { return nil }
            return bars[index].close > (prefix[index + 1] - prefix[index - 199]) / 200
        }
        let todayAbove = aboveAverage(bars.count - 1)

        var everyDay = Tally(), similarDays = Tally()
        if lastComplete >= firstStart {
            for start in firstStart...lastComplete {
                let trade = simulate(bars, from: start, plan: plan)
                everyDay.add(trade, date: bars[start].date)
                if let todayAbove, aboveAverage(start) == todayAbove {
                    similarDays.add(trade, date: bars[start].date)
                }
            }
        }
        var unfinished = Tally()
        let firstUnfinished = max(firstStart, lastComplete + 1)
        if firstUnfinished <= lastInPeriod {
            for start in firstUnfinished...lastInPeriod {
                unfinished.add(simulate(bars, from: start, plan: plan), date: bars[start].date)
            }
        }
        let similar = similarDays.tried >= minimumSimilar && todayAbove != nil ? similarDays.result : nil
        return Outcome(
            all: everyDay.result, similar: similar,
            similarity: similar == nil ? nil
                : "days when the price was \(todayAbove == true ? "above" : "below") its 200-day average, as it is now",
            recent: unfinished.tried > 0 ? unfinished.recent : nil
        )
    }

    private enum Trade {
        case unfilled
        /// A bid that has not filled and still has days left to.
        case pending
        case closed(fraction: Double, days: Int, kind: Kind)
        /// Entered, with neither level reached and the time limit not yet up.
        case open(fraction: Double)
        enum Kind { case target, stop, timeout }
    }

    private static func simulate(_ bars: [DailyClose], from start: Int, plan: BracketPlan) -> Trade {
        let lastBar = bars.count - 1
        var entryIndex = start
        var entryPrice = bars[start].close
        if plan.entryDiscount > 0 {
            let bid = bars[start].close * (1 - plan.entryDiscount)
            let lastFillDay = min(start + plan.fillDays, lastBar)
            guard start < lastFillDay,
                  let filled = ((start + 1)...lastFillDay).first(where: { bars[$0].low <= bid })
            else { return start + plan.fillDays <= lastBar ? .unfilled : .pending }
            entryIndex = filled
            entryPrice = bid
        }
        let stopPrice = entryPrice * (1 - plan.stop)
        let targetPrice = entryPrice * (1 + plan.target)
        let timeLimit = entryIndex + plan.maxDays
        let end = min(timeLimit, lastBar)
        if end > entryIndex {
            for index in (entryIndex + 1)...end {
                if bars[index].low <= stopPrice { return .closed(fraction: -plan.stop, days: index - entryIndex, kind: .stop) }
                if bars[index].high >= targetPrice { return .closed(fraction: plan.target, days: index - entryIndex, kind: .target) }
            }
        }
        // The prices ran out before the time limit: the trade is still on.
        guard timeLimit <= lastBar else { return .open(fraction: bars[lastBar].close / entryPrice - 1) }
        return .closed(fraction: bars[end].close / entryPrice - 1, days: end - entryIndex, kind: .timeout)
    }

    private struct Tally {
        var tried = 0, entered = 0, target = 0, stop = 0, timeout = 0, open = 0
        var total = 0.0, openTotal = 0.0
        var days: [Int] = []
        var from: Date?, to: Date?

        mutating func add(_ trade: Trade, date: Date) {
            // A bid still waiting to fill has not been tried yet.
            if case .pending = trade { return }
            tried += 1
            if from == nil { from = date }
            to = date
            switch trade {
            case .unfilled, .pending:
                return
            case .open(let fraction):
                entered += 1
                open += 1
                openTotal += fraction
            case .closed(let fraction, let held, let kind):
                entered += 1
                total += fraction
                days.append(held)
                switch kind {
                case .target: target += 1
                case .stop: stop += 1
                case .timeout: timeout += 1
                }
            }
        }

        var result: BracketResult {
            BracketResult(
                tried: tried, entered: entered, reachedTarget: target, stopped: stop, timedOut: timeout,
                averageReturn: entered > 0 ? total / Double(entered) : 0,
                medianDays: days.isEmpty ? 0 : days.sorted()[days.count / 2],
                from: from, to: to
            )
        }

        var recent: BracketRecent {
            BracketRecent(
                tried: tried, entered: entered, reachedTarget: target, stopped: stop, timedOut: timeout, stillOpen: open,
                openAverageReturn: open > 0 ? openTotal / Double(open) : 0, from: from, to: to
            )
        }
    }
}
