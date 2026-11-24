import Foundation
import Testing

@testable import LivermoreKit

private let server = URL(string: "https://api.test")!

/// The company page's 1D and 1W charts (2026-11-24): prices through the
/// day, measured from the close before them, ending on the live price.
@MainActor
@Suite("1D and 1W charts")
struct IntradayChartTests {
    private let operation = "get_intraday_chart_api_data_intraday__symbol__get"

    private func iso(_ text: String) -> Date {
        ISO8601DateFormatter().date(from: text)!
    }

    /// Bars as the backend sends them: start times in UTC.
    private func bars(from start: String, count: Int, minutes: Int, price: Double) -> String {
        let first = iso(start)
        return (0..<count).map { i in
            let time = ISO8601DateFormatter().string(from: first.addingTimeInterval(Double(i * minutes * 60)))
            return #"{"time":"\#(time)","open":\#(price + Double(i)),"close":\#(price + Double(i) + 0.5)}"#
        }.joined(separator: ",")
    }

    private func chart(_ json: String, range: IntradayRange = .oneDay) async throws -> (IntradayChart, MockTransport) {
        let transport = MockTransport()
        let session = AppSession(serverURL: server, store: InMemorySessionStore(), transport: transport)
        transport.stub(operation, .json(status: 200, json))
        let chart = try await session.research.intraday("NVDA", range: range)
        return (chart, transport)
    }

    /// Tuesday 24 November 2026, three 5-minute bars from the 9:30 open
    /// (14:30 UTC), measured from Monday's $165.05.
    private func today(close: String = "null", previous: String = "165.05") -> String {
        """
        {"symbol":"NVDA","range":"1d","interval_minutes":5,"previous_close":\(previous),
         "previous_close_date":"2026-11-23","previous_close_source":"official","as_of":"2026-11-24T14:45:00Z",
         "sessions":[{"date":"2026-11-24","close":\(close),"bars":[\(bars(from: "2026-11-24T14:30:00Z", count: 3, minutes: 5, price: 159))]}]}
        """
    }

    private let duringTheSession = ISO8601DateFormatter().date(from: "2026-11-24T17:40:00Z")!  // 12:40 ET

    @Test("asks for the range by name and decodes the sessions")
    func decodes() async throws {
        let (chart, transport) = try await chart(today())
        #expect(transport.requests.first?.path == "/api/data/intraday/NVDA?range=1d")
        #expect(chart.sessions.first?.bars.count == 3)
        #expect(chart.previousClose == 165.05)
    }

    @Test("a day opens at 9:30 on the first open, plots each bar at its end, and is one full session wide")
    func dayLayout() async throws {
        let (chart, _) = try await chart(today())
        let series = IntradaySeries(chart: chart, range: .oneDay, now: duringTheSession)
        #expect(series.points.map(\.x) == [0, 1, 2, 3])
        #expect(series.points.map(\.price) == [159, 159.5, 160.5, 161.5])
        #expect(series.points.last?.time == iso("2026-11-24T14:45:00Z"))
        #expect(series.domain == 0...78)
        #expect(series.isToday)
        #expect(series.previousCloseDay == ISO8601DateFormatter().date(from: "2026-11-23T00:00:00Z"))
        #expect(series.change.map { ($0 * 10_000).rounded() } == ((161.5 / 165.05 - 1) * 10_000).rounded())
        // 10 AM is six 5-minute bars after the open.
        #expect(series.x(minutesAfterOpen: 30) == 6)
    }

    @Test("today's line ends on the live price, only in the session and only after the bars")
    func livePrice() async throws {
        let (chart, _) = try await chart(today())
        let live = IntradaySeries(chart: chart, range: .oneDay, livePrice: 153.56, liveAt: duringTheSession, now: duringTheSession)
        #expect(live.endsLive)
        #expect(live.points.last?.price == 153.56)
        #expect(live.points.last?.isLive == true)
        // 12:40 is 190 minutes after the open: 38 five-minute bars.
        #expect(live.points.last?.x == 38)

        let afterClose = iso("2026-11-24T21:30:00Z")
        #expect(!IntradaySeries(chart: chart, range: .oneDay, livePrice: 153, liveAt: afterClose, now: afterClose).endsLive)
        let olderThanTheBars = iso("2026-11-24T14:40:00Z")
        #expect(!IntradaySeries(chart: chart, range: .oneDay, livePrice: 153, liveAt: olderThanTheBars, now: duringTheSession).endsLive)
        // Wednesday morning the chart still shows Tuesday: no live end on it.
        let nextDay = iso("2026-11-25T15:00:00Z")
        let yesterday = IntradaySeries(chart: chart, range: .oneDay, livePrice: 153, liveAt: nextDay, now: nextDay)
        #expect(!yesterday.endsLive && !yesterday.isToday)
    }

    @Test("a finished day ends on the exchange's close, not its last bar")
    func officialClose() async throws {
        let (chart, _) = try await chart(today(close: "162.0"))
        let series = IntradaySeries(chart: chart, range: .oneDay, now: iso("2026-11-25T15:00:00Z"))
        #expect(series.points.last?.price == 162.0)
    }

    @Test("without the previous close the change is measured from the open")
    func fromTheOpen() async throws {
        let (chart, _) = try await chart(today(previous: "null"))
        let series = IntradaySeries(chart: chart, range: .oneDay, now: duringTheSession)
        #expect(series.measuredFromOpen)
        #expect(series.base == 159)
    }

    @Test("a week puts the days side by side, each a full session wide")
    func weekLayout() async throws {
        let json = """
        {"symbol":"NVDA","range":"1w","interval_minutes":30,"previous_close":150,"as_of":"2026-11-24T15:30:00Z",
         "sessions":[
          {"date":"2026-11-23","close":166.0,"bars":[\(bars(from: "2026-11-23T14:30:00Z", count: 13, minutes: 30, price: 160))]},
          {"date":"2026-11-24","close":null,"bars":[\(bars(from: "2026-11-24T14:30:00Z", count: 2, minutes: 30, price: 159))]}]}
        """
        let (chart, _) = try await chart(json, range: .oneWeek)
        let series = IntradaySeries(chart: chart, range: .oneWeek, now: duringTheSession)
        #expect(series.sessionStarts.map(\.x) == [0, 13])
        #expect(series.domain == 0...26)
        // Monday closes at 16:00 on its official close; Tuesday opens where
        // Monday ended on the axis, at its own open.
        let monday = series.points.filter { $0.x <= 13 }
        #expect(monday.last(where: { $0.x == 13 && $0.price == 166 }) != nil)
        #expect(series.points.contains { $0.x == 13 && $0.price == 159 })
        #expect(series.points.last?.x == 15)
        #expect(series.sessionCount == 2)
    }

    @Test("the regular session is 9:30 to 4 pm New York, weekdays")
    func regularSession() {
        #expect(!MarketHours.isRegularSession(at: iso("2026-11-24T14:29:00Z")))
        #expect(MarketHours.isRegularSession(at: iso("2026-11-24T14:30:00Z")))
        #expect(MarketHours.isRegularSession(at: iso("2026-11-24T20:59:00Z")))
        #expect(!MarketHours.isRegularSession(at: iso("2026-11-24T21:00:00Z")))
        #expect(!MarketHours.isRegularSession(at: iso("2026-11-28T16:00:00Z")))  // Saturday
        // Summer time: 9:30 is 13:30 UTC.
        #expect(MarketHours.isRegularSession(at: iso("2026-07-14T13:30:00Z")))
    }
}
