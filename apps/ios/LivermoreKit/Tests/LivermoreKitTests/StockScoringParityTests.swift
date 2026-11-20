import Foundation
import Testing

@testable import LivermoreKit

/// The company scores exist twice: `scoring.ts` on the web and
/// `StockScoring.swift` here. This replays cases produced by the TypeScript
/// implementation (`scripts/gen_scoring_golden.mjs`), so the two cannot drift
/// apart without this failing.
@Suite("StockScoring parity with the web")
struct StockScoringParityTests {
    struct Golden: Decodable {
        struct Case: Decodable {
            struct Expected: Decodable {
                let health: Int
                let valuation: Int
                let trend: Int
                let overall: Int
                let label: String
                let status: [String]
            }
            let input: StockMetrics
            let expected: Expected
        }
        let cases: [Case]
    }

    private static func load() throws -> Golden {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("Fixtures/scoring-golden.json")
        return try JSONDecoder().decode(Golden.self, from: Data(contentsOf: url))
    }

    @Test("every generated case scores the same in Swift as in TypeScript")
    func matchesTypeScript() throws {
        let golden = try Self.load()
        #expect(golden.cases.count >= 400)

        var mismatches: [String] = []
        for (index, item) in golden.cases.enumerated() {
            let health = StockScoring.health(item.input)
            let valuation = StockScoring.valuation(item.input)
            let trend = StockScoring.trend(item.input)
            let overall = StockScoring.overall(health: health, valuation: valuation, trend: trend)
            let got = "\(health)/\(valuation)/\(trend)/\(overall)/\(StockScoring.label(forOverall: overall))/"
                + [health, valuation, trend].map { StockScoring.status($0).rawValue }.joined(separator: ",")
            let e = item.expected
            let want = "\(e.health)/\(e.valuation)/\(e.trend)/\(e.overall)/\(e.label)/" + e.status.joined(separator: ",")
            if got != want { mismatches.append("case \(index): swift \(got) vs ts \(want)") }
        }
        #expect(mismatches.prefix(5) == [])
    }

    @Test("with no data at all, every score is the neutral 50")
    func neutralWhenEmpty() {
        let empty = StockMetrics()
        #expect(StockScoring.health(empty) == 50)
        #expect(StockScoring.valuation(empty) == 50)
        #expect(StockScoring.trend(empty) == 50)
    }
}
