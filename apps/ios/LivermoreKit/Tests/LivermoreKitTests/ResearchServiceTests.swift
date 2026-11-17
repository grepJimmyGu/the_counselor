import Foundation
import LivermoreAPI
import Testing

@testable import LivermoreKit

private let server = URL(string: "https://api.test")!

private enum Op {
    static let search = "search_symbols_api_symbols_search_get"
    static let overview = "get_company_overview_api_company__symbol__overview_get"
    static let sentiment = "get_sentiment_summary_api_sentiment__symbol__summary_get"
}

@MainActor
@Suite("ResearchService")
struct ResearchServiceTests {
    private func make() -> (ResearchService, MockTransport) {
        let transport = MockTransport()
        let session = AppSession(serverURL: server, store: InMemorySessionStore(), transport: transport)
        return (session.research, transport)
    }

    @Test("the US listing is ranked ahead of foreign lines the backend returns first")
    func ranksUSListingsFirst() async throws {
        let (research, transport) = make()
        // The order production returns for "AAPL".
        transport.stub(Op.search, .json(status: 200, """
        [{"symbol":"AAPL.TRT","name":"Apple CDR (CAD Hedged)","region":"Toronto"},
         {"symbol":"AAPL34.SAO","name":"Apple Inc","region":"Brazil/Sao Paolo"},
         {"symbol":"APLE","name":"Apple Hospitality REIT","region":null},
         {"symbol":"AAPL","name":"Apple Inc.","region":"United States"}]
        """))

        let symbols = try await research.search(" aapl ").map(\.symbol)

        #expect(symbols == ["AAPL", "APLE", "AAPL.TRT", "AAPL34.SAO"])
    }

    @Test("an empty query makes no request")
    func emptyQuerySkipsNetwork() async throws {
        let (research, transport) = make()
        #expect(try await research.search("   ").isEmpty)
        #expect(transport.requests.isEmpty)
    }

    @Test("a plan gate surfaces the backend's own explanation")
    func upgradeRequired() async {
        let (research, transport) = make()
        transport.stub(Op.overview, .json(status: 402, """
        {"detail":{"entitlement":{"code":"market_pulse_scope","detail":"SMCI is outside the S&P 500 coverage on your plan."}}}
        """))

        await #expect(throws: ResearchError.upgradeRequired("SMCI is outside the S&P 500 coverage on your plan.")) {
            try await research.overview("SMCI")
        }
    }

    @Test("a 404 keeps the backend's reason but shows the user a plain message")
    func unavailable() async {
        let (research, transport) = make()
        let leaked = "(psycopg.errors.StringDataRightTruncation) value too long for type character varying(8)"
        transport.stub(Op.overview, .json(status: 404, #"{"detail":"\#(leaked)"}"#))

        do {
            _ = try await research.overview("MSFT")
            Issue.record("expected a failure")
        } catch {
            #expect(error == .unavailable(leaked))
            // The route returns raw exception text as `detail`; it must never
            // reach the screen.
            #expect(!error.message.contains("psycopg"))
        }
    }

    @Test("server faults, dropped connections and unreadable bodies are three different errors")
    func distinguishesFailures() async {
        let (research, transport) = make()

        transport.stub(Op.overview, .json(status: 500, "{}"))
        await #expect(throws: ResearchError.server(status: 500)) { try await research.overview("AAPL") }

        transport.stub(Op.overview, .failure)
        await #expect(throws: ResearchError.network) { try await research.overview("AAPL") }

        // A 200 whose body is missing required fields is a schema mismatch,
        // not a connectivity problem.
        transport.stub(Op.overview, .json(status: 200, #"{"symbol":"AAPL"}"#))
        await #expect(throws: ResearchError.unreadable) { try await research.overview("AAPL") }
    }
}

@Suite("LenientDateTranscoder")
struct LenientDateTranscoderTests {
    @Test("reads every timestamp shape the backend sends", arguments: [
        "2026-11-17T04:14:09.273587Z",  // sentiment: microseconds
        "2026-11-17T04:14:09Z",
        "2026-11-17T04:14:09.273587",   // naive datetime, treated as UTC
        "2026-11-17T04:14:09",
        "2026-11-17T04:14:09+00:00",
    ])
    func decodes(_ text: String) throws {
        let date = try LenientDateTranscoder().decode(text)
        let expected = 1_794_888_849.0  // 2026-11-17 04:14:09 UTC
        #expect(abs(date.timeIntervalSince1970 - expected) < 1)
    }

    @Test("rejects text that is not a timestamp")
    func rejectsGarbage() {
        #expect(throws: DecodingError.self) { try LenientDateTranscoder().decode("yesterday") }
    }
}

@Suite("detail parsing")
struct DetailParsingTests {
    @Test("handles both of FastAPI's detail shapes")
    func shapes() {
        #expect(APIFailure.detail(in: Data(#"{"detail":"plain"}"#.utf8)) == "plain")
        #expect(APIFailure.detail(in: Data(#"{"detail":{"entitlement":{"detail":"gated"}}}"#.utf8)) == "gated")
        #expect(APIFailure.detail(in: Data("not json".utf8)) == nil)
    }
}
