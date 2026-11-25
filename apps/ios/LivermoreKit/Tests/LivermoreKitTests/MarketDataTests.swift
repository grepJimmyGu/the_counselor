import Foundation
import Testing

@testable import LivermoreKit

private let server = URL(string: "https://api.test")!

@MainActor
@Suite("market data for the research screens")
struct MarketDataTests {
    private func make() -> (ResearchService, MockTransport) {
        let transport = MockTransport()
        let session = AppSession(serverURL: server, store: InMemorySessionStore(), transport: transport)
        return (session.research, transport)
    }

    private func day(_ text: String) -> Date {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.date(from: text)!
    }

    private func closes(_ rows: [(String, Double)]) -> [DailyClose] {
        rows.map { DailyClose(date: day($0.0), close: $0.1) }
    }

    @Test("daily closes decode oldest first, on the adjusted close")
    func dailyCloses() async throws {
        let (service, transport) = make()
        transport.stub("get_daily_prices_api_data_daily__symbol__get", .json(status: 200, """
        [{"symbol":"NVDA","trading_date":"2026-11-16","open":159.0,"high":163.2,"low":155.0,"close":156.14,"adjusted_close":156.14,"volume":1,"dividend_amount":0,"split_coefficient":1},
         {"symbol":"NVDA","trading_date":"1999-11-01","open":21.75,"high":24.38,"low":21.75,"close":23.5,"adjusted_close":0.0449,"volume":1,"dividend_amount":0,"split_coefficient":1}]
        """))
        let rows = try await service.dailyCloses("NVDA")
        #expect(rows.map(\.close) == [0.0449, 156.14])
        #expect(rows.last?.date == day("2026-11-16"))
    }

    // A stock listed since 1999 has 27 years of daily bars: 1.2 MB of JSON
    // per company page, twice with the benchmark, for charts that read five.
    @Test("a history is asked for six years back, not from the listing day")
    func dailyClosesAreBounded() async throws {
        let (service, transport) = make()
        transport.stub("get_daily_prices_api_data_daily__symbol__get", .json(status: 200, "[]"))
        _ = try await service.dailyCloses("NVDA", now: day("2026-11-20"))
        #expect(transport.requests.last?.path == "/api/data/daily/NVDA?start=2020-11-20")
        #expect(PriceHistory.yearsKept > BracketTest.years)
    }

    @Test("something looked at a moment ago is kept, then let go")
    func recentValues() {
        var clock = Date(timeIntervalSince1970: 1_800_000_000)
        let recent = RecentValues<String>(lifetime: 300, capacity: 2, now: { clock })
        #expect(recent.value(for: "NVDA") == nil)

        recent.store("nvidia", for: "nvda")
        clock.addTimeInterval(299)
        #expect(recent.value(for: "NVDA") == "nvidia")
        clock.addTimeInterval(2)
        #expect(recent.value(for: "NVDA") == nil)

        // Only the most recently stored are kept.
        recent.store("a", for: "A")
        recent.store("b", for: "B")
        recent.store("c", for: "C")
        #expect(recent.value(for: "A") == nil)
        #expect(recent.value(for: "B") == "b" && recent.value(for: "C") == "c")

        recent.removeAll()
        #expect(recent.value(for: "C") == nil)
    }

    @Test("what was looked at under one sign-in is not shown under another")
    func recentResearchIsPerSignIn() async throws {
        let transport = MockTransport()
        let session = AppSession(serverURL: server, store: InMemorySessionStore(), transport: transport)
        transport.stub("get_company_trend_api_company__symbol__trend_get", .json(status: 200, "{}"))
        let trend = try await session.research.trend("NVDA")
        session.recentTrends.store(trend, for: "NVDA")
        #expect(session.recentTrends.value(for: "nvda") != nil)
        session.signOut()
        #expect(session.recentTrends.value(for: "NVDA") == nil)
    }

    @Test("a period's return and the benchmark's cover exactly the same days")
    func performance() {
        let stock = closes([("2026-08-14", 90), ("2026-10-16", 100), ("2026-10-30", 110), ("2026-11-16", 125)])
        // The benchmark has no bar on 10-30 (as if a holiday); the day
        // before carries.
        let spy = closes([("2026-08-14", 380), ("2026-10-16", 400), ("2026-10-29", 410), ("2026-11-16", 420)])

        let month = PerformanceSeries(stock: stock, benchmark: spy, range: .oneMonth)
        #expect(month.points.map(\.price) == [100, 110, 125])
        #expect(month.stockReturn == 0.25)
        #expect(abs((month.benchmarkReturn ?? 0) - 0.05) < 1e-9)
        #expect(abs((month.excessReturn ?? 0) - 0.20) < 1e-9)
        #expect(abs((month.points[1].benchmark ?? 0) - 0.025) < 1e-9)
        // The period ends on the stock's last close.
        #expect(month.points.last?.date == day("2026-11-16"))

        let half = PerformanceSeries(stock: stock, benchmark: spy, range: .sixMonths)
        #expect(half.points.first?.price == 90)
    }

    @Test("year to date is measured from last year's final close")
    func yearToDate() {
        let stock = closes([("2025-12-30", 95), ("2025-12-31", 100), ("2026-01-02", 104), ("2026-11-16", 130)])
        let series = PerformanceSeries(stock: stock, benchmark: [], range: .yearToDate)
        #expect(series.points.map(\.price) == [100, 104, 130])
        #expect(abs((series.stockReturn ?? 0) - 0.30) < 1e-9)
        // No benchmark prices: the comparison is absent, not zero.
        #expect(series.benchmarkReturn == nil)
        #expect(series.excessReturn == nil)
    }

    /// 2026-11-23. Anthropic (ANT) listed on Nov 19; its year chart was
    /// titled "Past year −9.8%" over three closes. A history that starts
    /// inside the period says so, so the page can title it by its real days.
    @Test("a stock whose prices begin inside the period is marked as shorter than it")
    func shorterThanRange() {
        let ant = closes([("2026-11-19", 97.17), ("2026-11-20", 88.91), ("2026-11-23", 87.64)])
        let year = PerformanceSeries(stock: ant, benchmark: [], range: .oneYear)
        #expect(year.isShorterThanRange)
        #expect(year.tradingDays == 3)
        #expect(year.points.map(\.price) == [97.17, 88.91, 87.64])
        #expect(PerformanceSeries(stock: ant, benchmark: [], range: .yearToDate).isShorterThanRange)

        let stock = closes([("2026-08-14", 90), ("2026-10-16", 100), ("2026-10-30", 110), ("2026-11-16", 125)])
        let month = PerformanceSeries(stock: stock, benchmark: [], range: .oneMonth)
        #expect(!month.isShorterThanRange)
        #expect(month.tradingDays == 3)
        #expect(PerformanceSeries(stock: stock, benchmark: [], range: .oneYear).isShorterThanRange)

        let ytd = closes([("2025-12-31", 100), ("2026-01-02", 104), ("2026-11-16", 130)])
        #expect(!PerformanceSeries(stock: ytd, benchmark: [], range: .yearToDate).isShorterThanRange)
    }

    @Test("a long history is thinned for the chart but keeps its first and last day")
    func thinned() {
        let start = day("2021-11-16")
        let stock = (0..<1300).map { DailyClose(date: start.addingTimeInterval(Double($0) * 86_400), close: 100 + Double($0)) }
        let series = PerformanceSeries(stock: stock, benchmark: [], range: .fiveYears)
        #expect(series.points.count <= PerformanceSeries.maxPoints + 2)
        #expect(series.points.first?.price == 100)
        #expect(series.points.last?.price == 1399)
        #expect(PerformanceSeries(stock: [], benchmark: [], range: .oneYear).points.isEmpty)
    }

    @Test("a price history is fetched once per symbol, and the benchmark is never evicted")
    func historyCache() async throws {
        let counter = FetchCounter()
        let history = PriceHistory { symbol, _ in
            await counter.record(symbol)
            return [DailyClose(date: .now, close: 1)]
        }
        _ = try await history.closes(for: "spy")
        _ = try await history.closes(for: "SPY")
        for index in 0..<12 { _ = try await history.closes(for: "S\(index)") }
        _ = try await history.closes(for: "SPY")
        _ = try await history.closes(for: "S0")
        #expect(await counter.count("SPY") == 1)
        #expect(await counter.count("S0") == 2)
    }

    // MARK: Ending at the price now
    //
    // Production, 2026-11-25 at 12:58 New York time: NVDA's newest close in
    // the app was Monday's $165.05, the last real close was Tuesday's $155.38
    // and the stock was trading at $145.72. Every chart and model on the
    // company page stopped at a close.

    /// A moment given as New York wall-clock time.
    private func newYork(_ text: String) -> Date {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = TimeZone(identifier: "America/New_York")
        formatter.dateFormat = "yyyy-MM-dd HH:mm"
        return formatter.date(from: text)!
    }

    private func quote(_ price: Double, at moment: Date?, high: Double? = nil, low: Double? = nil) -> LiveQuote {
        LiveQuote(
            asOf: moment?.timeIntervalSince1970, change: 0, changePercent: 0,
            dayHigh: high, dayLow: low, fetchedAt: 0, price: price, symbol: "NVDA"
        )
    }

    @Test("the last completed session is the most recent weekday whose close has passed")
    func lastCompletedSession() {
        #expect(MarketHours.lastCompletedSession(at: newYork("2026-11-25 12:58")) == day("2026-11-24"))
        #expect(MarketHours.lastCompletedSession(at: newYork("2026-11-25 15:59")) == day("2026-11-24"))
        #expect(MarketHours.lastCompletedSession(at: newYork("2026-11-25 16:00")) == day("2026-11-25"))
        // Monday morning, Saturday and Sunday all look back to Friday.
        #expect(MarketHours.lastCompletedSession(at: newYork("2026-11-23 09:00")) == day("2026-11-20"))
        #expect(MarketHours.lastCompletedSession(at: newYork("2026-11-21 17:00")) == day("2026-11-20"))
        #expect(MarketHours.lastCompletedSession(at: newYork("2026-11-22 23:00")) == day("2026-11-20"))
        // Late evening in New York is already tomorrow in UTC; the trading
        // day is New York's.
        #expect(MarketHours.tradingDay(of: newYork("2026-11-25 21:30")) == day("2026-11-25"))
    }

    @Test("REGRESSION: with a live quote the history ends at the price now, not at the last close")
    func historyEndsAtTheLivePrice() {
        let history = closes([("2026-11-20", 125.53), ("2026-11-23", 165.05), ("2026-11-24", 155.38)])
        let live = quote(145.72, at: newYork("2026-11-25 12:58"), high: 146.42, low: 141.17)

        let ended = history.ending(at: live)
        #expect(ended.count == 4)
        #expect(ended.last == DailyClose(date: day("2026-11-25"), close: 145.72, high: 146.42, low: 141.17))
        #expect(ended.endsLive(at: newYork("2026-11-25 12:58")))
        #expect(!history.endsLive(at: newYork("2026-11-25 12:58")))

        // What is built on it ends there too: the period's return is to
        // $145.72, the price a person could trade at.
        let series = PerformanceSeries(stock: ended, benchmark: [], range: .oneMonth)
        #expect(series.points.last?.price == 145.72)
        #expect(abs((series.stockReturn ?? 0) - (145.72 / 125.53 - 1)) < 1e-12)
    }

    @Test("a quote from a day that already has its close adds nothing")
    func quoteFromAFinishedDay() {
        let history = closes([("2026-11-23", 165.05), ("2026-11-24", 155.38)])
        // Before Wednesday's open the quote is still Tuesday's last trade.
        #expect(history.ending(at: quote(155.40, at: newYork("2026-11-24 16:00"))) == history)
        // Older than the history, no trade time, no price, no quote, no history.
        #expect(history.ending(at: quote(150, at: newYork("2026-11-20 12:00"))) == history)
        #expect(history.ending(at: quote(150, at: nil)) == history)
        #expect(history.ending(at: quote(0, at: newYork("2026-11-25 12:58"))) == history)
        #expect(history.ending(at: nil) == history)
        #expect([DailyClose]().ending(at: quote(150, at: newYork("2026-11-25 12:58"))).isEmpty)
    }

    @Test("a quote without the day's range still makes a day, at the price")
    func quoteWithoutARange() {
        let history = closes([("2026-11-24", 155.38)])
        let last = history.ending(at: quote(145.72, at: newYork("2026-11-25 12:58"))).last
        #expect(last?.high == 145.72 && last?.low == 145.72)
    }

    @Test("REGRESSION: a history that has fallen behind is brought up to date, with only the days since")
    func historyCatchesUp() async throws {
        let clock = Clock(newYork("2026-11-25 12:58"))
        let asked = Asked()
        let monday = closes([("2026-11-20", 125.53), ("2026-11-23", 165.05)])
        let tuesday = closes([("2026-11-23", 165.05), ("2026-11-24", 155.38)])
        let history = PriceHistory(now: { clock.now }) { _, since in
            await asked.record(since)
            return since == nil ? monday : tuesday
        }

        // First look: everything. The backend had not yet loaded Tuesday.
        #expect(try await history.closes(for: "NVDA") == monday)
        // Looked at again inside five minutes: from memory.
        clock.advance(299)
        #expect(try await history.closes(for: "NVDA") == monday)
        #expect(await asked.all == [nil])

        // Five minutes on, still behind Tuesday's close: the days since Monday.
        clock.advance(2)
        let caught = try await history.closes(for: "NVDA")
        #expect(caught.map(\.close) == [125.53, 165.05, 155.38])
        #expect(await asked.all == [nil, day("2026-11-23")])

        // Up to the last completed close: nothing more to ask, however long.
        clock.advance(3_600)
        #expect(try await history.closes(for: "NVDA") == caught)
        #expect(await asked.all.count == 2)

        // Wednesday's close passes: asked again, from Tuesday.
        clock.set(newYork("2026-11-25 16:05"))
        _ = try await history.closes(for: "NVDA")
        #expect(await asked.all.last == day("2026-11-24"))
    }

    @Test("a failed look for newer days keeps the history already held")
    func historyCatchUpFails() async throws {
        let clock = Clock(newYork("2026-11-25 12:58"))
        let monday = closes([("2026-11-23", 165.05)])
        let history = PriceHistory(now: { clock.now }) { _, since in
            if since != nil { throw URLError(.notConnectedToInternet) }
            return monday
        }
        _ = try await history.closes(for: "NVDA")
        clock.advance(600)
        #expect(try await history.closes(for: "NVDA") == monday)
    }

    @Test("bringing a history up to date asks for the days from its last one")
    func dailyClosesSince() async throws {
        let (service, transport) = make()
        transport.stub("get_daily_prices_api_data_daily__symbol__get", .json(status: 200, "[]"))
        _ = try await service.dailyCloses("NVDA", since: day("2026-11-23"))
        #expect(transport.requests.last?.path == "/api/data/daily/NVDA?start=2026-11-23")
    }

    @Test("snapshots are asked for twelve at a time and keyed by symbol")
    func snapshots() async throws {
        let (service, transport) = make()
        transport.stub("get_market_overview_api_market_overview_get", .json(status: 200, """
        [{"symbol":"spy","name":"SPDR S&P 500","last_price":739.96,"prev_close":754.37,"change_pct":-0.0191,
          "change_abs":-14.41,"last_date":"2026-11-16","sparkline":[774.8,752.1,739.96]}]
        """))
        let symbols = (0..<14).map { "S\($0)" }
        let result = try await service.snapshots(symbols)
        #expect(result["SPY"]?.sparkline.count == 3)
        #expect(transport.requests.count == 2)
    }
}

private actor FetchCounter {
    private var counts: [String: Int] = [:]
    func record(_ symbol: String) { counts[symbol, default: 0] += 1 }
    func count(_ symbol: String) -> Int { counts[symbol] ?? 0 }
}

@MainActor
@Suite("Watchlist")
struct WatchlistTests {
    private func fresh() -> UserDefaults {
        let name = "watchlist-tests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defaults.removePersistentDomain(forName: name)
        return defaults
    }

    @Test("a new install starts with the widely held names")
    func starters() {
        #expect(Watchlist(defaults: fresh()).symbols == ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"])
    }

    @Test("adding, removing and reordering survive a relaunch")
    func persists() {
        let defaults = fresh()
        let list = Watchlist(defaults: defaults)
        list.toggle("amd", name: "Advanced Micro Devices")
        #expect(list.symbols.first == "AMD")
        #expect(list.contains("AMD"))
        list.toggle("AAPL", name: "Apple")
        #expect(!list.contains("aapl"))
        list.move(fromOffsets: [0], toOffset: 3)
        #expect(Array(list.symbols.prefix(3)) == ["MSFT", "NVDA", "AMD"])
        list.remove(atOffsets: [0])

        let relaunched = Watchlist(defaults: defaults)
        #expect(relaunched.symbols == list.symbols)
        #expect(relaunched.symbols.first == "NVDA")
    }

    @Test("an emptied list stays empty instead of refilling with starters")
    func emptied() {
        let defaults = fresh()
        let list = Watchlist(defaults: defaults)
        list.remove(atOffsets: IndexSet(0..<list.entries.count))
        #expect(Watchlist(defaults: defaults).entries.isEmpty)
    }

    @Test("recently viewed keeps the newest first, once each, capped")
    func recents() {
        let list = Watchlist(defaults: fresh())
        for index in 0..<10 { list.viewed("S\(index)", name: "Company \(index)") }
        list.viewed("s5", name: "Company 5")
        #expect(list.recents.count == Watchlist.maxRecents)
        #expect(list.recents.first?.symbol == "S5")
        #expect(list.recents.filter { $0.symbol == "S5" }.count == 1)
    }
}

/// A clock a test moves by hand.
private final class Clock: @unchecked Sendable {
    private let lock = NSLock()
    private var moment: Date
    init(_ start: Date) { moment = start }
    var now: Date { lock.withLock { moment } }
    func advance(_ seconds: TimeInterval) { lock.withLock { moment += seconds } }
    func set(_ date: Date) { lock.withLock { moment = date } }
}

/// The `since` of each request a history made.
private actor Asked {
    private(set) var all: [Date?] = []
    func record(_ since: Date?) { all.append(since) }
}
