#if DEBUG
import Foundation
import HTTPTypes
import OpenAPIRuntime
import OpenAPIURLSession

/// Sample responses for the signed-in endpoints, for debug builds only.
///
/// The Strategies screens need an account to show anything, which makes their
/// layout impossible to check without real credentials. Launching a debug
/// build with `-demo` signs in a made-up user and answers the account
/// endpoints from the fixtures below; everything else (research, quotes) still
/// goes to the real API. None of this is compiled into release builds.
///
/// The fixtures double as decoding tests: `StrategyServiceTests` runs them
/// through the generated client, so they cannot drift from the schema.
public enum DemoData {
    public static let session = StoredSession(
        token: "demo-token", userID: "demo-user", email: "demo@example.com", displayName: "Sample account"
    )

    public static let entitlements = """
    {"tier":"strategist","status":"active","week_start":"2026-11-16","template_runs_unlimited":false,"universe_size_max_custom":50,"history_window_years_custom":10,"asset_classes":["equities"],"robustness_tests":[],"market_pulse_ticker_scope":"top_250","business_model_section":"full","commodity_framework":false,"saved_strategies_max":10,"saved_strategies_always_public":false}
    """

    public static let strategies = """
    [{"id":"s-trend","user_id":"demo-user","title":"NVDA 200-day trend","is_public":false,
      "created_at":"2026-10-02T14:03:11.120000Z","updated_at":"2026-11-10T09:00:00Z",
      "strategy_json":{"strategy_type":"trend_following","universe":["NVDA"],"bar_resolution":"daily",
        "risk_management":{"exit_ladder":[{"type":"stop","trigger_pct":-0.08},{"type":"target","trigger_pct":0.15}]}}},
     {"id":"s-rotation","user_id":"demo-user","title":"Magnificent Seven momentum rotation","is_public":true,
      "created_at":"2026-09-18T20:41:00Z","updated_at":"2026-09-18T20:41:00Z",
      "strategy_json":{"strategy_type":"momentum_rotation","universe":["AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA"],
        "risk_management":{"exit_ladder":[]}}},
     {"id":"s-intraday","user_id":"demo-user","title":"AAPL opening-range breakout","is_public":false,
      "created_at":"2026-11-05T15:30:00Z","updated_at":"2026-11-05T15:30:00Z",
      "strategy_json":{"strategy_type":"custom_build","universe":["AAPL"],"bar_resolution":"15min",
        "risk_management":{"exit_ladder":[{"type":"stop","trigger_pct":-0.02}]}}}]
    """

    public static let openPositions = """
    [{"strategy_id":"s-trend","strategy_title":"NVDA 200-day trend","position_id":"p-1","symbol":"NVDA",
      "entered_at":"2026-10-06T14:31:00Z","entry_price":142.50,"shares_initial":40,"shares_remaining":40,
      "latest_price":156.14,"pct_change_from_entry":0.0957,"price_source":"live_quote","bar_resolution":"daily",
      "stop":{"trigger_pct":-0.08,"price":131.10,"distance_pct":-0.1604,"label":"Stop"},
      "next_target":{"trigger_pct":0.15,"price":163.88,"distance_pct":0.0496,"label":"Target 1"},"unresolved_count":0},
     {"strategy_id":"s-intraday","strategy_title":"AAPL opening-range breakout","position_id":"p-2","symbol":"AAPL",
      "entered_at":"2026-11-16T14:45:00Z","entry_price":358.20,"shares_initial":25,"shares_remaining":25,
      "latest_price":352.78,"pct_change_from_entry":-0.0151,"price_source":"live_quote","bar_resolution":"15min",
      "stop":{"trigger_pct":-0.02,"price":351.04,"distance_pct":-0.0049,"label":"Stop"},
      "next_target":null,"unresolved_count":1},
     {"strategy_id":"s-trend","strategy_title":"NVDA 200-day trend","position_id":"p-3","symbol":"MSFT",
      "entered_at":"2026-08-20T13:35:00Z","entry_price":498.00,"shares_initial":12,"shares_remaining":6,
      "latest_price":517.99,"pct_change_from_entry":0.0401,"price_source":"daily_close","bar_resolution":"daily",
      "stop":null,"next_target":null,"unresolved_count":0}]
    """

    public static let signal = """
    {"saved_strategy_id":"s-trend","subscription_active":true,"as_of_date":"2026-11-16",
     "current_signal":{"NVDA":"long"},"current_signal_display":"Long NVDA — price is above its 200-day average",
     "last_changed_at":"2026-10-05T21:10:00Z",
     "recent_events":[
       {"id":"e-2","as_of_date":"2026-10-05","change_type":"entered","new_signal_display":"Long NVDA","previous_signal_display":"Cash","reference_price_snapshot":{"NVDA":141.9}},
       {"id":"e-1","as_of_date":"2026-08-11","change_type":"exited","new_signal_display":"Cash","previous_signal_display":"Long NVDA","reference_price_snapshot":null}]}
    """

    public static let positions = """
    {"strategy_id":"s-trend","open_count":1,"closed_count":1,"positions":[
      {"id":"p-1","symbol":"NVDA","entered_at":"2026-10-06T14:31:00Z","entry_price":142.50,"shares_initial":40,"shares_remaining":40,
       "is_open":true,"latest_price":156.14,"pct_change_from_entry":0.0957,"trade_log":[]},
      {"id":"p-0","symbol":"NVDA","entered_at":"2026-06-02T14:31:00Z","closed_at":"2026-08-11T20:00:00Z","entry_price":118.00,
       "shares_initial":30,"shares_remaining":0,"is_open":false,"final_pnl":412.50,"trade_log":[]}]}
    """

    static let replies: [String: String] = [
        "get_my_entitlements_api_me_entitlements_get": entitlements,
        "list_saved_strategies_api_saved_strategies_get": strategies,
        "list_open_positions_api_saved_strategies_open_positions_get": openPositions,
        "get_signal_api_saved_strategies__strategy_id__signal_get": signal,
        "get_strategy_positions_api_saved_strategies__strategy_id__positions_get": positions,
    ]
}

struct DemoTransport: ClientTransport {
    let live = URLSessionTransport()

    func send(
        _ request: HTTPRequest,
        body: HTTPBody?,
        baseURL: URL,
        operationID: String
    ) async throws -> (HTTPResponse, HTTPBody?) {
        guard let reply = DemoData.replies[operationID] else {
            return try await live.send(request, body: body, baseURL: baseURL, operationID: operationID)
        }
        return (HTTPResponse(status: .ok, headerFields: [.contentType: "application/json"]), HTTPBody(reply))
    }
}

extension AppSession {
    /// A session signed in as a made-up user, answering account calls from
    /// `DemoData`. Debug builds only.
    public static func demo() -> AppSession {
        let session = AppSession(store: InMemorySessionStore(DemoData.session), transport: DemoTransport())
        session.isDemo = true
        return session
    }
}
#endif
