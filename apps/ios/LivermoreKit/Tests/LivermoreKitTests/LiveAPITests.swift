import Foundation
import Testing

@testable import LivermoreKit

/// Read-only checks against production. Off by default so the suite never
/// depends on the network: `LIVERMORE_LIVE_TESTS=1 swift test`.
@MainActor
@Suite("live API", .enabled(if: ProcessInfo.processInfo.environment["LIVERMORE_LIVE_TESTS"] == "1"))
struct LiveAPITests {
    @Test("production rejects a wrong password the way the client expects")
    func wrongPasswordIs401() async {
        let session = AppSession(store: InMemorySessionStore())
        await #expect(throws: SignInError.invalidCredentials) {
            try await session.signIn(email: "ios-contract-probe@livermorealpha.com", password: "not-the-password")
        }
        #expect(session.state == .signedOut)
    }

    @Test("a live quote decodes into the generated type")
    func liveQuoteDecodes() async throws {
        let session = AppSession(store: InMemorySessionStore())
        let response = try await session.client.getLiveQuotesApiLiveQuotesGet(query: .init(symbols: "AAPL"))
        let quotes = try response.ok.body.json.quotes.additionalProperties
        let apple = try #require(quotes["AAPL"])
        #expect(apple.price > 0)
        #expect(apple.symbol == "AAPL")
    }

    // The research endpoints: each must decode into its generated type. A
    // field the schema calls required but production omits, or a date in a
    // format the decoder rejects, shows up here rather than on a phone.

    @Test("search puts the US listing first for a ticker")
    func searchRanksUSListing() async throws {
        let session = AppSession(store: InMemorySessionStore())
        let matches = try await session.research.search("AAPL")
        #expect(matches.first?.symbol == "AAPL")
    }

    @Test("a company overview and its trend decode and can be scored")
    func overviewAndTrendDecode() async throws {
        let session = AppSession(store: InMemorySessionStore())
        let overview = try await session.research.overview("AAPL")
        let trend = try await session.research.trend("AAPL")
        #expect(overview.symbol == "AAPL")
        #expect(trend.pricePoints.count > 30)
        let metrics = StockMetrics(overview: overview, trend: trend)
        #expect(metrics.peRatio != nil)
        #expect((0...100).contains(StockScoring.health(metrics)))
    }

    @Test("sentiment decodes, including its timestamps")
    func sentimentDecodes() async throws {
        let session = AppSession(store: InMemorySessionStore())
        let summary = try await session.research.sentiment("AAPL")
        #expect(summary.symbol == "AAPL")
    }

    @Test("the supply-chain summary decodes")
    func supplyChainDecodes() async throws {
        let session = AppSession(store: InMemorySessionStore())
        let summary = try await session.research.supplyChain("AAPL")
        #expect(!summary.verdict.isEmpty)
    }
}
