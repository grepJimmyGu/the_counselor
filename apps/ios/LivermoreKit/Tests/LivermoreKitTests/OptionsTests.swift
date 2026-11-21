import Foundation
import Testing

@testable import LivermoreKit

private let server = URL(string: "https://api.test")!

private enum OptionOp {
    static let chain = "get_chain_api_options__symbol__chain_get"
    static let plans = "list_plans_api_options_plans_get"
    static let save = "save_plan_api_options_plans_post"
    static let delete = "delete_plan_api_options_plans__plan_id__delete"
}

/// NVIDIA's chain at the close on 2026-11-20, when the stock closed at
/// $125.53. The January 15, 2027 expiry, with strikes every $5.
private func chainJSON(_ expiration: String? = nil) -> String {
    String(decoding: DemoData.optionChain(expiration: expiration)!, as: UTF8.self)
}

private func chain(_ expiration: String? = nil) throws -> OptionChain {
    let decoder = JSONDecoder()
    return try decoder.decode(OptionChain.self, from: DemoData.optionChain(expiration: expiration)!)
}

private func draft(_ strategy: OptionStrategy, contracts: Int = 1) throws -> OptionPlanDraft {
    try #require(OptionPlanDraft(strategy: strategy, chain: try chain(), contracts: contracts))
}

private func close(_ a: Double?, _ b: Double, within tolerance: Double = 0.005) -> Bool {
    guard let a else { return false }
    return abs(a - b) <= tolerance
}

@Suite("what an option plan makes or loses at expiry")
struct OptionPayoffTests {
    @Test("buying a call: lose the fee at most, no limit on the way up")
    func longCall() {
        // The $125 call at $14.23: $1,423 for one contract.
        let payoff = OptionPayoff(legs: [
            OptionLeg(kind: .call, side: .buy, quantity: 1, price: 14.23, strike: 125),
        ])
        #expect(close(payoff.cashNow, 1423))
        #expect(close(payoff.maxLoss, 1423))
        #expect(payoff.maxGain == nil)
        #expect(payoff.breakevens.count == 1 && close(payoff.breakevens.first, 139.23))
        #expect(close(payoff.profit(at: 100), -1423))
        #expect(close(payoff.profit(at: 125), -1423))
        #expect(close(payoff.profit(at: 139.23), 0))
        #expect(close(payoff.profit(at: 160), 2077))
    }

    @Test("buying a put: lose the fee at most, make the most if the stock goes to zero")
    func longPut() {
        let payoff = OptionPayoff(legs: [
            OptionLeg(kind: .put, side: .buy, quantity: 1, price: 12.40, strike: 125),
        ])
        #expect(close(payoff.cashNow, 1240))
        #expect(close(payoff.maxLoss, 1240))
        #expect(close(payoff.maxGain, 11260))
        #expect(payoff.breakevens.count == 1 && close(payoff.breakevens.first, 112.60))
        #expect(close(payoff.profit(at: 0), 11260))
        #expect(close(payoff.profit(at: 200), -1240))
    }

    @Test("a covered call: paid now, capped above the strike, still exposed below")
    func coveredCall() {
        // 100 shares at $125.53, and the $135 call sold for $9.48.
        let payoff = OptionPayoff(legs: [
            OptionLeg(kind: .stock, side: .buy, quantity: 100, price: 125.53),
            OptionLeg(kind: .call, side: .sell, quantity: 1, price: 9.48, strike: 135),
        ])
        #expect(close(payoff.cashNow, -948))
        // Shares called away at 135: 9.47 a share, plus the 9.48 received.
        #expect(close(payoff.maxGain, 1895))
        // Shares worthless, less the 9.48 kept.
        #expect(close(payoff.maxLoss, 11605))
        #expect(payoff.breakevens.count == 1 && close(payoff.breakevens.first, 116.05))
        #expect(close(payoff.profit(at: 135), 1895) && close(payoff.profit(at: 300), 1895))
    }

    @Test("a protective put: a floor under the shares, at the cost of the fee")
    func protectivePut() {
        // 100 shares at $125.53, and the $115 put bought for $8.68.
        let payoff = OptionPayoff(legs: [
            OptionLeg(kind: .stock, side: .buy, quantity: 100, price: 125.53),
            OptionLeg(kind: .put, side: .buy, quantity: 1, price: 8.68, strike: 115),
        ])
        #expect(close(payoff.cashNow, 868))
        // Sold at 115 whatever happens: 10.53 a share lost, plus the 8.68 fee.
        #expect(close(payoff.maxLoss, 1921))
        #expect(payoff.maxGain == nil)
        #expect(payoff.breakevens.count == 1 && close(payoff.breakevens.first, 134.21))
        #expect(close(payoff.profit(at: 0), -1921) && close(payoff.profit(at: 115), -1921))
    }

    @Test("more contracts scale every number")
    func quantity() {
        let one = OptionPayoff(legs: [OptionLeg(kind: .call, side: .buy, quantity: 1, price: 14.23, strike: 125)])
        let three = OptionPayoff(legs: [OptionLeg(kind: .call, side: .buy, quantity: 3, price: 14.23, strike: 125)])
        #expect(close(three.maxLoss, 4269) && close(three.profit(at: 160), 3 * one.profit(at: 160)))
        #expect(three.breakevens == one.breakevens)
    }

    @Test("the same arithmetic covers shapes the app does not offer yet")
    func general() {
        // Selling a call with no shares behind it has no limit to its loss.
        let naked = OptionPayoff(legs: [OptionLeg(kind: .call, side: .sell, quantity: 1, price: 5, strike: 100)])
        #expect(naked.maxLoss == nil && close(naked.maxGain, 500) && close(naked.breakevens.first, 105))
        // A call and a put at the same strike: two breakevens.
        let straddle = OptionPayoff(legs: [
            OptionLeg(kind: .call, side: .buy, quantity: 1, price: 6, strike: 100),
            OptionLeg(kind: .put, side: .buy, quantity: 1, price: 4, strike: 100),
        ])
        #expect(straddle.breakevens.count == 2)
        #expect(close(straddle.breakevens[0], 90) && close(straddle.breakevens[1], 110))
        #expect(close(straddle.maxLoss, 1000) && straddle.maxGain == nil)
        // A call spread is capped both ways.
        let spread = OptionPayoff(legs: [
            OptionLeg(kind: .call, side: .buy, quantity: 1, price: 6, strike: 100),
            OptionLeg(kind: .call, side: .sell, quantity: 1, price: 2, strike: 110),
        ])
        #expect(close(spread.maxLoss, 400) && close(spread.maxGain, 600) && close(spread.breakevens.first, 104))
        // A free option cannot lose and never quite breaks even.
        let free = OptionPayoff(legs: [OptionLeg(kind: .call, side: .buy, quantity: 1, price: 0, strike: 100)])
        #expect(close(free.maxLoss, 0) && free.breakevens.isEmpty)
    }

    @Test("the chart's line turns exactly at the strike and the breakeven")
    func curve() {
        let payoff = OptionPayoff(legs: [OptionLeg(kind: .call, side: .buy, quantity: 1, price: 14.23, strike: 125)])
        let points = payoff.curve(from: 100, to: 160)
        #expect(points.map(\.price) == [100, 125, 139.23, 160])
        #expect(close(points[2].profit, 0))
    }
}

@Suite("where a plan starts")
struct OptionStrategyTests {
    private let strikes: [Double] = [105, 110, 115, 120, 125, 130, 135, 140, 145, 150]

    @Test("buying starts at the price; plans about shares held start 5% away")
    func defaults() {
        #expect(OptionStrategy.longCall.defaultStrike(in: strikes, price: 125.53) == 125)
        #expect(OptionStrategy.longPut.defaultStrike(in: strikes, price: 125.53) == 125)
        // 5% above 125.53 is 131.81: the first strike past it.
        #expect(OptionStrategy.coveredCall.defaultStrike(in: strikes, price: 125.53) == 135)
        // 5% below is 119.25: the first strike under it.
        #expect(OptionStrategy.protectivePut.defaultStrike(in: strikes, price: 125.53) == 115)
    }

    @Test("with no strike that far away, the nearest end is used")
    func edges() {
        #expect(OptionStrategy.coveredCall.defaultStrike(in: [100, 105], price: 125.53) == 105)
        #expect(OptionStrategy.protectivePut.defaultStrike(in: [140, 145], price: 125.53) == 140)
        #expect(OptionStrategy.longCall.defaultStrike(in: [], price: 125.53) == nil)
    }

    @Test("each plan is the option, plus the shares it is written against")
    func legs() {
        let call = OptionStrategy.longCall.legs(
            strike: 125, expiration: "2027-01-15", contractID: "NVDA270115C00125000",
            premium: 14.23, contracts: 2, underlyingPrice: 125.53
        )
        #expect(call == [OptionLeg(kind: .call, side: .buy, quantity: 2, price: 14.23, strike: 125,
                                   expiration: "2027-01-15", contractID: "NVDA270115C00125000")])
        let covered = OptionStrategy.coveredCall.legs(
            strike: 135, expiration: "2027-01-15", contractID: "NVDA270115C00135000",
            premium: 9.48, contracts: 2, underlyingPrice: 125.53
        )
        #expect(covered.count == 2)
        #expect(covered[0] == OptionLeg(kind: .stock, side: .buy, quantity: 200, price: 125.53))
        #expect(covered[1].side == .sell && covered[1].kind == .call)
        #expect(OptionStrategy.protectivePut.legs(
            strike: 115, expiration: "2027-01-15", contractID: "x", premium: 8.68, contracts: 1, underlyingPrice: 125.53
        ).map(\.kind) == [.stock, .put])
    }
}

@Suite("a plan built from a real chain")
struct OptionPlanTests {
    @Test("buying a call, in the app's own words")
    func longCall() throws {
        let plan = try draft(.longCall).plan
        #expect(plan.headline == "Pay $1,423 now. You profit if NVDA is above $139.23 on Jan 15, 2027.")
        #expect(plan.figures.map(\.label) == ["You pay now", "Most you can lose", "Most you can make", "Breakeven"])
        #expect(plan.figures.map(\.value) == ["$1,423", "$1,423", "No limit", "$139.23"])
        #expect(plan.figures[0].detail == "1 contract × 100 shares × $14.23")
        #expect(plan.figures[1].detail == "If NVDA is at or below $125 on Jan 15")
        #expect(plan.figures[3].detail == "NVDA needs to rise 10.9% from $125.53")
        #expect(plan.title == "NVDA $125 call · Jan 15, 2027")
        #expect(plan.caution == nil)
    }

    @Test("buying a put")
    func longPut() throws {
        let plan = try draft(.longPut).plan
        #expect(plan.headline == "Pay $1,240 now. You profit if NVDA is below $112.60 on Jan 15, 2027.")
        #expect(plan.figures.map(\.value) == ["$1,240", "$1,240", "$100 per $1 fall", "$112.60"])
        #expect(plan.figures[3].detail == "NVDA needs to fall 10.3% from $125.53")
    }

    /// Changed on purpose (2026-11-20): this used to assert the tile read
    /// "$11,260 — If NVDA falls to $0". Jimmy pointed out that a share price
    /// of $0 by the expiry is not a real outcome, so the big number misled.
    @Test("a put's gain is stated per $1 of fall, with the $0 ceiling in the small print")
    func longPutGainIsNotHeadlinedAtZero() throws {
        let gain = try draft(.longPut).plan.figures[2]
        #expect(gain.label == "What you can make")
        #expect(gain.value == "$100 per $1 fall")
        #expect(gain.detail == "For each $1 NVDA is below $112.60 on Jan 15. It tops out at $11,260, only if NVDA went to $0.")

        var three = try draft(.longPut)
        three.contracts = 3
        #expect(three.plan.figures[2].value == "$300 per $1 fall")
    }

    @Test("a covered call says what is received and what is agreed to")
    func coveredCall() throws {
        let plan = try draft(.coveredCall).plan
        #expect(plan.headline == "Receive $948 now. In return you sell your 100 NVDA shares at $135 if NVDA is above that on Jan 15, 2027.")
        #expect(plan.figures.map(\.label).first == "You receive now")
        #expect(plan.figures.map(\.value) == ["$948", "$11,605", "$1,895", "$116.05"])
        #expect(plan.figures[3].detail == "NVDA can fall 7.6% from $125.53 before you are behind")
        #expect(plan.caution == "The buyer can take your shares at $135 before Jan 15, most often just before a dividend.")
    }

    @Test("a protective put")
    func protectivePut() throws {
        let plan = try draft(.protectivePut).plan
        #expect(plan.headline == "Pay $868 now. Until Jan 15, 2027 your 100 NVDA shares can be sold at $115, however far the price falls.")
        #expect(plan.figures.map(\.value) == ["$868", "$1,921", "No limit", "$134.21"])
        #expect(plan.figures[3].detail == "NVDA needs to rise 6.9% from $125.53 to cover the fee")
    }

    @Test("what happens at a price the user picks on the chart")
    func outcome() throws {
        let plan = try draft(.longCall).plan
        #expect(plan.outcome(at: 160) == "If NVDA is at $160.00 on Jan 15, you make $2,077.")
        #expect(plan.outcome(at: 120) == "If NVDA is at $120.00 on Jan 15, you lose $1,423.")
        #expect(plan.outcome(at: 139.23) == "If NVDA is at $139.23 on Jan 15, you break even.")
    }

    @Test("moving the strike and the size changes the plan")
    func adjusting() throws {
        var draft = try draft(.longCall)
        #expect(draft.strike == 125 && draft.strikeDistance == "at the price")
        draft.strikeIndex += 2
        #expect(draft.strike == 135 && draft.strikeDistance == "7.5% above the price")
        #expect(draft.plan.figures.map(\.value) == ["$948", "$948", "No limit", "$144.48"])
        draft.contracts = 3
        #expect(draft.plan.figures[0].value == "$2,844")
        #expect(draft.plan.figures[0].detail == "3 contracts × 100 shares × $9.48")
        // The slider and the stepper cannot leave what exists.
        draft.strikeIndex = 999
        #expect(draft.strike == 150)
        draft.strikeIndex = -5
        #expect(draft.strike == 100)
        draft.contracts = 0
        #expect(draft.contracts == 1)
        draft.contracts = 9_999
        #expect(draft.contracts == OptionPlanDraft.maxContracts)
    }

    @Test("changing the expiry keeps the strike and the size the user chose")
    func changingExpiry() throws {
        var first = try draft(.longCall, contracts: 2)
        first.strikeIndex += 2
        let december = try chain("2026-12-18")
        let moved = try #require(OptionPlanDraft(strategy: .longCall, chain: december, near: first.strike, contracts: first.contracts))
        #expect(moved.strike == 135 && moved.contracts == 2)
        #expect(moved.plan.expiration == "2026-12-18")
    }

    @Test("an expiry with no contract of the kind needed cannot be planned on")
    func nothingToPlanOn() throws {
        var callsOnly = try chain()
        callsOnly.contracts.removeAll { $0.kind == .put }
        #expect(OptionPlanDraft(strategy: .longPut, chain: callsOnly) == nil)
        #expect(OptionPlanDraft(strategy: .longCall, chain: callsOnly) != nil)
    }

    @Test("the chart covers the price, the strike, the breakeven and the implied range")
    func chartRange() throws {
        let plan = try draft(.longCall).plan
        // 21.2% of 125.53 is 26.61 either side: 98.92 to 152.14.
        let range = plan.chartRange(including: try chain().impliedRange)
        #expect(range.lowerBound < 98.92 && range.upperBound > 152.14)
        #expect(range.contains(139.23) && range.lowerBound > 0)
        let plain = plan.chartRange()
        #expect(plain.contains(125) && plain.contains(139.23) && plain.lowerBound > range.lowerBound)
    }

    @Test("the ticket is written the way a broker's order screen reads")
    func ticket() throws {
        let call = OptionTicket(plan: try draft(.longCall, contracts: 2).plan)
        #expect(call.lines.count == 1)
        #expect(call.lines[0].action == "Buy to open")
        #expect(call.lines[0].contract == "2 NVDA Jan 15, 2027 $125 call")
        #expect(call.lines[0].limit == "Limit $14.23")
        #expect(call.lines[0].contractSymbol == "NVDA270115C00125000")
        #expect(call.requirement == nil)
        #expect(call.text == """
        Buy to open 2 NVDA Jan 15, 2027 $125 call
        Limit $14.23 per share
        Contract NVDA270115C00125000
        Prices from the close on Nov 20, 2026. Check the live price before you send it.
        """)
        #expect(call.steps.count == 5)
        #expect(call.steps[1] == "Find the contract: Jan 15, 2027 $125 call.")
        #expect(call.steps[2] == "Choose Buy to open, 2 contracts.")
        #expect(call.steps[3].contains("$14.23 was the price at the last close"))
        let covered = OptionTicket(plan: try draft(.coveredCall).plan)
        #expect(covered.lines.map(\.action) == ["Sell to open"])
        #expect(covered.requirement == "You need 100 NVDA shares in the same account.")
        #expect(covered.text.contains("You need 100 NVDA shares in the same account."))
    }
}

@Suite("the words a first-time user meets")
struct OptionTermTests {
    @Test("every term has a one-sentence meaning in plain words")
    func terms() {
        for term in OptionTerm.allCases {
            #expect(!term.title.isEmpty)
            #expect(term.meaning.count > 30 && term.meaning.count < 200 && term.meaning.hasSuffix("."))
        }
        #expect(OptionStrategy.allCases.map(\.goal) == [
            "I think it will go up", "I think it will go down", "Earn income on shares I own", "Protect shares I own",
        ])
        #expect(OptionStrategy.allCases.map(\.needs) == [
            "Needs cash for the fee", "Needs cash for the fee", "Needs 100 shares", "Needs 100 shares",
        ])
    }
}

@Suite("reading a chain")
struct OptionChainTests {
    @Test("the first expiries offered are the monthly ones one, three and six months out")
    func quickExpirations() throws {
        let chain = try chain()
        #expect(chain.expiration == "2027-01-15" && chain.defaultExpiration == "2027-01-15")
        #expect(chain.quickExpirations.map(\.date) == ["2027-01-15", "2027-03-19", "2027-06-17"])
        #expect(chain.quickExpirations.map(\.label) == ["Jan 15 · 56 days", "Mar 19 · 119 days", "Jun 17 · 209 days"])
        #expect(chain.selected?.impliedMovePct == 21.2)
    }

    @Test("the implied range is the at-the-money call and put either side of the price")
    func impliedRange() throws {
        let range = try #require(try chain().impliedRange)
        #expect(close(range.lowerBound, 98.92, within: 0.01) && close(range.upperBound, 152.14, within: 0.01))
        var unknown = try chain()
        unknown.expirations = unknown.expirations.map { var e = $0; e.impliedMovePct = nil; return e }
        #expect(unknown.impliedRange == nil)
    }

    @Test("a contract few people trade is called out with its own numbers")
    func thinlyTraded() throws {
        let weekly = try chain("2026-11-27")
        let thin = try #require(weekly.contracts.first { $0.contractId == "NVDA261127C00105000" })
        #expect(thin.thinlyTraded == "Thinly traded: 2 contracts are open, buyers bid $21.65 and sellers ask $23.25. You may not get the price shown.")
        let busy = try #require(try chain().contracts.first { $0.contractId == "NVDA270115C00125000" })
        #expect(busy.thinlyTraded == nil)
        // Plenty open, but buyers and sellers far apart.
        var wide = busy
        wide.bid = 10; wide.ask = 14; wide.mid = 12
        #expect(wide.thinlyTraded?.hasPrefix("Thinly traded: 9256 contracts are open") == true)
    }

    @Test("every sample expiry decodes and has both calls and puts")
    func fixtures() throws {
        for expiration in ["2026-11-27", "2026-12-18", "2027-01-15", "2027-03-19", "2027-06-17"] {
            let chain = try chain(expiration)
            #expect(chain.expiration == expiration && chain.symbol == "NVDA" && chain.asOf == "2026-11-20")
            #expect(!chain.quotes(.call).isEmpty && !chain.quotes(.put).isEmpty)
            #expect(chain.quotes(.call).map(\.strike) == chain.quotes(.call).map(\.strike).sorted())
        }
        #expect(DemoData.optionChain(expiration: "2030-01-01") == nil)
    }
}

@MainActor
@Suite("the options endpoints")
struct OptionsServiceTests {
    private func service(_ transport: MockTransport) -> OptionsService {
        AppSession(serverURL: server, store: InMemorySessionStore(), biometrics: InMemoryBiometricStore(), transport: transport).options
    }

    @Test("the chain is asked for by symbol, and by expiry when one is chosen")
    func chainRequests() async throws {
        let transport = MockTransport()
        transport.stub(OptionOp.chain, .json(status: 200, chainJSON()))
        let options = service(transport)
        let first = try await options.chain("NVDA")
        #expect(first.underlyingPrice == 125.53 && first.contracts.count == 21)
        _ = try await options.chain("NVDA", expiration: "2026-12-18")
        #expect(transport.requests.map(\.path) == ["/api/options/NVDA/chain", "/api/options/NVDA/chain?expiration=2026-12-18"])
    }

    @Test("a stock with no options says so in the backend's words")
    func noOptions() async {
        let transport = MockTransport()
        transport.stub(OptionOp.chain, .json(status: 404, #"{"detail":"There are no listed options for LCUT."}"#))
        do {
            _ = try await service(transport).chain("LCUT")
            Issue.record("expected a failure")
        } catch {
            #expect(OptionsService.message(for: error) == "There are no listed options for LCUT.")
        }
    }

    @Test("other failures get a message a person can act on")
    func failures() async {
        // A backend older than the app has no such endpoint.
        #expect(OptionsService.message(for: .unavailable("Not Found")) == "Options aren't available yet. Try again later.")
        #expect(OptionsService.message(for: .unavailable("")) == "Options aren't available yet. Try again later.")
        // Raw exception text is never shown.
        #expect(OptionsService.message(for: .unavailable("Traceback (most recent call last)")) == APIFailure.unavailable("").message)
        let transport = MockTransport()
        transport.stub(OptionOp.chain, .json(status: 503, #"{"detail":"Option prices are not available right now. Try again in a minute."}"#))
        do {
            _ = try await service(transport).chain("NVDA")
            Issue.record("expected a failure")
        } catch {
            #expect(OptionsService.message(for: error) == "Option prices are not available right now. Try again in a minute.")
        }
        transport.stub(OptionOp.chain, .json(status: 401, #"{"detail":"Authentication required."}"#))
        do {
            _ = try await service(transport).chain("NVDA")
            Issue.record("expected a failure")
        } catch {
            #expect(error == .notSignedIn)
        }
    }

    @Test("a plan is saved with its legs and prices, and reads back as the same plan")
    func saveAndRead() async throws {
        let plan = try draft(.coveredCall, contracts: 2).plan
        let transport = MockTransport()
        let saved = """
        {"id":"p-1","symbol":"NVDA","strategy":"covered_call","underlying_price":125.53,"as_of":"2026-11-20","created_at":"2026-11-20T21:30:00.120000",
         "legs":[{"kind":"stock","side":"buy","quantity":200,"price":125.53},
                 {"kind":"call","side":"sell","quantity":2,"price":9.48,"strike":135.0,"expiration":"2027-01-15","contract_id":"NVDA270115C00135000"}]}
        """
        transport.stub(OptionOp.save, .json(status: 201, saved))
        transport.stub(OptionOp.plans, .json(status: 200, "[\(saved)]"))
        let options = service(transport)
        let row = try await options.save(plan)
        #expect(row.id == "p-1" && row.plan == plan)

        let sent = try #require(transport.requests.first?.body.data(using: .utf8))
        let body = try #require(try JSONSerialization.jsonObject(with: sent) as? [String: Any])
        #expect(body["symbol"] as? String == "NVDA" && body["strategy"] as? String == "covered_call")
        #expect(body["as_of"] as? String == "2026-11-20" && body["underlying_price"] as? Double == 125.53)
        let legs = try #require(body["legs"] as? [[String: Any]])
        #expect(legs.count == 2 && legs[0]["kind"] as? String == "stock" && legs[0]["quantity"] as? Int == 200)
        #expect(legs[0]["strike"] == nil && legs[1]["contract_id"] as? String == "NVDA270115C00135000")
        #expect(legs[1]["side"] as? String == "sell" && legs[1]["price"] as? Double == 9.48)

        let listed = try await options.plans()
        #expect(listed.count == 1 && listed[0].plan?.figures.map(\.value) == plan.figures.map(\.value))
    }

    @Test("a saved plan of a kind this build does not know is not shown with wrong numbers")
    func unknownStrategy() async throws {
        let transport = MockTransport()
        transport.stub(OptionOp.plans, .json(status: 200, """
        [{"id":"p-9","symbol":"NVDA","strategy":"iron_condor","underlying_price":125.53,"as_of":"2026-11-20","created_at":"2026-11-20T21:30:00",
          "legs":[{"kind":"call","side":"sell","quantity":1,"price":9.48,"strike":135.0,"expiration":"2027-01-15","contract_id":"NVDA270115C00135000"}]}]
        """))
        let listed = try await service(transport).plans()
        #expect(listed.count == 1 && listed[0].plan == nil)
    }

    @Test("saving past the limit, and deleting")
    func limitAndDelete() async throws {
        let transport = MockTransport()
        transport.stub(OptionOp.save, .json(status: 409, #"{"detail":"You have 200 saved plans, the most there can be. Delete one to save another."}"#))
        let plan = try draft(.longCall).plan
        do {
            _ = try await service(transport).save(plan)
            Issue.record("expected a failure")
        } catch {
            #expect(error == .rejected("You have saved as many plans as an account can hold. Delete one to save another."))
        }
        transport.stub(OptionOp.delete, .json(status: 204, ""))
        try await service(transport).delete(id: "p-1")
        #expect(transport.requests.last?.path == "/api/options/plans/p-1")
        transport.stub(OptionOp.delete, .json(status: 404, #"{"detail":"Plan not found."}"#))
        await #expect(throws: APIFailure.self) { try await service(transport).delete(id: "p-2") }
    }

    @Test("the sample account can build, save, list and delete a plan")
    func demo() async throws {
        let options = AppSession.demo().options
        let chain = try await options.chain("NVDA")
        #expect(chain.symbol == "NVDA" && chain.expiration == "2027-01-15")
        let december = try await options.chain("nvda", expiration: "2026-12-18")
        #expect(december.expiration == "2026-12-18")
        do {
            _ = try await options.chain("AAPL")
            Issue.record("expected a failure")
        } catch {
            #expect(OptionsService.message(for: error) == "The sample account has options for NVDA only.")
        }
        let plan = try #require(OptionPlanDraft(strategy: .protectivePut, chain: chain)).plan
        let saved = try await options.save(plan)
        #expect(saved.plan == plan)
        #expect(try await options.plans().map(\.id) == [saved.id])
        try await options.delete(id: saved.id)
        #expect(try await options.plans().isEmpty)
    }
}
