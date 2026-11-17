import LivermoreAPI
import LivermoreKit
import SwiftUI

/// One strategy: today's signal, what changed recently, and its positions.
struct StrategyDetailView: View {
    @Environment(AppSession.self) private var session
    let strategy: SavedStrategy
    /// Open positions for this strategy from the list screen — these carry the
    /// live stop and next target, which the per-strategy endpoint does not.
    let trackedPositions: [TrackedPosition]

    @State private var signal: SignalState?
    @State private var signalError: APIFailure?
    @State private var positions: StrategyPositions?

    var body: some View {
        List {
            if session.isDemo { SampleDataNotice() }
            Section("Today's signal") {
                if let signal {
                    SignalSummary(signal: signal)
                } else if let signalError {
                    Text(signalError.message).font(.subheadline).foregroundStyle(.secondary)
                } else {
                    ProgressView()
                }
            }

            if let events = signal?.recentEvents, !events.isEmpty {
                Section("Recent changes") {
                    ForEach(events, id: \.id) { event in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(event.asOfDate).font(.caption2.weight(.semibold)).tracking(0.6).foregroundStyle(.secondary)
                            Text(event.newSignalDisplay).font(.subheadline)
                            if let previous = event.previousSignalDisplay {
                                Text("was: \(previous)").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }

            Section("Open positions") {
                if !strategy.tracksExits {
                    Text("This strategy has no exit rules, so there's nothing to monitor a position against. Add a stop (and any targets) when building it, and you can track positions here.")
                        .font(.subheadline).foregroundStyle(.secondary)
                } else if trackedPositions.isEmpty {
                    Text("No open positions on this strategy.").font(.subheadline).foregroundStyle(.secondary)
                } else {
                    ForEach(trackedPositions, id: \.positionId) { position in
                        TrackedPositionRow(position: position, quote: session.quotes.quotes[position.symbol.uppercased()])
                    }
                    QuoteFreshnessLabel()
                }
            }

            let closed = (positions?.positions ?? []).filter { !$0.isOpen }
            if !closed.isEmpty {
                Section("Closed positions") {
                    ForEach(closed, id: \.id) { position in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("\(Fmt.shares(position.sharesInitial)) \(position.symbol)").font(.subheadline.weight(.semibold))
                                if let closedAt = position.closedAt {
                                    Text("Closed \(closedAt.formatted(date: .abbreviated, time: .omitted))")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            }
                            Spacer()
                            if let pnl = position.finalPnl {
                                Text(Fmt.signedMoney(pnl)).font(.subheadline.monospacedDigit()).foregroundStyle(pnl.changeColor)
                            }
                        }
                    }
                }
            }
        }
        .liveQuotes(trackedPositions.map(\.symbol))
        .navigationTitle(strategy.title)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task {
            guard signal == nil, signalError == nil else { return }
            let service = session.strategies
            async let positionsResult = try? service.positions(strategyID: strategy.id)
            do throws(APIFailure) {
                signal = try await service.signal(strategyID: strategy.id)
            } catch {
                signalError = error
            }
            positions = await positionsResult
        }
    }
}

private struct SignalSummary: View {
    let signal: SignalState

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let asOf = signal.asOfDate {
                Text("AS OF \(asOf)").font(.caption2.weight(.semibold)).tracking(0.8).foregroundStyle(.secondary)
            }
            Text(signal.currentSignalDisplay ?? "No signal has been computed for this strategy yet.")
                .font(.body.weight(.medium))
            if let changed = signal.lastChangedAt {
                Text("Last changed \(changed.formatted(date: .abbreviated, time: .omitted))")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Label(
                signal.subscriptionActive ? "Email alerts are on" : "Email alerts are off",
                systemImage: signal.subscriptionActive ? "bell.fill" : "bell.slash"
            )
            .font(.caption).foregroundStyle(.secondary)
        }
    }
}
