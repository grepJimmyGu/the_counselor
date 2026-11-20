import Foundation
import LivermoreAPI
import Testing

@testable import LivermoreKit

private let server = URL(string: "https://api.test")!

private enum Op {
    static let status = "snaptrade_status_api_snaptrade_status_get"
    static let connect = "snaptrade_connect_api_snaptrade_connect_post"
    static let accounts = "snaptrade_accounts_api_snaptrade_accounts_get"
    static let preview = "preview_order_api_snaptrade_orders_preview_post"
    static let place = "place_order_api_snaptrade_orders_place_post"
    static let signup = "password_signup_api_auth_password_signup_post"
    static let confirm = "confirm_position_exit_api_saved_strategies__strategy_id__positions__position_id__confirm_exit_post"
    static let exits = "list_unresolved_exits_api_saved_strategies_unresolved_exits_get"
}

private func body(_ request: MockTransport.Recorded) throws -> [String: Any] {
    try #require(try JSONSerialization.jsonObject(with: Data(request.body.utf8)) as? [String: Any])
}

@MainActor
private func mocked() -> (AppSession, MockTransport) {
    let transport = MockTransport()
    return (AppSession(serverURL: server, store: InMemorySessionStore(DemoData.session), transport: transport), transport)
}

private func exit(
    action: String, shares: Double?, remaining: Double, initial: Double,
    resolution: String? = "daily", barDate: String? = "2026-11-13", change: Double? = -0.082
) -> UnresolvedExit {
    UnresolvedExit(
        action: action, barDate: barDate, barResolution: resolution, entryPrice: 100, pctChange: change,
        positionId: "p", price: 91.8, shares: shares, sharesInitial: initial, sharesRemaining: remaining,
        signaledAt: "2026-11-13T21:10:00Z", strategyId: "s", strategyTitle: "T", symbol: "AAPL",
        tierLabel: "Stop", triggerType: "stop_hit"
    )
}

@Suite("what an exit asks for")
struct UnresolvedExitTests {
    @Test("a sell-all tier is everything still held, whole shares rounded down")
    func sellAll() {
        #expect(exit(action: "sell_all", shares: nil, remaining: 25, initial: 25).quantity == .exact(25))
        #expect(exit(action: "sell_all", shares: nil, remaining: 12.9, initial: 25).quantity == .exact(12))
    }

    @Test("a partial tier on an untouched position is the suggested size")
    func partial() {
        #expect(exit(action: "sell_fraction", shares: 12.5, remaining: 25, initial: 25).quantity == .exact(12))
        // Fractional positions keep four places, still rounded down.
        #expect(exit(action: "sell_fraction", shares: 0.33337, remaining: 1.5, initial: 1.5).quantity == .exact(0.3333))
    }

    @Test("after an earlier tier of unknown outcome, no single number is stated")
    func ambiguous() {
        let later = exit(action: "sell_fraction", shares: 6, remaining: 18, initial: 24)
        #expect(later.quantity == .ambiguous(ifEarlierTierSold: 6, ifNot: 18))
    }

    @Test("the headline and the price caveat say which kind of price this is")
    func copy() {
        let daily = exit(action: "sell_all", shares: nil, remaining: 25, initial: 25)
        #expect(daily.headline == "Stop tier reached at -8.2%")
        #expect(daily.priceCaveat.contains("close of 2026-11-13"))
        #expect(daily.priceCaveat.contains("next open"))

        let intraday = exit(action: "sell_all", shares: nil, remaining: 25, initial: 25, resolution: "15min", barDate: nil)
        #expect(intraday.priceCaveat.contains("delayed"))
        // Absent means daily; with no bar date the signal's day is used.
        let unstamped = exit(action: "sell_all", shares: nil, remaining: 25, initial: 25, resolution: nil, barDate: nil, change: nil)
        #expect(unstamped.priceCaveat.contains("close of 2026-11-13"))
        #expect(unstamped.headline == "Stop tier reached")
        #expect(unstamped.id == "p:stop_hit")
    }
}

@MainActor
@Suite("BrokerageService")
struct BrokerageServiceTests {
    @Test("a sell is sized in shares and a buy in dollars — never both")
    func previewSizes() async throws {
        let (session, transport) = mocked()
        transport.stub(Op.preview, .json(status: 200, #"{"trade_id":"t-1","symbol":"AAPL","action":"SELL","units":25}"#))

        let sell = try await session.brokerage.preview(
            OrderDraft(accountID: "acct-1", symbol: "aapl", size: .sell(shares: 25))
        )
        #expect(sell.tradeId == "t-1")
        let sellBody = try body(transport.requests[0])
        #expect(sellBody["units"] as? Double == 25)
        #expect(sellBody["notional"] == nil)
        #expect(sellBody["symbol"] as? String == "AAPL")
        #expect(sellBody["action"] as? String == "SELL")
        #expect(sellBody["order_type"] as? String == "Market")

        _ = try await session.brokerage.preview(OrderDraft(accountID: "acct-1", symbol: "NVDA", size: .buy(dollars: 500)))
        let buyBody = try body(transport.requests[1])
        #expect(buyBody["notional"] as? Double == 500)
        #expect(buyBody["units"] == nil)
        #expect(buyBody["action"] as? String == "BUY")
    }

    @Test("a dollar-sized buy previews without a share count")
    func previewWithoutUnits() async throws {
        let (session, transport) = mocked()
        transport.stub(Op.preview, .json(status: 200, #"{"trade_id":"t-2","symbol":"NVDA","action":"BUY","estimated_commission":0,"remaining_cash":1200.5}"#))
        let preview = try await session.brokerage.preview(OrderDraft(accountID: "a", symbol: "NVDA", size: .buy(dollars: 500)))
        #expect(preview.units == nil)
        #expect(preview.remainingCash == 1200.5)
    }

    @Test("an order that can't be priced is refused before anything is sent")
    func invalidDrafts() async {
        let (session, transport) = mocked()
        for draft in [
            OrderDraft(accountID: "", symbol: "AAPL", size: .sell(shares: 1)),
            OrderDraft(accountID: "a", symbol: "", size: .sell(shares: 1)),
            OrderDraft(accountID: "a", symbol: "AAPL", size: .sell(shares: 0)),
            OrderDraft(accountID: "a", symbol: "AAPL", size: .buy(dollars: -5)),
        ] {
            await #expect(throws: APIFailure.rejected(draft.problem ?? "")) {
                try await session.brokerage.preview(draft)
            }
        }
        #expect(transport.requests.isEmpty)
    }

    @Test("placing sends the preview's id and nothing else")
    func place() async throws {
        let (session, transport) = mocked()
        transport.stub(Op.place, .json(status: 200, #"{"status":"ACCEPTED","brokerage_order_id":"B-9"}"#))
        let preview = OrderPreview(action: "SELL", symbol: "AAPL", tradeId: "t-1", units: 25)

        let receipt = try await session.brokerage.place(preview)

        #expect(receipt.brokerageOrderId == "B-9")
        #expect(transport.requests.count == 1)
        #expect(try body(transport.requests[0]).keys.sorted() == ["trade_id"])
        #expect(transport.requests[0].authorization == "Bearer demo-token")
    }

    @Test("switched off, upstream failure and bad request are three different answers")
    func failures() async {
        let (session, transport) = mocked()

        transport.stub(Op.preview, .json(status: 503, #"{"detail":"Order placement isn't enabled."}"#))
        await #expect(throws: APIFailure.turnedOff("Order placement isn't enabled.")) {
            try await session.brokerage.preview(OrderDraft(accountID: "a", symbol: "AAPL", size: .sell(shares: 1)))
        }

        // The preview route forwards the aggregator's raw exception text.
        transport.stub(Op.preview, .json(status: 502, #"{"detail":"(400)\nReason: Bad Request\nHTTP response body: {\"code\":\"1063\"}"}"#))
        await #expect(throws: APIFailure.upstream(nil)) {
            try await session.brokerage.preview(OrderDraft(accountID: "a", symbol: "AAPL", size: .sell(shares: 1)))
        }

        transport.stub(Op.accounts, .json(status: 502, #"{"detail":"Couldn't read your brokerage accounts."}"#))
        await #expect(throws: APIFailure.upstream("Couldn't read your brokerage accounts.")) {
            try await session.brokerage.accounts()
        }

        transport.stub(Op.preview, .json(status: 400, #"{"detail":"Not enough shares to sell."}"#))
        await #expect(throws: APIFailure.rejected("Not enough shares to sell.")) {
            try await session.brokerage.preview(OrderDraft(accountID: "a", symbol: "AAPL", size: .sell(shares: 1)))
        }
        #expect(APIFailure.upstream(nil).message.contains("brokerage"))
    }

    @Test("a brokerage link is only followed to an https address")
    func connectionURL() async throws {
        let (session, transport) = mocked()
        transport.stub(Op.connect, .json(status: 200, #"{"redirect_uri":"https://app.snaptrade.com/snapTrade/redeemToken?x=1"}"#))
        #expect(try await session.brokerage.connectionURL().host == "app.snaptrade.com")
        #expect(try body(transport.requests[0])["return_path"] as? String == "/account/brokerage")

        transport.stub(Op.connect, .json(status: 200, #"{"redirect_uri":"javascript:alert(1)"}"#))
        await #expect(throws: APIFailure.server(status: 200)) { try await session.brokerage.connectionURL() }
    }

    @Test("linked and able to trade are separate facts")
    func statusFlags() async throws {
        let (session, transport) = mocked()
        transport.stub(Op.status, .json(status: 200, #"{"configured":true,"registered":true,"connected_accounts":2,"trading_enabled":false}"#))
        let readOnly = try await session.brokerage.status()
        #expect(readOnly.isLinked)
        #expect(!readOnly.canTrade)

        transport.stub(Op.status, .json(status: 200, #"{"configured":true,"registered":true,"connected_accounts":0}"#))
        let registeredOnly = try await session.brokerage.status()
        #expect(!registeredOnly.isLinked)
        #expect(!registeredOnly.canTrade)
    }

    @Test("accounts are told apart by institution and last four digits")
    func accountNames() {
        #expect(BrokerAccount(id: "1", institutionName: "Robinhood", name: "Individual", number: "30014821").displayName == "Robinhood ···4821")
        #expect(BrokerAccount(id: "1", institutionName: "Schwab", name: "Roth IRA").displayName == "Schwab — Roth IRA")
        #expect(BrokerAccount(id: "1").displayName == "Brokerage account")
    }
}

@MainActor
@Suite("ActionService")
struct ActionServiceTests {
    @Test("confirming an exit reports the user's own fill against the right tier")
    func confirm() async throws {
        let (session, transport) = mocked()
        transport.stub(Op.confirm, .json(status: 200, #"{"id":"p","symbol":"AAPL","entered_at":"2026-11-16T14:45:00Z","entry_price":100,"shares_initial":25,"shares_remaining":0,"is_open":false,"trade_log":[]}"#))

        let position = try await session.actions.confirmExit(
            exit(action: "sell_all", shares: nil, remaining: 25, initial: 25), sharesSold: 25, fillPrice: 91.4
        )

        #expect(position.isOpen == false)
        let sent = try body(transport.requests[0])
        #expect(sent["trigger_type"] as? String == "stop_hit")
        #expect(sent["shares_sold"] as? Double == 25)
        #expect(sent["fill_price"] as? Double == 91.4)
    }

    @Test("an expired session on the inbox is reported as signed out")
    func expired() async {
        let (session, transport) = mocked()
        transport.stub(Op.exits, .json(status: 401, #"{"detail":"Invalid or expired session token."}"#))
        await #expect(throws: APIFailure.notSignedIn) { try await session.actions.unresolvedExits() }
    }
}

@MainActor
@Suite("the sample account")
struct DemoAccountTests {
    @Test("its exits decode, and deciding on one removes it from the list")
    func exits() async throws {
        let session = AppSession.demo()
        let waiting = try await session.actions.unresolvedExits()
        #expect(waiting.map(\.symbol) == ["AAPL", "MSFT"])
        #expect(waiting.map(\.isDaily) == [false, true])
        #expect(waiting.map(\.quantity) == [.exact(25), .exact(6)])

        let held = try await session.actions.hold(waiting[0])
        #expect(held.isOpen)
        #expect(try await session.actions.unresolvedExits().map(\.symbol) == ["MSFT"])

        let sold = try await session.actions.confirmExit(waiting[1], sharesSold: 6, fillPrice: nil)
        #expect(!sold.isOpen)
        #expect(try await session.actions.unresolvedExits().isEmpty)
    }

    @Test("its notices decode, and reading one clears it")
    func notices() async throws {
        let session = AppSession.demo()
        let notices = try await session.actions.notices()
        #expect(notices.count == 1)
        try await session.actions.acknowledge(notices[0])
        #expect(try await session.actions.notices().isEmpty)
    }

    @Test("its brokerage decodes: status, accounts, holdings, a preview and a receipt")
    func brokerage() async throws {
        let session = AppSession.demo()
        let status = try await session.brokerage.status()
        #expect(status.canTrade)
        let accounts = try await session.brokerage.accounts()
        #expect(accounts.map(\.displayName) == ["Sample Brokerage ···4821"])
        let holdings = try await session.brokerage.holdings()
        #expect(holdings.map(\.symbol) == ["NVDA", "AAPL", "MSFT", "SPAXX"])
        #expect(holdings.last?.cashEquivalent == true)
        #expect(holdings[0].marketValue == 40 * 156.14)

        let preview = try await session.brokerage.preview(
            OrderDraft(accountID: accounts[0].id, symbol: "AAPL", size: .sell(shares: 25))
        )
        #expect(preview.units == 25)
        let receipt = try await session.brokerage.place(preview)
        #expect(receipt.status?.contains("sample") == true)

        let declared = try await session.actions.declarePosition(strategyID: "s-trend", symbol: "amd", shares: 10, entryPrice: 120)
        #expect(declared.symbol == "AMD")
    }

    @Test("it never reaches a real account endpoint, and can never send an order")
    func isolated() async {
        // Only public, read-only calls go to the network.
        #expect(DemoData.liveOperations.allSatisfy { $0.hasSuffix("_get") })
        #expect(DemoData.liveOperations.allSatisfy { !$0.contains("snaptrade") && !$0.contains("saved_strategies") })
        // Price history is public market data, and the company page's
        // signals and models are empty without it.
        #expect(DemoData.liveOperations.contains("get_daily_prices_api_data_daily__symbol__get"))
        // Anything not answered from fixtures is refused locally.
        let session = AppSession.demo()
        let strategy = TemplateCatalog.runnable[0].strategy
        await #expect(throws: APIFailure.rejected("The sample account can't do this. Sign in to your own account.")) {
            try await session.backtests.run(strategy, templateID: "trend-following", signedIn: true)
        }
    }
}

@MainActor
@Suite("sign-up")
struct SignUpTests {
    private func make() -> (AppSession, MockTransport, InMemorySessionStore) {
        let transport = MockTransport()
        let store = InMemorySessionStore()
        return (AppSession(serverURL: server, store: store, transport: transport), transport, store)
    }

    @Test("a new account is signed in straight away")
    func success() async throws {
        let (session, transport, store) = make()
        transport.stub(Op.signup, .json(status: 201, Fixture.tokenResponse))

        try await session.signUp(email: " new@example.com ", password: "nuvmyz-Tapgo4-zimqyr", displayName: "  ")

        #expect(session.isSignedIn)
        #expect(store.load()?.token == "tok-123")
        let sent = try body(transport.requests[0])
        #expect(sent["email"] as? String == "new@example.com")
        // A blank name is left out rather than stored as spaces.
        #expect(sent["display_name"] == nil)
    }

    @Test("an address that already has an account says so")
    func taken() async {
        let (session, transport, _) = make()
        transport.stub(Op.signup, .json(status: 409, #"{"detail":"An account with this email already exists."}"#))
        await #expect(throws: SignInError.emailTaken) {
            try await session.signUp(email: "me@example.com", password: "nuvmyz-Tapgo4-zimqyr", displayName: nil)
        }
        #expect(!session.isSignedIn)
    }

    @Test("a password that breaks a rule is refused on the device")
    func weak() async {
        let (session, transport, _) = make()
        // Twelve characters and four kinds, but it contains the account's own name.
        for password in ["short", "long-enough-but-plain", "Me-Jordan-4-ever!"] {
            await #expect(throws: SignInError.weakPassword) {
                try await session.signUp(email: "jordan@example.com", password: password, displayName: nil)
            }
        }
        #expect(transport.requests.isEmpty)
    }

    @Test("a password the backend refuses is reported in the backend's words")
    func refusedByBackend() async {
        // Only the backend can know a password has appeared in a breach.
        let (session, transport, _) = make()
        let reason = "That password has appeared in a known data breach. Choose a different one."
        transport.stub(Op.signup, .json(status: 400, #"{"detail":"\#(reason)","code":"breached_password","failed":[]}"#))
        await #expect(throws: SignInError.passwordRejected(reason)) {
            try await session.signUp(email: "me@example.com", password: "nuvmyz-Tapgo4-zimqyr", displayName: nil)
        }
        #expect(!session.isSignedIn)
    }
}
