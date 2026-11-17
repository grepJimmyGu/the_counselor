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
}
