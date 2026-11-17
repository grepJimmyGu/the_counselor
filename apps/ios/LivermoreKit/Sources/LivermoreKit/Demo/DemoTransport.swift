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
      "strategy_json":{"strategy_name":"NVDA 200-day trend","strategy_type":"moving_average_filter","universe":["NVDA"],
        "benchmark":"SPY","start_date":"2021-10-02","end_date":"2026-10-02","initial_capital":10000,
        "rebalance_frequency":"daily","bar_resolution":"daily","transaction_cost_bps":10,"slippage_bps":5,
        "position_sizing":{"method":"equal_weight","max_positions":1},"rules":[{"lookback_days":200}],
        "risk_management":{"exit_ladder":[{"trigger_pct":-0.08,"action":"sell_all","label":"Stop"},
          {"trigger_pct":0.15,"action":"sell_fraction","fraction":0.5,"label":"Target 1"},
          {"trigger_pct":0.30,"action":"sell_all","label":"Target 2"}]}}},
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
      "stop":null,"next_target":null,"unresolved_count":1}]
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

    /// Exits waiting on a decision. One intraday stop and one daily target,
    /// so both price caveats and both order sizes are on screen.
    nonisolated(unsafe) static let unresolvedExits: [[String: Any]] = [
        ["strategy_id": "s-intraday", "strategy_title": "AAPL opening-range breakout", "position_id": "p-2",
         "symbol": "AAPL", "trigger_type": "stop_hit", "tier_label": "Stop", "signaled_at": "2026-11-16T15:30:00Z",
         "price": 351.04, "pct_change": -0.02, "action": "sell_all", "shares": 25, "shares_remaining": 25,
         "shares_initial": 25, "entry_price": 358.20, "bar_resolution": "15min"],
        ["strategy_id": "s-trend", "strategy_title": "NVDA 200-day trend", "position_id": "p-3",
         "symbol": "MSFT", "trigger_type": "tp2_hit", "tier_label": "Target 2", "signaled_at": "2026-11-13T21:10:00Z",
         "price": 522.90, "pct_change": 0.05, "action": "sell_all", "shares": 6, "shares_remaining": 6,
         "shares_initial": 12, "entry_price": 498.00, "bar_resolution": "daily", "bar_date": "2026-11-13"],
    ]

    nonisolated(unsafe) static let notices: [[String: Any]] = [
        ["id": 41, "title": "NVDA 200-day trend — signal unchanged",
         "body": "Still long NVDA: the price closed above its 200-day average on Friday.",
         "created_at": "2026-11-14T21:15:00Z"],
    ]

    public static let brokerageStatus = """
    {"configured":true,"registered":true,"connected_accounts":1,"last_synced_at":"2026-11-16T21:00:00+00:00","trading_enabled":true}
    """

    public static let brokerageAccounts = """
    [{"id":"acct-1","name":"Individual","number":"30014821","institution_name":"Sample Brokerage"}]
    """

    public static let brokerageHoldings = """
    [{"account_id":"acct-1","symbol":"NVDA","units":40,"average_purchase_price":142.50,"last_price":156.14,"open_pnl":545.60,"cash_equivalent":false},
     {"account_id":"acct-1","symbol":"AAPL","units":25,"average_purchase_price":358.20,"last_price":352.78,"open_pnl":-135.50,"cash_equivalent":false},
     {"account_id":"acct-1","symbol":"MSFT","units":6,"average_purchase_price":498.00,"last_price":517.99,"open_pnl":119.94,"cash_equivalent":false},
     {"account_id":"acct-1","symbol":"SPAXX","units":1520.33,"average_purchase_price":1.0,"last_price":1.0,"open_pnl":0,"cash_equivalent":true}]
    """

    static let replies: [String: String] = [
        "get_my_entitlements_api_me_entitlements_get": entitlements,
        "list_saved_strategies_api_saved_strategies_get": strategies,
        "list_open_positions_api_saved_strategies_open_positions_get": openPositions,
        "get_signal_api_saved_strategies__strategy_id__signal_get": signal,
        "get_strategy_positions_api_saved_strategies__strategy_id__positions_get": positions,
        "snaptrade_status_api_snaptrade_status_get": brokerageStatus,
        "snaptrade_accounts_api_snaptrade_accounts_get": brokerageAccounts,
        "snaptrade_positions_api_snaptrade_positions_get": brokerageHoldings,
        "snaptrade_connect_api_snaptrade_connect_post": #"{"redirect_uri":"https://livermorealpha.com/account/brokerage"}"#,
        "place_order_api_snaptrade_orders_place_post": #"{"status":"ACCEPTED (sample — nothing was sent)","brokerage_order_id":"SAMPLE-0001"}"#,
    ]

    /// Public, read-only calls the sample account still makes for real, so
    /// research and prices are live. Everything else is answered here or
    /// refused: the sample account never reaches an account endpoint, and can
    /// never send an order.
    static let liveOperations: Set<String> = [
        "get_live_quotes_api_live_quotes_get",
        "search_symbols_api_symbols_search_get",
        "get_company_overview_api_company__symbol__overview_get",
        "get_company_trend_api_company__symbol__trend_get",
        "get_sentiment_summary_api_sentiment__symbol__summary_get",
        "get_summary_api_supply_chain__symbol__summary_get",
    ]
}

/// What the sample account has done this launch, so resolving an exit or
/// dismissing a notice makes it leave the list as it would for real.
final class DemoState: @unchecked Sendable {
    private let lock = NSLock()
    private var resolvedPositions = Set<String>()
    private var acknowledged = Set<Int>()

    func resolve(position: String) { lock.withLock { _ = resolvedPositions.insert(position) } }
    func acknowledge(_ id: Int) { lock.withLock { _ = acknowledged.insert(id) } }

    var exits: [[String: Any]] {
        let resolved = lock.withLock { resolvedPositions }
        return DemoData.unresolvedExits.filter { !resolved.contains($0["position_id"] as? String ?? "") }
    }

    var notices: [[String: Any]] {
        let seen = lock.withLock { acknowledged }
        return DemoData.notices.filter { !seen.contains($0["id"] as? Int ?? -1) }
    }
}

struct DemoTransport: ClientTransport {
    let live = URLSessionTransport()
    let state = DemoState()

    private static func json(_ value: Any, status: HTTPResponse.Status = .ok) -> (HTTPResponse, HTTPBody?) {
        let data = (try? JSONSerialization.data(withJSONObject: value)) ?? Data("null".utf8)
        return (HTTPResponse(status: status, headerFields: [.contentType: "application/json"]), HTTPBody(data))
    }

    /// The path segment after `marker`: the position id in
    /// `/positions/p-2/hold`, the entry id in `/notifications/41/ack`.
    private static func segment(after marker: String, in request: HTTPRequest) -> String? {
        let parts = (request.path ?? "").split(separator: "?").first?.split(separator: "/").map(String.init) ?? []
        guard let index = parts.firstIndex(of: marker), index + 1 < parts.count else { return nil }
        return parts[index + 1]
    }

    private static func position(id: String, symbol: String, shares: Double, entry: Double, open: Bool) -> [String: Any] {
        ["id": id, "symbol": symbol, "entered_at": "2026-11-16T14:45:00Z", "entry_price": entry,
         "shares_initial": shares, "shares_remaining": open ? shares : 0, "is_open": open, "trade_log": []]
    }

    func send(
        _ request: HTTPRequest,
        body: HTTPBody?,
        baseURL: URL,
        operationID: String
    ) async throws -> (HTTPResponse, HTTPBody?) {
        if let reply = DemoData.replies[operationID] {
            return (HTTPResponse(status: .ok, headerFields: [.contentType: "application/json"]), HTTPBody(reply))
        }
        if DemoData.liveOperations.contains(operationID) {
            return try await live.send(request, body: body, baseURL: baseURL, operationID: operationID)
        }

        var sent: [String: Any] = [:]
        if let body, let data = try? await Data(collecting: body, upTo: 1 << 20) {
            sent = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        }

        switch operationID {
        case "list_unresolved_exits_api_saved_strategies_unresolved_exits_get":
            return Self.json(state.exits)
        case "list_pending_banners_api_me_notifications_pending_get":
            return Self.json(state.notices)
        case "acknowledge_banner_api_me_notifications__entry_id__ack_post":
            if let id = Self.segment(after: "notifications", in: request).flatMap(Int.init) { state.acknowledge(id) }
            return (HTTPResponse(status: .noContent), nil)
        case "confirm_position_exit_api_saved_strategies__strategy_id__positions__position_id__confirm_exit_post",
             "hold_position_through_exit_api_saved_strategies__strategy_id__positions__position_id__hold_post":
            let id = Self.segment(after: "positions", in: request) ?? ""
            state.resolve(position: id)
            let exit = DemoData.unresolvedExits.first { $0["position_id"] as? String == id }
            return Self.json(Self.position(
                id: id, symbol: exit?["symbol"] as? String ?? "", shares: exit?["shares_initial"] as? Double ?? 0,
                entry: exit?["entry_price"] as? Double ?? 0, open: operationID.hasSuffix("hold_post")
            ))
        case "declare_position_api_saved_strategies__strategy_id__positions_post":
            return Self.json(Self.position(
                id: "p-new", symbol: sent["symbol"] as? String ?? "", shares: sent["shares"] as? Double ?? 0,
                entry: sent["entry_price"] as? Double ?? 0, open: true
            ), status: .created)
        case "preview_order_api_snaptrade_orders_preview_post":
            var preview: [String: Any] = [
                "trade_id": "sample-trade", "symbol": sent["symbol"] as? String ?? "",
                "action": sent["action"] as? String ?? "", "estimated_commission": 0.0, "remaining_cash": 4812.07,
            ]
            if let units = sent["units"] as? Double { preview["units"] = units }
            return Self.json(preview)
        default:
            return Self.json(["detail": "The sample account can't do this. Sign in to your own account."], status: .badRequest)
        }
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
