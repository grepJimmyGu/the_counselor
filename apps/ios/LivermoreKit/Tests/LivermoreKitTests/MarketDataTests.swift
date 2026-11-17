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
        let history = PriceHistory { symbol in
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
