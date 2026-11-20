import Foundation
import Testing

@testable import LivermoreKit

/// Records what the store asked for and answers from a script.
private actor FakeQuotes {
    private(set) var calls: [[String]] = []
    private var prices: [String: Double]
    private var failing = false

    init(prices: [String: Double]) {
        self.prices = prices
    }

    func set(_ symbol: String, _ price: Double) { prices[symbol] = price }
    func setFailing(_ value: Bool) { failing = value }

    func fetch(_ symbols: [String]) throws -> [String: LiveQuote] {
        calls.append(symbols)
        if failing { throw URLError(.notConnectedToInternet) }
        var result: [String: LiveQuote] = [:]
        for symbol in symbols {
            guard let price = prices[symbol] else { continue }
            result[symbol] = LiveQuote(change: 0, changePercent: 0, fetchedAt: 0, price: price, symbol: symbol)
        }
        return result
    }
}

@MainActor
private func makeStore(_ fake: FakeQuotes, interval: Duration = .seconds(3600)) -> QuoteStore {
    QuoteStore(interval: interval, now: { Date(timeIntervalSince1970: 1_800_000_000) }) { symbols in
        try await fake.fetch(symbols)
    }
}

/// Polls until `condition` holds; the store refreshes on its own task.
@MainActor
private func eventually(_ condition: @MainActor () async -> Bool) async -> Bool {
    for _ in 0..<200 {
        if await condition() { return true }
        try? await Task.sleep(for: .milliseconds(5))
    }
    return false
}

@Suite("QuoteStore")
@MainActor
struct QuoteStoreTests {
    @Test("watching a symbol fetches it straight away, and stamps when")
    func watchFetches() async {
        let fake = FakeQuotes(prices: ["AAPL": 210.5])
        let store = makeStore(fake)
        #expect(store.lastChecked == nil)

        store.watch([" aapl "])
        #expect(await eventually { store.quotes["AAPL"]?.price == 210.5 })
        #expect(store.lastChecked == Date(timeIntervalSince1970: 1_800_000_000))
        #expect(store.lastRefreshFailed == false)
        #expect(await fake.calls == [["AAPL"]])
        store.unwatch(["AAPL"])
    }

    @Test("screens share one request for the union of what they show")
    func union() async {
        let fake = FakeQuotes(prices: ["AAPL": 1, "MSFT": 2, "NVDA": 3])
        let store = makeStore(fake)
        store.watch(["AAPL", "MSFT"])
        store.watch(["MSFT", "NVDA"])
        #expect(store.watchedSymbols == ["AAPL", "MSFT", "NVDA"])
        #expect(await eventually { store.quotes.count == 3 })
        #expect(await fake.calls.last == ["AAPL", "MSFT", "NVDA"])

        // MSFT is still on the second screen after the first lets go.
        store.unwatch(["AAPL", "MSFT"])
        #expect(store.watchedSymbols == ["MSFT", "NVDA"])
        store.unwatch(["MSFT", "NVDA"])
        #expect(store.watchedSymbols == [])
    }

    @Test("prices keep refreshing on the interval while watched, and stop after")
    func polls() async {
        let fake = FakeQuotes(prices: ["AAPL": 100])
        let store = makeStore(fake, interval: .milliseconds(20))
        store.watch(["AAPL"])
        #expect(await eventually { store.quotes["AAPL"]?.price == 100 })

        await fake.set("AAPL", 101)
        #expect(await eventually { store.quotes["AAPL"]?.price == 101 })

        store.unwatch(["AAPL"])
        try? await Task.sleep(for: .milliseconds(60))
        let settled = await fake.calls.count
        try? await Task.sleep(for: .milliseconds(100))
        #expect(await fake.calls.count == settled)
    }

    @Test("a failed refresh keeps the last known price and says so")
    func failureKeepsLastKnown() async {
        let fake = FakeQuotes(prices: ["AAPL": 100])
        let store = makeStore(fake)
        store.watch(["AAPL"])
        #expect(await eventually { store.quotes["AAPL"] != nil })

        await fake.setFailing(true)
        await store.refresh()
        #expect(store.quotes["AAPL"]?.price == 100)
        #expect(store.lastRefreshFailed)

        await fake.setFailing(false)
        await store.refresh()
        #expect(store.lastRefreshFailed == false)
        store.unwatch(["AAPL"])
    }

    @Test("a symbol the backend has no quote for is simply absent")
    func missingSymbol() async {
        let fake = FakeQuotes(prices: ["AAPL": 100])
        let store = makeStore(fake)
        store.watch(["AAPL", "NOPE"])
        #expect(await eventually { store.quotes["AAPL"] != nil })
        #expect(store.quotes["NOPE"] == nil)
        #expect(store.lastRefreshFailed == false)
        store.unwatch(["AAPL", "NOPE"])
    }

    @Test("nothing is fetched in the background, and returning refreshes at once")
    func pausesInBackground() async {
        let fake = FakeQuotes(prices: ["AAPL": 100])
        let store = makeStore(fake, interval: .milliseconds(20))
        store.watch(["AAPL"])
        #expect(await eventually { store.quotes["AAPL"] != nil })

        store.setActive(false)
        try? await Task.sleep(for: .milliseconds(60))
        let paused = await fake.calls.count
        await fake.set("AAPL", 105)
        try? await Task.sleep(for: .milliseconds(100))
        #expect(await fake.calls.count == paused)
        #expect(store.quotes["AAPL"]?.price == 100)

        store.setActive(true)
        #expect(await eventually { store.quotes["AAPL"]?.price == 105 })
        store.unwatch(["AAPL"])
    }

    @Test("more symbols than the endpoint takes are split across requests")
    func batches() async {
        let symbols = (0..<230).map { "S\($0)" }
        let fake = FakeQuotes(prices: Dictionary(uniqueKeysWithValues: symbols.map { ($0, 1.0) }))
        let store = makeStore(fake)
        store.watch(symbols)
        #expect(await eventually { store.quotes.count == 230 })
        #expect(await fake.calls.map(\.count) == [100, 100, 30])
        store.unwatch(symbols)
    }
}
