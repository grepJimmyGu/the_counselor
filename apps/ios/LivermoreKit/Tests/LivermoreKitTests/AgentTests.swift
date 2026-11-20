import Foundation
import Testing

@testable import LivermoreKit

private let server = URL(string: "https://api.test")!

private enum AgentOp {
    static let profile = "get_profile_api_agent_profile_get"
    static let update = "update_profile_api_agent_profile_put"
    static let insights = "list_insights_api_agent_insights_get"
    static let dismiss = "dismiss_insight_api_agent_insights__insight_id__dismiss_post"
    static let scan = "scan_now_api_agent_scan_post"
}

private func profileJSON(watchlist: String = #"["AAPL","NVDA"]"#, enabled: Bool = false) -> String {
    #"{"enabled":\#(enabled),"watchlist":\#(watchlist),"move_alert_pct":4.0,"max_position_pct":25.0,"notes":"","last_scan_at":null,"chat_available":true}"#
}

private let concentration = """
{"id":"i-1","kind":"concentration","severity":"watch","symbol":"AAPL","title":"AAPL is 50% of your holdings, over your 25% limit","body":"Selling about $26,667 would bring it to 25%.","facts":{"weight_pct":50.0},"action":{"type":"review_order","symbol":"AAPL","side":"sell","units":66},"created_at":"2026-11-20T15:05:00","dismissed":false}
"""
private let move = """
{"id":"i-2","kind":"price_move","severity":"info","symbol":"NVDA","title":"NVDA is down 5.2% today","body":"NVDA is at $145.98.","facts":{},"action":{"type":"open_company","symbol":"NVDA"},"created_at":"2026-11-20T15:05:00","dismissed":false}
"""

@Suite("what the agent offers to open")
struct AgentActionTests {
    @Test("each kind of action is read from the backend's object")
    func kinds() {
        #expect(AgentAction(json: ["type": "open_company", "symbol": "NVDA"]) == .openCompany(symbol: "NVDA"))
        #expect(AgentAction(json: ["type": "open_actions"]) == .openActions)
        #expect(AgentAction(json: ["type": "review_order", "symbol": "AAPL", "side": "sell", "units": 66]) ==
            .reviewOrder(OrderSuggestion(symbol: "AAPL", side: .sell, units: 66)))
        #expect(AgentAction(json: ["type": "review_order", "symbol": "NVDA", "side": "buy", "amount_usd": 500.0, "reason": "You asked."]) ==
            .reviewOrder(OrderSuggestion(symbol: "NVDA", side: .buy, amountUSD: 500, reason: "You asked.")))
    }

    @Test("an action this build does not understand opens nothing")
    func unknown() {
        #expect(AgentAction(json: ["type": "place_order", "symbol": "AAPL"]) == nil)
        #expect(AgentAction(json: ["type": "review_order", "symbol": "AAPL", "side": "short", "units": 1]) == nil)
        // A draft with no size is not an order.
        #expect(AgentAction(json: ["type": "review_order", "symbol": "AAPL", "side": "sell"]) == nil)
        #expect(AgentAction(json: ["type": "open_company"]) == nil)
        #expect(AgentAction(json: [:]) == nil)
    }
}

@MainActor
@Suite("the agent's settings and findings")
struct AgentStoreTests {
    private func make() -> (AppSession, MockTransport) {
        let transport = MockTransport()
        let session = AppSession(
            serverURL: server, store: InMemorySessionStore(Fixture.saved),
            biometrics: InMemoryBiometricStore(), transport: transport
        )
        return (session, transport)
    }

    @Test("loading reads the settings and the findings, with what each offers to open")
    func load() async {
        let (session, transport) = make()
        transport.stub(AgentOp.profile, .json(status: 200, profileJSON()))
        transport.stub(AgentOp.insights, .json(status: 200, "[\(concentration),\(move)]"))

        await session.agent.load()

        #expect(session.agent.profile?.enabled == false)
        #expect(session.agent.insights.map(\.id) == ["i-1", "i-2"])
        #expect(session.agent.attentionCount == 1)
        #expect(session.agent.insights[0].suggestedAction ==
            .reviewOrder(OrderSuggestion(symbol: "AAPL", side: .sell, units: 66)))
        #expect(session.agent.insights[1].suggestedAction == .openCompany(symbol: "NVDA"))
        #expect(session.agent.failure == nil)
    }

    @Test("a check replaces the findings and keeps what it could not do")
    func check() async {
        let (session, transport) = make()
        transport.stub(AgentOp.scan, .json(status: 200, """
        {"checked_at":"2026-11-20T15:05:00","new_insights":1,"symbols_checked":2,"brokerage_linked":false,"notes":["No brokerage is linked, so holdings were not checked."],"insights":[\(move)]}
        """))
        await session.agent.check()
        #expect(session.agent.insights.map(\.id) == ["i-2"])
        #expect(session.agent.notes == ["No brokerage is linked, so holdings were not checked."])
        #expect(session.agent.lastChecked != nil)
        #expect(!session.agent.isChecking)
    }

    @Test("a dismissed finding goes at once and comes back if the backend refused")
    func dismiss() async throws {
        let (session, transport) = make()
        transport.stub(AgentOp.profile, .json(status: 200, profileJSON()))
        transport.stub(AgentOp.insights, .json(status: 200, "[\(concentration),\(move)]"))
        await session.agent.load()
        let first = try #require(session.agent.insights.first)

        transport.stub(AgentOp.dismiss, .json(status: 200, concentration))
        await session.agent.dismiss(first)
        #expect(session.agent.insights.map(\.id) == ["i-2"])

        let second = try #require(session.agent.insights.first)
        transport.stub(AgentOp.dismiss, .json(status: 503, "{}"))
        await session.agent.dismiss(second)
        #expect(session.agent.insights.map(\.id) == ["i-2"])
        #expect(session.agent.failure != nil)
    }

    @Test("the watchlist is sent only when it differs from what the backend has")
    func watchlist() async throws {
        let (session, transport) = make()
        transport.stub(AgentOp.profile, .json(status: 200, profileJSON()))
        transport.stub(AgentOp.insights, .json(status: 200, "[]"))
        await session.agent.load()
        let before = transport.requests.count

        await session.agent.syncWatchlist(["AAPL", "NVDA"])
        #expect(transport.requests.count == before)

        transport.stub(AgentOp.update, .json(status: 200, profileJSON(watchlist: #"["AAPL","NVDA","GOOGL"]"#)))
        await session.agent.syncWatchlist(["AAPL", "NVDA", "GOOGL"])
        let sent = try JSONSerialization.jsonObject(with: Data(transport.requests[before].body.utf8)) as? [String: Any]
        // Only the watchlist is sent, so no other setting can be changed by a sync.
        #expect(sent?.keys.sorted() == ["watchlist"])
        #expect(session.agent.profile?.watchlist == ["AAPL", "NVDA", "GOOGL"])
    }

    @Test("turning the agent on sends that one setting")
    func enable() async throws {
        let (session, transport) = make()
        transport.stub(AgentOp.update, .json(status: 200, profileJSON(enabled: true)))
        await session.agent.update(enabled: true)
        let sent = try JSONSerialization.jsonObject(with: Data(transport.requests[0].body.utf8)) as? [String: Any]
        #expect(sent?.keys.sorted() == ["enabled"])
        #expect(session.agent.profile?.enabled == true)
    }

    @Test("a session the backend no longer accepts signs the app out")
    func expired() async {
        let (session, transport) = make()
        transport.stub(AgentOp.profile, .json(status: 401, #"{"detail":"Invalid or expired session token."}"#))
        transport.stub(AgentOp.insights, .json(status: 401, #"{"detail":"Invalid or expired session token."}"#))
        await session.agent.load()
        #expect(!session.isSignedIn)
    }
}

@Suite("the agent's answer, as it streams")
struct AgentChatEventTests {
    @Test("each line of the stream becomes one event")
    func parse() {
        #expect(AgentChatEvent.parse(line: #"data: {"type":"token","text":"AAPL is "}"#) == .token("AAPL is "))
        #expect(AgentChatEvent.parse(line: #"data: {"type":"tool_call_start","call_id":"c1","name":"agent_overview","arguments":{}}"#) ==
            .toolStarted(name: "agent_overview"))
        #expect(AgentChatEvent.parse(line: #"data: {"type":"tool_result","call_id":"c1","name":"agent_overview"}"#) ==
            .toolFinished(name: "agent_overview", action: nil))
        #expect(AgentChatEvent.parse(line: #"data: {"type":"done","finish_reason":"stop"}"#) == .done)
        #expect(AgentChatEvent.parse(line: #"data: {"type":"error","message":"LLM disabled","fatal":true}"#) == .failed("LLM disabled"))
    }

    @Test("a drafted order rides on the tool's result")
    func draft() {
        let line = #"data: {"type":"tool_result","call_id":"c2","name":"agent_draft_order","client":{"type":"review_order","symbol":"AAPL","side":"sell","units":66.0,"reason":"Back to 25%."}}"#
        #expect(AgentChatEvent.parse(line: line) == .toolFinished(
            name: "agent_draft_order",
            action: .reviewOrder(OrderSuggestion(symbol: "AAPL", side: .sell, units: 66, reason: "Back to 25%."))
        ))
    }

    @Test("blank lines, other events and broken lines are skipped")
    func skipped() {
        #expect(AgentChatEvent.parse(line: "") == nil)
        #expect(AgentChatEvent.parse(line: #"data: {"type":"started","conversation_id":"x"}"#) == nil)
        #expect(AgentChatEvent.parse(line: #"data: {"type":"guardrail","action":"x"}"#) == nil)
        #expect(AgentChatEvent.parse(line: "data: {not json") == nil)
        #expect(AgentChatEvent.parse(line: #"data: {"type":"token","text":""}"#) == nil)
    }
}

@MainActor
@Suite("a conversation with the agent")
struct AgentConversationTests {
    private func service(lines: [String], status: Int = 200, log: RequestLog? = nil) -> AgentChatService {
        AgentChatService(serverURL: server, token: { "tok-1" }) { request in
            log?.add(request)
            let stream = AsyncThrowingStream<String, Error> { continuation in
                for line in lines { continuation.yield(line) }
                continuation.finish()
            }
            return (stream, status)
        }
    }

    @Test("the message is sent with the session, and the answer builds up as it arrives")
    func answer() async throws {
        let log = RequestLog()
        let conversation = AgentConversation(service: service(lines: [
            #"data: {"type":"started","conversation_id":"x"}"#, "",
            #"data: {"type":"tool_call_start","call_id":"c1","name":"agent_overview","arguments":{}}"#,
            #"data: {"type":"tool_result","call_id":"c1","name":"agent_overview"}"#,
            #"data: {"type":"token","text":"AAPL is 50% "}"#,
            #"data: {"type":"token","text":"of your holdings."}"#,
            #"data: {"type":"done","finish_reason":"stop"}"#,
        ], log: log))

        await conversation.send("  What needs my attention? ")

        #expect(conversation.messages.map(\.text) == ["What needs my attention?", "AAPL is 50% of your holdings."])
        #expect(conversation.messages[1].failure == nil)
        #expect(!conversation.isAnswering && conversation.activity == nil)
        let request = try #require(log.requests.first)
        #expect(request.url?.absoluteString == "https://api.test/api/agent/chat/\(conversation.id)/messages")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer tok-1")
        let body = try JSONSerialization.jsonObject(with: request.httpBody ?? Data()) as? [String: String]
        #expect(body == ["content": "What needs my attention?"])
    }

    @Test("an order the agent drafts is attached to its answer")
    func drafts() async {
        let conversation = AgentConversation(service: service(lines: [
            #"data: {"type":"tool_result","call_id":"c2","name":"agent_draft_order","client":{"type":"review_order","symbol":"AAPL","side":"sell","units":66}}"#,
            #"data: {"type":"token","text":"I have drafted it for you to review."}"#,
            #"data: {"type":"done","finish_reason":"stop"}"#,
        ]))
        await conversation.send("Trim AAPL to my limit")
        #expect(conversation.messages[1].drafts == [OrderSuggestion(symbol: "AAPL", side: .sell, units: 66)])
    }

    @Test("a refusal, a server without the agent, and a stream that just stops are each explained")
    func failures() async {
        let quota = AgentConversation(service: service(lines: [], status: 402))
        await quota.send("hi")
        #expect(quota.messages[1].failure == "You've used today's conversations on your plan. They reset tomorrow.")

        let behind = AgentConversation(service: service(lines: [], status: 404))
        await behind.send("hi")
        #expect(behind.messages[1].failure?.contains("server update") == true)

        let cut = AgentConversation(service: service(lines: [#"data: {"type":"token","text":"AAPL"}"#]))
        await cut.send("hi")
        #expect(cut.messages[1].text == "AAPL")
        #expect(cut.messages[1].failure == "The agent stopped before it finished. Try again.")

        let model = AgentConversation(service: service(lines: [#"data: {"type":"error","message":"No model is configured.","fatal":true}"#]))
        await model.send("hi")
        #expect(model.messages[1].failure == "No model is configured.")
    }

    @Test("an empty message is not sent")
    func empty() async {
        let log = RequestLog()
        let conversation = AgentConversation(service: service(lines: [], log: log))
        await conversation.send("   ")
        #expect(conversation.messages.isEmpty && log.requests.isEmpty)
    }
}
