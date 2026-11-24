import Foundation
import Testing

@testable import LivermoreKit

private let start = Date(timeIntervalSince1970: 1_700_000_000)

/// `count` daily closes produced by `price(dayIndex)`.
private func series(_ count: Int, _ price: (Int) -> Double) -> [DailyClose] {
    (0..<count).map { DailyClose(date: start.addingTimeInterval(Double($0) * 86_400), close: price($0)) }
}

private func signal(_ read: TechnicalRead, _ id: String) -> TechnicalSignal? {
    read.signals.first { $0.id == id }
}

@Suite("TechnicalRead")
struct TechnicalReadTests {
    @Test("a steady climb reads as an uptrend on every signal")
    func uptrend() throws {
        let rising = series(300) { 100 * pow(1.002, Double($0)) }
        let flatMarket = series(300) { _ in 400 }
        let read = try #require(TechnicalRead(closes: rising, benchmark: flatMarket))

        #expect(read.trend == .up)
        #expect(read.signals.map(\.id) == ["trend200", "trend50", "cross", "momentum", "relative", "range"])
        #expect(read.signals.allSatisfy { $0.lean == .up })
        #expect(read.upCount == 6 && read.downCount == 0)
        #expect(read.rangePosition == 1)
        #expect(read.fromHigh == 0)
        // Every day up: the index is pinned at 100, which is overbought.
        #expect(read.rsi == 100)
        #expect(read.stretch == .overbought)
        #expect(read.headline == "Uptrend, overbought")
        #expect(signal(read, "cross")?.reading == "The 50-day average is above the 200-day, and has been for at least three months.")
    }

    @Test("a steady fall reads as a downtrend, oversold")
    func downtrend() throws {
        let falling = series(300) { 300 * pow(0.998, Double($0)) }
        let read = try #require(TechnicalRead(closes: falling, benchmark: series(300) { _ in 400 }))
        #expect(read.trend == .down)
        #expect(read.signals.allSatisfy { $0.lean == .down })
        #expect(read.stretch == .oversold)
        #expect(read.headline == "Downtrend, oversold")
        #expect(read.rangePosition == 0)
        #expect(read.summary.contains("0 of 6 signals lean up, 6 lean down."))
        // The sentence states the reading; it does not say what tends to
        // happen next.
        #expect(read.summary.contains("the 14-day RSI is"))
        #expect(read.summary.contains("under the 30 line"))
        #expect(!read.summary.contains("common"))
        #expect(signal(read, "trend200")?.reading.contains("below its 200-day average") == true)
    }

    @Test("a flat price has no trend and normal stretch")
    func flat() throws {
        let read = try #require(TechnicalRead(closes: series(300) { 100 + ($0 % 2 == 0 ? 0.05 : -0.05) }))
        #expect(read.trend == .mixed)
        #expect(read.stretch == .normal)
        #expect(read.headline == "No clear trend")
        #expect(signal(read, "trend200")?.lean == .neutral)
        #expect(signal(read, "trend200")?.reading == "The price is right at its 200-day average.")
        #expect(signal(read, "momentum")?.lean == .neutral)
        // No benchmark supplied: that signal is absent, not guessed.
        #expect(signal(read, "relative") == nil)
    }

    @Test("a recent turn is dated: the averages crossed N days ago")
    func recentCross() throws {
        // A long decline, then a rally sharp enough to lift the 50-day
        // average through the 200-day near the end.
        let closes = series(330) { day in day < 250 ? 200 - Double(day) * 0.2 : 150 + Double(day - 250) * 1.6 }
        let read = try #require(TechnicalRead(closes: closes))
        let cross = try #require(signal(read, "cross"))
        #expect(cross.lean == .up)
        // The crossing is named only because it is recent.
        #expect(cross.reading.contains("a golden cross"))
        #expect(cross.reading.contains("trading day"))
    }

    @Test("beating a rising market counts; merely rising with it does not")
    func relativeStrength() throws {
        let stock = series(300) { 100 * pow(1.001, Double($0)) }
        let sameMarket = series(300) { 400 * pow(1.001, Double($0)) }
        let weakMarket = series(300) { 400 * pow(1.0002, Double($0)) }
        #expect(signal(try #require(TechnicalRead(closes: stock, benchmark: sameMarket)), "relative")?.lean == .neutral)
        #expect(signal(try #require(TechnicalRead(closes: stock, benchmark: weakMarket)), "relative")?.lean == .up)
        let reading = signal(try #require(TechnicalRead(closes: stock, benchmark: weakMarket)), "relative")?.reading ?? ""
        #expect(reading.contains("points over three months"))
        #expect(!reading.contains("% points"))
    }

    @Test("short histories drop the signals they can't support")
    func shortHistory() throws {
        #expect(TechnicalRead(closes: series(49) { _ in 10 }) == nil)
        let young = try #require(TechnicalRead(closes: series(80) { 50 + Double($0) * 0.5 }))
        #expect(young.average200 == nil)
        #expect(young.signals.map(\.id) == ["trend50", "momentum"])
        #expect(young.average50 != nil)
    }

    // Regression: with exactly 200 closes there is a 200-day average but no
    // earlier one to compare it with, and the look-back range was 1...0.
    @Test("exactly 200 closes has a cross signal and does not crash looking back")
    func exactlyTwoHundred() throws {
        let read = try #require(TechnicalRead(closes: series(200) { 100 + Double($0) * 0.3 }))
        let cross = try #require(signal(read, "cross"))
        #expect(cross.lean == .up)
        #expect(cross.reading == "The 50-day average is above the 200-day.")
        _ = try #require(TechnicalRead(closes: series(201) { 100 + Double($0) * 0.3 }))
    }

    @Test("RSI matches a hand-worked example")
    func rsi() throws {
        // Seven gains of 1 and seven losses of 1 over 14 changes: RS = 1.
        var prices = [100.0]
        for step in 0..<14 { prices.append(prices.last! + (step % 2 == 0 ? 1 : -1)) }
        #expect(TechnicalRead.rsi(prices, period: 14) == 50)
        #expect(TechnicalRead.rsi([1, 2, 3], period: 14) == nil)
        // All gains: 100. No movement: 50.
        #expect(TechnicalRead.rsi((0...20).map { 10 + Double($0) }, period: 14) == 100)
        #expect(TechnicalRead.rsi(Array(repeating: 5.0, count: 20), period: 14) == 50)
    }

    @Test("volatility is annualised from the last 20 days")
    func volatility() throws {
        // Alternating ±1% log moves: daily sd ≈ 1.03%, ≈ 16% a year.
        let closes = series(100) { 100 * exp($0 % 2 == 0 ? 0.005 : -0.005) }
        let vol = try #require(TechnicalRead(closes: closes)?.volatility)
        #expect(vol > 0.14 && vol < 0.18)
    }
}

@Suite("StrategyAdvisor")
struct StrategyAdvisorTests {
    private func read(_ price: (Int) -> Double) -> TechnicalRead? {
        TechnicalRead(closes: series(300, price), benchmark: series(300) { _ in 400 })
    }

    @Test("an uptrend leads with the trend rule; a washed-out downtrend with the reversion rule")
    func ordering() {
        let up = StrategyAdvisor.suggestions(for: read { 100 + Double($0) * 0.1 + ($0 % 3 == 0 ? -1.5 : 0) }, symbol: "aapl", peers: [])
        #expect(up.first?.template.id == "trend-following")
        #expect(up.first?.tickers == ["AAPL"])

        let down = StrategyAdvisor.suggestions(for: read { 300 * pow(0.998, Double($0)) }, symbol: "NVDA", peers: [])
        #expect(down.map(\.template.id) == ["bollinger-mean-reversion", "trend-following"])
        #expect(down[0].why.contains("oversold"))
        #expect(down[1].why.contains("in cash"))
    }

    @Test("with no read at all it still offers both approaches")
    func noRead() {
        let ideas = StrategyAdvisor.suggestions(for: nil, symbol: "AAPL", peers: [])
        #expect(Set(ideas.map(\.template.id)) == ["trend-following", "bollinger-mean-reversion"])
    }

    @Test("rivals make a group for the ranking strategy, without duplicates")
    func peers() throws {
        let ideas = StrategyAdvisor.suggestions(for: nil, symbol: "NVDA", peers: ["amd", "AVGO", "NVDA", "INTC", "QCOM", "MRVL"])
        let ranking = try #require(ideas.last)
        #expect(ranking.template.id == "cross-sectional-momentum")
        #expect(ranking.tickers == ["NVDA", "AMD", "AVGO", "INTC", "QCOM"])
        // One rival is not a group.
        #expect(StrategyAdvisor.suggestions(for: nil, symbol: "NVDA", peers: ["AMD"]).count == 2)
    }

    @Test("every suggestion names a strategy the app can actually run")
    func runnable() {
        let ids = Set(TemplateCatalog.runnable.map(\.id))
        for id in ["trend-following", "bollinger-mean-reversion", "cross-sectional-momentum"] {
            #expect(ids.contains(id), "\(id) is no longer runnable")
        }
    }
}
