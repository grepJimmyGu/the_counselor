import Foundation
import Testing

@testable import LivermoreKit

private let start = Date(timeIntervalSince1970: 1_700_000_000)

private func bars(_ count: Int, _ close: (Int) -> Double, range: Double = 0) -> [DailyClose] {
    (0..<count).map { day in
        let price = close(day)
        return DailyClose(
            date: start.addingTimeInterval(Double(day) * 86_400), close: price,
            high: price * (1 + range), low: price * (1 - range)
        )
    }
}

@Suite("TrendModel")
struct TrendModelTests {
    @Test("a price compounding at a steady rate is recovered exactly")
    func exactFit() throws {
        // 0.1% a day is e^(0.001 × 252) − 1 ≈ 28.7% a year.
        let model = try #require(TrendModel(closes: bars(200) { 100 * exp(0.001 * Double($0)) }, window: 120))
        #expect(model.window == 120)
        #expect(abs(model.annualRate - (exp(0.252) - 1)) < 1e-9)
        #expect(model.rSquared > 0.999999)
        #expect(abs(model.deviations) < 1e-6)
        #expect(model.points.count == 120)
        #expect(abs(model.points.last!.middle - 100 * exp(0.199)) < 1e-6)
        #expect(model.summary.contains("risen at a rate of 29% a year"))
        #expect(model.summary.contains("on that line"))
    }

    @Test("a fall, a noisy series and a price off its line are each described as such")
    func descriptions() throws {
        let falling = try #require(TrendModel(closes: bars(150) { 300 * exp(-0.002 * Double($0)) }, window: 120))
        #expect(falling.annualRate < -0.39 && falling.annualRate > -0.40)
        #expect(falling.summary.contains("fallen at a rate of 40% a year"))

        let choppy = try #require(TrendModel(closes: bars(150) { 100 + ($0 % 2 == 0 ? 3.0 : -3.0) }, window: 120))
        #expect(choppy.rSquared < 0.05)
        #expect(choppy.summary.contains("little steady direction"))

        // A small rate keeps its decimal, so the sentence agrees with the
        // tile beside it: -2.5% a year must not be written as "2%".
        let slow = try #require(TrendModel(closes: bars(150) { 100 * exp(-0.0001 * Double($0)) }, window: 120))
        #expect(slow.summary.contains("fallen at a rate of 2.5% a year"))

        // A steady climb with a sharp drop on the last day.
        let dropped = try #require(TrendModel(closes: bars(120) { day in
            100 * exp(0.001 * Double(day)) * (day == 119 ? 0.9 : (day % 2 == 0 ? 1.002 : 0.998))
        }, window: 120))
        #expect(dropped.deviations < -3)
        #expect(dropped.summary.contains("standard deviations below that line"))
        // The band brackets the line.
        #expect(dropped.points.allSatisfy { $0.lower < $0.middle && $0.middle < $0.upper })
    }

    @Test("too little history gives no model")
    func tooShort() {
        #expect(TrendModel(closes: bars(10) { _ in 5 }, window: 120) == nil)
        // Fewer bars than the window, but enough to fit: uses what there is.
        #expect(TrendModel(closes: bars(60) { 50 + Double($0) }, window: 120)?.window == 60)
    }
}

@Suite("PriceLevels")
struct PriceLevelsTests {
    @Test("levels are sorted, measured from the price, and split above and below")
    func levels() throws {
        // Up for 200 days to 300, then down to 250.
        let closes = bars(260, { $0 < 200 ? 100 + Double($0) : 300 - Double($0 - 200) * (50.0 / 59) }, range: 0.01)
        let levels = try #require(PriceLevels(closes: closes))
        #expect(abs(levels.price - 250) < 0.01)
        #expect(levels.levels.map(\.price) == levels.levels.map(\.price).sorted(by: >))
        let high = try #require(levels.levels.first { $0.name.contains("52-week high") })
        #expect(abs(high.price - 299 * 1.01) < 0.5 || abs(high.price - 300 * 1.01) < 0.5)
        #expect(high.isAbove)
        #expect(levels.nearestAbove != nil && levels.nearestBelow != nil)
        #expect(levels.nearestAbove!.price > levels.price && levels.nearestBelow!.price < levels.price)
        // A 1% band either side of a slowly moving close: the daily range is about 2%.
        #expect(levels.averageRangeShare > 0.018 && levels.averageRangeShare < 0.03)
    }

    @Test("with a live price, the levels are measured from it rather than the last close")
    func livePrice() throws {
        let closes = bars(260, { $0 < 200 ? 100 + Double($0) : 300 - Double($0 - 200) * (50.0 / 59) }, range: 0.01)
        let atClose = try #require(PriceLevels(closes: closes))
        let live = try #require(PriceLevels(closes: closes, price: 240))
        #expect(live.price == 240)
        let high = try #require(live.levels.first { $0.name.contains("52-week high") })
        #expect(abs(high.distance - (high.price / 240 - 1)) < 1e-12)
        // The levels themselves do not move; only the distances do.
        #expect(Set(live.levels.map(\.price)).isSuperset(of: atClose.levels.filter { $0.name.contains("average") }.map(\.price)))
        // A missing or nonsensical live price falls back to the close.
        #expect(PriceLevels(closes: closes, price: 0)?.price == atClose.price)
    }

    @Test("two names for the same price are one level")
    func merged() throws {
        // A steady decline: the 20-day low is the 52-week low.
        let levels = try #require(PriceLevels(closes: bars(260, { 500 - Double($0) }, range: 0.005)))
        #expect(levels.levels.filter { $0.name.contains("52-week low") }.count == 1)
        let names = levels.levels.map(\.name)
        #expect(Set(names).count == names.count)
    }

    @Test("a plan sized to the stock: stop two typical days away, target twice that")
    func sizedPlan() throws {
        let levels = try #require(PriceLevels(closes: bars(100, { _ in 100 }, range: 0.02)))
        let plan = BracketPlan.sized(to: levels)
        #expect(abs(plan.stop - 0.08) < 0.006)
        #expect(abs(plan.target - plan.stop * 2) < 1e-9)
        #expect(abs(plan.breakevenWinRate - 1.0 / 3) < 1e-9)
        // With nothing known, a 4% stop.
        #expect(BracketPlan.sized(to: nil).stop == 0.04)
    }
}

@Suite("BracketTest")
struct BracketTestTests {
    @Test("in a steady climb every entry reaches its target")
    func climb() throws {
        let outcome = try #require(BracketTest.run(
            closes: bars(600) { 100 * exp(0.004 * Double($0)) }, plan: BracketPlan(stop: 0.05, target: 0.10, maxDays: 60)
        ))
        #expect(outcome.all.entered == outcome.all.tried)
        #expect(outcome.all.targetRate == 1)
        #expect(outcome.all.stopped == 0 && outcome.all.timedOut == 0)
        #expect(abs(outcome.all.averageReturn - 0.10) < 1e-9)
        // 10% at 0.4% a day takes 24 days.
        #expect(outcome.all.medianDays == 24)
    }

    @Test("in a steady fall every entry is stopped out")
    func fall() throws {
        let outcome = try #require(BracketTest.run(
            closes: bars(600) { 1000 * exp(-0.004 * Double($0)) }, plan: BracketPlan(stop: 0.05, target: 0.10)
        ))
        #expect(outcome.all.stopRate == 1)
        #expect(abs(outcome.all.averageReturn + 0.05) < 1e-9)
    }

    @Test("a flat price times out with no gain or loss")
    func flat() throws {
        let outcome = try #require(BracketTest.run(closes: bars(400) { _ in 50 }, plan: BracketPlan(stop: 0.05, target: 0.10, maxDays: 30)))
        #expect(outcome.all.timeoutRate == 1)
        #expect(outcome.all.averageReturn == 0)
        #expect(outcome.all.medianDays == 30)
    }

    @Test("a day that touches both the stop and the target counts as stopped")
    func conservative() throws {
        // Flat closes, but every day ranges 20% either side.
        let outcome = try #require(BracketTest.run(
            closes: bars(400, { _ in 100 }, range: 0.2), plan: BracketPlan(stop: 0.05, target: 0.10)
        ))
        #expect(outcome.all.stopRate == 1)
        #expect(outcome.all.reachedTarget == 0)
    }

    @Test("a bid below the close fills only if the price comes down to it, and at the bid")
    func limitEntry() throws {
        // Never dips: nothing fills.
        let rising = try #require(BracketTest.run(
            closes: bars(400) { 100 + Double($0) }, plan: BracketPlan(entryDiscount: 0.03, stop: 0.05, target: 0.10)
        ))
        #expect(rising.all.entered == 0)
        #expect(rising.all.fillRate == 0)
        #expect(rising.all.tried > 0)

        // Daily lows 4% under the close: a 3% bid fills the next day.
        let dipping = try #require(BracketTest.run(
            closes: bars(400, { _ in 100 }, range: 0.04), plan: BracketPlan(entryDiscount: 0.03, stop: 0.10, target: 0.02, maxDays: 20)
        ))
        #expect(dipping.all.fillRate == 1)
        // Entered at 97; a 2% target is 98.94, inside the next day's high of 104.
        #expect(dipping.all.targetRate == 1)
        #expect(abs(dipping.all.averageReturn - 0.02) < 1e-9)
    }

    @Test("only days with the full waiting period after them are tried")
    func noTruncatedTrades() throws {
        let plan = BracketPlan(stop: 0.05, target: 0.10, maxDays: 60, fillDays: 10)
        let closes = bars(500) { _ in 50 }
        let outcome = try #require(BracketTest.run(closes: closes, plan: plan))
        #expect(outcome.all.tried == 500 - 60 - 10)
        #expect(outcome.all.to == closes[500 - 1 - 60 - 10].date)
        #expect(BracketTest.run(closes: bars(100) { _ in 50 }, plan: plan) == nil)
        #expect(BracketTest.run(closes: closes, plan: BracketPlan(stop: 0, target: 0.1)) == nil)
    }

    @Test("days like today are counted separately, and only when there are enough of them")
    func similarDays() throws {
        // Rises for 600 days, then falls for 300: today is below the 200-day average.
        let closes = bars(900) { $0 < 600 ? 100 * exp(0.002 * Double($0)) : 100 * exp(1.2) * exp(-0.003 * Double($0 - 600)) }
        let outcome = try #require(BracketTest.run(closes: closes, plan: BracketPlan(stop: 0.05, target: 0.10)))
        let similar = try #require(outcome.similar)
        #expect(outcome.similarity == "days when the price was below its 200-day average, as it is now")
        #expect(similar.tried < outcome.all.tried)
        // Entries made below the average were all in the decline.
        #expect(similar.stopRate > outcome.all.stopRate)
        #expect(similar.stopRate > 0.9)
    }
}

@Suite("filing analysis decoding")
@MainActor
struct FilingAnalysisTests {
    private func fixture() throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("Fixtures/filings-nvda.json")
        return try String(contentsOf: url, encoding: .utf8)
    }

    private func load() async throws -> FilingAnalysis {
        let transport = MockTransport()
        let session = AppSession(serverURL: URL(string: "https://api.test")!, store: InMemorySessionStore(), transport: transport)
        transport.stub("get_company_filings_api_company__symbol__filings_get", .json(status: 200, try fixture()))
        return try await session.research.filings("NVDA")
    }

    @Test("the backend's real response for NVIDIA decodes, figures intact")
    func decodes() async throws {
        let analysis = try await load()
        #expect(analysis.latest.label == "Q2 FY2027")
        #expect(analysis.latest.form == "10-Q")
        #expect(analysis.latest.shortLabel == "Q2 '27")
        #expect(analysis.quarters.count == 9)
        #expect(analysis.latest.value("revenue") == 96_221_000_000)
        #expect(analysis.latest.value("receivables") == 63_059_000_000)
        #expect(analysis.latest.filingUrl?.hasPrefix("https://www.sec.gov/Archives/edgar/data/1045810/") == true)
        #expect(analysis.findings.first?.severity == "watch")
        #expect(analysis.metricGroups.map(\.name) == ["Growth", "Profitability", "Cash", "Balance sheet", "Shareholders"])
    }

    @Test("a metric's series comes from the quarters, and a missing quarter is nil, not zero")
    func series() async throws {
        let analysis = try await load()
        let revenue = analysis.series("revenue")
        #expect(revenue.count == 9 && revenue.last == 96_221_000_000)
        // Year-over-year growth needs a year of history: the first four are absent.
        let growth = analysis.series("revenue_growth_yoy")
        #expect(growth.prefix(4).allSatisfy { $0 == nil })
        #expect(growth.last! != nil)
    }

    @Test("a row shows the range note in a few words, and passes any other note through")
    func shortNote() async throws {
        let analysis = try await load()
        let inventory = try #require(analysis.metric("inventory"))
        #expect(inventory.note == "Highest of the last 9 quarters.")
        #expect(inventory.shortNote == "9-quarter high")
        let shares = try #require(analysis.metric("diluted_shares"))
        #expect(shares.shortNote == "9-quarter low")
        var other = inventory
        other.note = "Restated in the latest filing."
        #expect(other.shortNote == "Restated in the latest filing.")
        other.note = nil
        #expect(other.shortNote == nil)
    }

    @Test("each unit formats as a person would write it, and changes carry their kind")
    func formatting() async throws {
        let analysis = try await load()
        let revenue = try #require(analysis.metric("revenue"))
        #expect(revenue.formatted(revenue.latest) == "$96.2B")
        #expect(revenue.formattedChange(revenue.changeQoq) == "+17.9%")
        #expect(revenue.isImprovement(revenue.changeQoq) == true)

        let margin = try #require(analysis.metric("gross_margin"))
        #expect(margin.formatted(margin.latest) == "75.0%")
        #expect(margin.formattedChange(margin.changeYoy) == "+2.6 pts")

        let dso = try #require(analysis.metric("days_sales_outstanding"))
        #expect(dso.formatted(dso.latest) == "60 days")
        #expect(dso.formattedChange(dso.changeQoq) == "+14 days")
        // More days uncollected is the wrong direction.
        #expect(dso.isImprovement(dso.changeQoq) == false)

        let capex = try #require(analysis.metric("capital_expenditure"))
        #expect(capex.isImprovement(capex.changeYoy) == nil)
        #expect(revenue.formatted(nil) == "—")
        #expect(try #require(analysis.metric("eps_diluted")).formatted(2.46) == "$2.46")
        #expect(try #require(analysis.metric("diluted_shares")).formatted(24_285_000_000) == "24.29B")
    }

    @Test("the sample account serves NVIDIA's filing analysis from its bundled copy")
    func demo() async throws {
        let analysis = try await AppSession.demo().research.filings("nvda")
        #expect(analysis.symbol == "NVDA")
        #expect(analysis.latest.value("revenue") == 96_221_000_000)
    }

    @Test("a company with no quarterly filings is unavailable, with the backend's reason")
    func unavailable() async throws {
        let transport = MockTransport()
        let session = AppSession(serverURL: URL(string: "https://api.test")!, store: InMemorySessionStore(), transport: transport)
        transport.stub("get_company_filings_api_company__symbol__filings_get",
                       .json(status: 404, #"{"detail":"TSM has no quarterly 10-Q / 10-K revenue data in the SEC's XBRL records."}"#))
        await #expect(throws: APIFailure.unavailable("TSM has no quarterly 10-Q / 10-K revenue data in the SEC's XBRL records.")) {
            try await session.research.filings("TSM")
        }
    }
}

@Suite("Test an entry and exit: the + and − buttons")
struct BracketPlanMoveTests {
    /// The prices the card shows for a plan, from the price now.
    private func prices(_ plan: BracketPlan, price: Double = 278.02) -> (entry: Double, stop: Double, target: Double) {
        let entry = price * (1 - plan.entryDiscount)
        return (entry, entry * (1 - plan.stop), entry * (1 + plan.target))
    }

    @Test("regression: + raises the price shown on every row, and − lowers it")
    func plusRaisesEveryPrice() {
        // Jimmy, 2026-11-24: + on "Buy at" and "Stop" lowered the price,
        // because it added to the distance below.
        let start = BracketPlan(entryDiscount: 0.05, stop: 0.09, target: 0.18)
        let before = prices(start)

        var plan = start
        plan.moveEntry(up: true)
        #expect(prices(plan).entry > before.entry)
        plan = start
        plan.moveEntry(up: false)
        #expect(prices(plan).entry < before.entry)

        plan = start
        plan.moveStop(up: true)
        #expect(prices(plan).stop > before.stop)
        plan = start
        plan.moveStop(up: false)
        #expect(prices(plan).stop < before.stop)

        plan = start
        plan.moveTarget(up: true)
        #expect(prices(plan).target > before.target)
        plan = start
        plan.moveTarget(up: false)
        #expect(prices(plan).target < before.target)
    }

    @Test("a price at its limit cannot move further, and its button says so")
    func limits() {
        // Buying at the price now: the buy price cannot go above it.
        var plan = BracketPlan(entryDiscount: 0, stop: 0.005, target: 1.00)
        #expect(!plan.canMoveEntry(up: true) && plan.canMoveEntry(up: false))
        #expect(!plan.canMoveStop(up: true) && plan.canMoveStop(up: false))
        #expect(!plan.canMoveTarget(up: true) && plan.canMoveTarget(up: false))
        plan.moveEntry(up: true)
        plan.moveStop(up: true)
        plan.moveTarget(up: true)
        #expect(plan == BracketPlan(entryDiscount: 0, stop: 0.005, target: 1.00))

        plan = BracketPlan(entryDiscount: 0.20, stop: 0.40, target: 0.01)
        #expect(!plan.canMoveEntry(up: false) && !plan.canMoveStop(up: false) && !plan.canMoveTarget(up: false))
    }

    @Test("steps stay on whole numbers: 1% for the buy price and target, half a percent for the stop")
    func steps() {
        var plan = BracketPlan(entryDiscount: 0.03, stop: 0.09, target: 0.18)
        for _ in 0..<3 { plan.moveEntry(up: true) }
        plan.moveStop(up: true)
        plan.moveTarget(up: true)
        #expect(plan.entryDiscount == 0)
        #expect(plan.stop == 0.085)
        #expect(plan.target == 0.19)
    }
}
