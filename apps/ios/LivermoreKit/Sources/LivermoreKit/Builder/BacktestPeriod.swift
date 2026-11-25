import Foundation

/// The stretch of history a test covers: a number of months, ending today
/// or at the end of an earlier month.
///
/// Jimmy, 2026-11-25, with the market falling hard: the three fixed choices
/// (3, 5 and 10 years) could not ask "how did this do over the last three
/// months?" or "through the 2022 fall?". Any length from three months up, a
/// month at a time, ending in any month of the last ten years.
public struct BacktestPeriod: Equatable, Hashable, Sendable {
    /// Three months is the shortest: under that a monthly strategy has
    /// rebalanced twice and the result says nothing.
    public static let lengthLimits = 3...120
    /// How many months back the period may end.
    public static let endLimits = 0...120

    /// Length in months.
    public var months: Int {
        didSet { months = min(max(months, Self.lengthLimits.lowerBound), Self.lengthLimits.upperBound) }
    }

    /// Months before the current one that the period ends in. 0 ends today;
    /// 1 ends on the last day of last month.
    public var endsMonthsAgo: Int {
        didSet { endsMonthsAgo = min(max(endsMonthsAgo, Self.endLimits.lowerBound), Self.endLimits.upperBound) }
    }

    public init(months: Int = 60, endsMonthsAgo: Int = 0) {
        self.months = min(max(months, Self.lengthLimits.lowerBound), Self.lengthLimits.upperBound)
        self.endsMonthsAgo = min(max(endsMonthsAgo, Self.endLimits.lowerBound), Self.endLimits.upperBound)
    }

    public static let threeMonths = BacktestPeriod(months: 3)
    public static let sixMonths = BacktestPeriod(months: 6)
    public static let oneYear = BacktestPeriod(months: 12)
    public static let threeYears = BacktestPeriod(months: 36)
    public static let fiveYears = BacktestPeriod(months: 60)
    public static let tenYears = BacktestPeriod(months: 120)

    /// The lengths offered as one tap; any other is reached a month at a time.
    public static let quickLengths: [(label: String, months: Int)] = [
        ("3M", 3), ("6M", 6), ("1Y", 12), ("3Y", 36), ("5Y", 60), ("10Y", 120),
    ]

    public var endsToday: Bool { endsMonthsAgo == 0 }
    public var canLengthen: Bool { months < Self.lengthLimits.upperBound }
    public var canShorten: Bool { months > Self.lengthLimits.lowerBound }
    /// Later means closer to today.
    public var canEndLater: Bool { endsMonthsAgo > Self.endLimits.lowerBound }
    public var canEndEarlier: Bool { endsMonthsAgo < Self.endLimits.upperBound }

    private static var utc: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar
    }

    /// The last day of the period: today, or the last day of an earlier month.
    public func end(today: Date = .now) -> Date {
        guard endsMonthsAgo > 0 else { return today }
        let calendar = Self.utc
        let thisMonth = calendar.date(from: calendar.dateComponents([.year, .month], from: today)) ?? today
        // The first of the month after the one it ends in, less a day.
        let after = calendar.date(byAdding: .month, value: 1 - endsMonthsAgo, to: thisMonth) ?? thisMonth
        return calendar.date(byAdding: .day, value: -1, to: after) ?? after
    }

    /// The first day: `months` before the last, on the same day of the month
    /// (or that month's last day, when it is shorter).
    public func start(today: Date = .now) -> Date {
        let end = end(today: today)
        return Self.utc.date(byAdding: .month, value: -months, to: end) ?? end
    }

    /// A date as the backend reads one.
    public static func isoDay(_ date: Date) -> String {
        let parts = utc.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
    }

    /// "3 months", "1 year", "1 year 2 months", "5 years".
    public var lengthText: String {
        let years = months / 12, rest = months % 12
        let yearPart = years == 0 ? nil : "\(years) year\(years == 1 ? "" : "s")"
        let monthPart = rest == 0 ? nil : "\(rest) month\(rest == 1 ? "" : "s")"
        return [yearPart, monthPart].compactMap { $0 }.joined(separator: " ")
    }
}

extension BacktestResult {
    /// The days the test actually covers: the first and last day there were
    /// prices for, which can sit inside the dates asked for (a weekend, a
    /// holiday, or today before the close), and how many sessions that is.
    public var tested: (first: String, last: String, sessions: Int)? {
        guard let first = equityCurve.first, let last = equityCurve.last else { return nil }
        return (String(first.date.prefix(10)), String(last.date.prefix(10)), equityCurve.count)
    }

    /// Under a year of daily returns. A per-year figure would then be the
    /// period's return compounded out to a year it did not cover: 9% over
    /// three months reads as 41% "a year".
    public var isUnderAYear: Bool { equityCurve.count - 1 < 252 }
}
