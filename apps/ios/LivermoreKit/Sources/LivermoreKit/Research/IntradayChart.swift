import Foundation
import LivermoreAPI

public typealias IntradayChart = Components.Schemas.IntradayChartView

/// The two chart ranges drawn from prices through the day rather than from
/// daily closes.
public enum IntradayRange: String, CaseIterable, Identifiable, Sendable {
    /// The latest session, every 5 minutes.
    case oneDay = "1D"
    /// The latest five sessions, every 30 minutes.
    case oneWeek = "1W"

    public var id: String { rawValue }

    /// As the backend takes it.
    var query: String {
        switch self {
        case .oneDay: "1d"
        case .oneWeek: "1w"
        }
    }

    /// How many sessions a full chart holds.
    public var sessions: Int {
        switch self {
        case .oneDay: 1
        case .oneWeek: 5
        }
    }
}

extension ResearchService {
    /// A stock's regular-session prices through the day: the latest session
    /// (1D) or the latest five (1W), with the close they are measured from.
    public func intraday(_ symbol: String, range: IntradayRange) async throws(ResearchError) -> IntradayChart {
        let output = try await APIFailure.perform {
            try await client.getIntradayChartApiDataIntradaySymbolGet(
                path: .init(symbol: symbol), query: .init(range: range.query)
            )
        }
        switch output {
        case .ok(let ok):
            guard case .json(let chart) = ok.body else { throw .server(status: 200) }
            return chart
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }
}

extension MarketHours {
    /// Monday to Friday, 9:30 to 16:00 New York time: when prices through
    /// the day are being made. Holidays count as open, as above.
    public static func isRegularSession(at date: Date) -> Bool {
        let calendar = IntradaySeries.newYork
        let parts = calendar.dateComponents([.weekday, .hour, .minute], from: date)
        guard let weekday = parts.weekday, let hour = parts.hour, let minute = parts.minute else { return false }
        let minutes = hour * 60 + minute
        return (2...6).contains(weekday) && (570..<960).contains(minutes)
    }
}

/// A day or a week of prices through the day, laid out for a chart.
///
/// The x axis is session time, not clock time. Each session is as wide as
/// 9:30 to 16:00 and the sessions sit side by side, so a week has no nights
/// or weekends in it and the jump from one close to the next open shows as
/// it happened. A session still under way keeps its full width, so the line
/// fills the day from the left as it goes.
///
/// While today's session is open the line ends on the live price, which is
/// newer than the newest bar.
public struct IntradaySeries: Equatable, Sendable {
    public struct Point: Equatable, Sendable, Identifiable {
        /// Position on the session-time axis, in bars.
        public let x: Double
        /// When the price was the price: a bar's end, or the live check.
        public let time: Date
        public let price: Double
        /// The live price, not a bar.
        public let isLive: Bool

        /// Unique where `x` is not: a session's open sits where the day
        /// before it closed.
        public var id: Date { time }
    }

    /// Where a session starts on the axis, for its label and divider.
    public struct SessionStart: Equatable, Sendable, Identifiable {
        public let x: Double
        /// The trading day, as midnight UTC like daily closes.
        public let day: Date
        public var id: Double { x }
    }

    public let range: IntradayRange
    public let points: [Point]
    public let sessionStarts: [SessionStart]
    /// Bars in one session's width.
    public let slotsPerSession: Double
    public let domain: ClosedRange<Double>
    public let intervalMinutes: Int
    /// The close of the session before the first one shown.
    public let previousClose: Double?
    /// The day of that close, as midnight UTC like daily closes.
    public let previousCloseDay: Date?
    /// That close is the day's last bar, because the exchange's close was
    /// not available.
    public let previousCloseIsApproximate: Bool
    /// The newest bar's end: how far the bars go.
    public let barsThrough: Date?
    /// The chart's latest session is today's.
    public let isToday: Bool
    /// The line ends on the live price.
    public let endsLive: Bool

    /// What the change is measured from: the previous close, or the first
    /// price shown when that close is unknown.
    public var base: Double? { previousClose ?? points.first?.price }
    public var measuredFromOpen: Bool { previousClose == nil }

    public var change: Double? {
        guard let base, base > 0, let last = points.last else { return nil }
        return last.price / base - 1
    }

    /// Sessions drawn.
    public var sessionCount: Int { sessionStarts.count }

    public static let newYork: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/New_York") ?? .gmt
        return calendar
    }()

    private static func day(_ text: String, in calendar: Calendar) -> Date? {
        let parts = text.prefix(10).split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3 else { return nil }
        return calendar.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2]))
    }

    /// - Parameters:
    ///   - livePrice: the live quote's price, and `liveAt` when it was
    ///     checked. Drawn only during today's session and after the newest
    ///     bar.
    public init(chart: IntradayChart, range: IntradayRange, livePrice: Double? = nil, liveAt: Date? = nil, now: Date = .now) {
        let interval = max(chart.intervalMinutes, 1)
        let slots = 390.0 / Double(interval)
        let newYork = Self.newYork
        let todayParts = newYork.dateComponents([.year, .month, .day], from: now)

        // The newest bar can still be in progress: FMP sends it, and its end
        // is in the future. It is drawn where its price was read (`asOf`),
        // and never later than now.
        let readUpTo = min(chart.asOf ?? now, now)

        var points: [Point] = []
        var starts: [SessionStart] = []
        var latestOpen: Date?
        var latestOrigin = 0.0
        var latestIsToday = false
        for (index, session) in chart.sessions.enumerated() {
            guard let midnight = Self.day(session.date, in: newYork),
                  let open = newYork.date(bySettingHour: 9, minute: 30, second: 0, of: midnight),
                  let first = session.bars.first,
                  let utcDay = Self.day(session.date, in: PerformanceSeries.utc)
            else { continue }
            let origin = Double(starts.count) * slots
            starts.append(SessionStart(x: origin, day: utcDay))
            // The session opens on its first bar's open.
            points.append(Point(x: origin, time: first.time, price: first.open, isLive: false))
            for (barIndex, bar) in session.bars.enumerated() {
                let end = max(bar.time, min(bar.time.addingTimeInterval(Double(interval) * 60), readUpTo))
                let x = origin + end.timeIntervalSince(open) / 60 / Double(interval)
                // A finished day ends on the exchange's close, not its last trade.
                let isLast = barIndex == session.bars.count - 1
                let price = isLast ? (session.close ?? bar.close) : bar.close
                points.append(Point(x: x, time: end, price: price, isLive: false))
            }
            latestOpen = open
            latestOrigin = origin
            let parts = newYork.dateComponents([.year, .month, .day], from: midnight)
            latestIsToday = index == chart.sessions.count - 1
                && parts.year == todayParts.year && parts.month == todayParts.month && parts.day == todayParts.day
        }

        let barsThrough = points.isEmpty ? nil : min(chart.asOf ?? readUpTo, readUpTo)
        var endsLive = false
        if latestIsToday, let livePrice, let liveAt, let latestOpen,
           MarketHours.isRegularSession(at: liveAt),
           newYork.isDate(liveAt, inSameDayAs: latestOpen),
           liveAt > (barsThrough ?? .distantPast) {
            let x = latestOrigin + liveAt.timeIntervalSince(latestOpen) / 60 / Double(interval)
            points.append(Point(x: min(x, latestOrigin + slots), time: liveAt, price: livePrice, isLive: true))
            endsLive = true
        }

        self.range = range
        self.points = points
        self.sessionStarts = starts
        self.slotsPerSession = slots
        // A day chart is always one full session wide; a week is as many
        // sessions as there are, up to five.
        self.domain = 0...(Double(max(starts.count, 1)) * slots)
        self.intervalMinutes = interval
        self.previousClose = chart.previousClose
        self.previousCloseDay = chart.previousCloseDate.flatMap { Self.day($0, in: PerformanceSeries.utc) }
        self.previousCloseIsApproximate = chart.previousCloseSource == "last_bar"
        self.barsThrough = barsThrough
        self.isToday = latestIsToday
        self.endsLive = endsLive
    }

    /// Position on the axis `minutes` after a session's open, for labels.
    public func x(session: Int = 0, minutesAfterOpen minutes: Double) -> Double {
        Double(session) * slotsPerSession + minutes / Double(intervalMinutes)
    }

    /// The point nearest `x`, for reading the chart by touch.
    public func point(nearest x: Double) -> Point? {
        points.min { abs($0.x - x) < abs($1.x - x) }
    }
}
