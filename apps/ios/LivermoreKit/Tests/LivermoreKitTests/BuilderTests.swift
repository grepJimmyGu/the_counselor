import Foundation
import LivermoreAPI
import Testing

@testable import LivermoreKit

private let server = URL(string: "https://api.test")!

private enum Op {
    static let run = "run_backtest_api_backtest_run_post"
    static let anonymousRun = "anonymous_backtest_run_api_anonymous_backtest_run_post"
    static let save = "create_saved_strategy_api_saved_strategies_post"
}

private func fixture(_ name: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("Fixtures/\(name)")
    return try String(contentsOf: url, encoding: .utf8)
}

@Suite("template catalogue")
struct TemplateCatalogTests {
    @Test("every exported template decodes, strategy included")
    func decodes() {
        // An empty list here means templates.json failed to decode against the
        // generated StrategyJSON type — one bad field drops the whole file.
        #expect(TemplateCatalog.all.count >= 10)
        #expect(Set(TemplateCatalog.all.map(\.id)).count == TemplateCatalog.all.count)
    }

    @Test("runnable templates are the ready and proxy ones, and can each run as shipped")
    func runnable() {
        let runnable = TemplateCatalog.runnable
        #expect(runnable.count >= 5)
        #expect(runnable.allSatisfy { $0.availability == "ready" || $0.availability == "proxy" })
        #expect(runnable.allSatisfy { $0.comingSoon != true })
        // Its own default tickers must satisfy its own minimum.
        #expect(runnable.filter { $0.defaultTickers.count < $0.minimumTickers }.map(\.id) == [])
    }
}

@Suite("StrategyBuilder")
struct StrategyBuilderTests {
    private var trend: StrategyTemplate {
        TemplateCatalog.all.first { $0.id == "trend-following" }!
    }

    private var today: Date {
        ISO8601DateFormatter().date(from: "2026-11-17T15:00:00Z")!
    }

    @Test("typed tickers are split, upper-cased and de-duplicated")
    func parsesTickers() {
        #expect(StrategyBuilder.tickers(from: " aapl, msft  nvda,AAPL\n") == ["AAPL", "MSFT", "NVDA"])
        #expect(StrategyBuilder.tickers(from: "  ,  ") == [])
    }

    @Test("a template keeps its rules and takes the chosen tickers, dates and name")
    func buildsFromTemplate() {
        let built = StrategyBuilder.strategy(from: trend, tickers: ["NVDA"], range: .threeYears, today: today)

        #expect(built.universe == ["NVDA"])
        #expect(built.strategyName == "Trend Following — NVDA")
        #expect(built.startDate == "2023-11-17")
        #expect(built.endDate == "2026-11-17")
        // Everything that defines the strategy is the template's own.
        #expect(built.strategyType == trend.strategy.strategyType)
        #expect(built.rules == trend.strategy.rules)
        #expect(built.riskManagement == trend.strategy.riskManagement)
        #expect(built.positionSizing == trend.strategy.positionSizing)
        #expect(built.benchmark == trend.strategy.benchmark)
    }

    @Test("with no tickers typed, the template's defaults are used")
    func fallsBackToDefaults() {
        let built = StrategyBuilder.strategy(from: trend, tickers: [], range: .fiveYears, today: today)
        #expect(built.universe == trend.defaultTickers)
        #expect(built.startDate == "2021-11-17")
    }

    @Test("long ticker lists are abbreviated in the name")
    func namesLongLists() {
        let name = StrategyBuilder.name(for: trend, tickers: ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"])
        #expect(name == "Trend Following — AAPL, MSFT +3")
    }
}

@MainActor
@Suite("BacktestService")
struct BacktestServiceTests {
    private func make(signedIn: Bool) -> (BacktestService, MockTransport) {
        let transport = MockTransport()
        let store = InMemorySessionStore(signedIn ? DemoData.session : nil)
        let session = AppSession(serverURL: server, store: store, transport: transport)
        return (session.backtests, transport)
    }

    private var strategy: StrategyJSON {
        StrategyBuilder.strategy(
            from: TemplateCatalog.all.first { $0.id == "trend-following" }!, tickers: ["AAPL"], range: .threeYears
        )
    }

    @Test("a real production result decodes")
    func decodesRealResult() async throws {
        let (service, transport) = make(signedIn: true)
        // Captured from POST /api/anonymous/backtest/run, curves thinned.
        transport.stub(Op.run, .json(status: 200, try fixture("backtest-result.json")))

        let result = try await service.run(strategy, templateID: "trend-following", signedIn: true)

        #expect(result.metrics.numberOfTrades == 13)
        #expect(result.equityCurve.first?.value == 10000)
        #expect(result.tradeLog.count == 13)
        #expect(result.strategyJson.universe == ["AAPL"])
    }

    @Test("signed in, the run is authorised and marked as a template run")
    func signedInRun() async throws {
        let (service, transport) = make(signedIn: true)
        transport.stub(Op.run, .json(status: 200, try fixture("backtest-result.json")))

        _ = try await service.run(strategy, templateID: "trend-following", signedIn: true)

        let sent = try #require(transport.requests.last)
        #expect(sent.operationID == Op.run)
        #expect(sent.authorization == "Bearer demo-token")
        let body = try #require(try JSONSerialization.jsonObject(with: Data(sent.body.utf8)) as? [String: Any])
        #expect(body["template_id"] as? String == "trend-following")
        let sentStrategy = try #require(body["strategy_json"] as? [String: Any])
        #expect(sentStrategy["universe"] as? [String] == ["AAPL"])
        #expect(sentStrategy["strategy_type"] as? String == "breakout")
    }

    @Test("signed out, the anonymous endpoint is used")
    func signedOutRun() async throws {
        let (service, transport) = make(signedIn: false)
        transport.stub(Op.anonymousRun, .json(status: 200, try fixture("backtest-result.json")))

        _ = try await service.run(strategy, templateID: "trend-following", signedIn: false)

        #expect(transport.requests.last?.operationID == Op.anonymousRun)
        #expect(transport.requests.last?.authorization == nil)
    }

    @Test("a used-up allowance and a bad ticker are reported in the backend's own words")
    func failures() async {
        let (service, transport) = make(signedIn: false)

        transport.stub(Op.anonymousRun, .json(status: 402, #"{"detail":{"entitlement":{"code":"anonymous_runs_exhausted","detail":"Sign up to run more backtests."}}}"#))
        await #expect(throws: APIFailure.upgradeRequired("Sign up to run more backtests.")) {
            try await service.run(strategy, templateID: "trend-following", signedIn: false)
        }

        transport.stub(Op.anonymousRun, .json(status: 400, #"{"detail":"Unknown or unsupported ticker(s): ZZZZ. Please check the symbols and try again."}"#))
        await #expect(throws: APIFailure.rejected("Unknown or unsupported ticker(s): ZZZZ. Please check the symbols and try again.")) {
            try await service.run(strategy, templateID: "trend-following", signedIn: false)
        }
    }

    @Test("saving sends the strategy and links the backtest")
    func saves() async throws {
        let (service, transport) = make(signedIn: true)
        transport.stub(Op.save, .json(status: 201, """
        {"id":"s-new","user_id":"demo-user","title":"Trend Following — AAPL","is_public":false,
         "created_at":"2026-11-17T15:00:00Z","updated_at":"2026-11-17T15:00:00Z","backtest_record_id":"bt-1",
         "strategy_json":{"strategy_type":"breakout","universe":["AAPL"]}}
        """))

        let saved = try await service.save(title: "Trend Following — AAPL", strategy: strategy, backtestID: "bt-1")

        #expect(saved.id == "s-new")
        let body = try #require(try JSONSerialization.jsonObject(with: Data(transport.requests.last!.body.utf8)) as? [String: Any])
        #expect(body["title"] as? String == "Trend Following — AAPL")
        #expect(body["backtest_record_id"] as? String == "bt-1")
        #expect(body["is_public"] as? Bool == false)
        let sentStrategy = try #require(body["strategy_json"] as? [String: Any])
        #expect((sentStrategy["rules"] as? [[String: Any]])?.first?["entry_window"] as? Int == 20)
    }
}
