import Foundation
import LivermoreAPI
import Testing

@testable import LivermoreKit

private let server = URL(string: "https://api.test")!

private enum Op {
    static let strategies = "list_saved_strategies_api_saved_strategies_get"
    static let openPositions = "list_open_positions_api_saved_strategies_open_positions_get"
    static let signal = "get_signal_api_saved_strategies__strategy_id__signal_get"
    static let positions = "get_strategy_positions_api_saved_strategies__strategy_id__positions_get"
}

@MainActor
@Suite("StrategyService")
struct StrategyServiceTests {
    private func make() -> (StrategyService, MockTransport, AppSession) {
        let transport = MockTransport()
        let session = AppSession(
            serverURL: server, store: InMemorySessionStore(DemoData.session), transport: transport
        )
        return (session.strategies, transport, session)
    }

    // The sample data the debug build shows is run through the real decoder
    // here, so it cannot drift from the API schema.

    @Test("saved strategies decode, and only those with exit rules can be tracked")
    func strategies() async throws {
        let (service, transport, _) = make()
        transport.stub(Op.strategies, .json(status: 200, DemoData.strategies))

        let rows = try await service.strategies()

        #expect(rows.map(\.id) == ["s-trend", "s-rotation", "s-intraday"])
        // An empty exit ladder means there is nothing to monitor.
        #expect(rows.map(\.tracksExits) == [true, false, true])
        // Absent means daily.
        #expect(rows.map(\.barResolution) == ["daily", "daily", "15min"])
        #expect(transport.requests.last?.authorization == "Bearer demo-token")
    }

    @Test("open positions decode with their stop, next target and price note")
    func openPositions() async throws {
        let (service, transport, _) = make()
        transport.stub(Op.openPositions, .json(status: 200, DemoData.openPositions))

        let rows = try await service.openPositions()

        #expect(rows.count == 3)
        #expect(rows[0].stop?.price == 131.10)
        #expect(rows[0].nextTarget?.distancePct == 0.0496)
        #expect(rows[1].nextTarget == nil)
        #expect(rows[1].unresolvedCount == 1)
        // A daily strategy on a live quote says it is checked at the close;
        // an intraday one does not; a close is called a close.
        #expect(rows.map(\.priceNote) == ["latest quote · checked at the close", "latest quote", "last close"])
    }

    @Test("a signal and a strategy's positions decode")
    func signalAndPositions() async throws {
        let (service, transport, _) = make()
        transport.stub(Op.signal, .json(status: 200, DemoData.signal))
        transport.stub(Op.positions, .json(status: 200, DemoData.positions))

        let signal = try await service.signal(strategyID: "s-trend")
        #expect(signal.subscriptionActive)
        #expect(signal.recentEvents.map(\.changeType) == ["entered", "exited"])
        #expect(signal.lastChangedAt != nil)

        let positions = try await service.positions(strategyID: "s-trend")
        #expect(positions.openCount == 1)
        #expect(positions.positions.last?.finalPnl == 412.50)
    }

    @Test("a signal that has never been computed is not an error")
    func emptySignal() async throws {
        let (service, transport, _) = make()
        transport.stub(Op.signal, .json(status: 200, #"{"saved_strategy_id":"s-x","subscription_active":false,"recent_events":[]}"#))

        let signal = try await service.signal(strategyID: "s-x")

        #expect(signal.currentSignalDisplay == nil)
        #expect(signal.recentEvents.isEmpty)
    }

    @Test("an expired token is reported as not signed in, not as a server fault")
    func expiredToken() async {
        let (service, transport, _) = make()
        transport.stub(Op.strategies, .json(status: 401, #"{"detail":"Invalid or expired session token."}"#))

        await #expect(throws: APIFailure.notSignedIn) { try await service.strategies() }
    }
}
