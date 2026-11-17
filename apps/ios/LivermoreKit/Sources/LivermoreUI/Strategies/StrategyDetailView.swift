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
    @State private var isDeclaring = false
    @State private var buySymbol: BuyTarget?
    /// A buy the user just sent, offered for tracking once it fills.
    @State private var boughtSymbol: String?
    @State private var declaredNote: String?

    private struct BuyTarget: Identifiable {
        let symbol: String
        var id: String { symbol }
    }

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

            actSection

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
        .sheet(isPresented: $isDeclaring) {
            DeclarePositionView(strategy: strategy, presetSymbol: boughtSymbol) {
                boughtSymbol = nil
                declaredNote = "Tracking started. It appears under Open positions on the Strategies tab."
            }
        }
        .sheet(item: $buySymbol) { target in
            OrderTicketView(
                symbol: target.symbol, side: .buy(suggestedDollars: nil),
                reason: "Buying for “\(strategy.title)”"
            ) { _, _ in
                boughtSymbol = target.symbol
            }
        }
        .screenBackground()
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
            if session.brokerageLink.status == nil { await session.brokerageLink.refresh() }
        }
    }
}

extension StrategyDetailView {
    /// Acting on the strategy: buy through the user's broker, and tell
    /// Livermore about a position so its exits are watched.
    @ViewBuilder
    fileprivate var actSection: some View {
        let link = session.brokerageLink
        Section {
            if link.canTrade {
                if strategy.universe.count == 1, let only = strategy.universe.first {
                    Button("Buy \(only) at your broker", systemImage: "arrow.down.left.circle.fill") {
                        buySymbol = BuyTarget(symbol: only)
                    }
                    .accessibilityIdentifier("buy-at-broker")
                } else if !strategy.universe.isEmpty {
                    Menu {
                        ForEach(strategy.universe, id: \.self) { symbol in
                            Button(symbol) { buySymbol = BuyTarget(symbol: symbol) }
                        }
                    } label: {
                        Label("Buy at your broker", systemImage: "arrow.down.left.circle.fill")
                    }
                    .accessibilityIdentifier("buy-at-broker")
                }
            }
            if strategy.tracksExits {
                Button(
                    boughtSymbol.map { "Track the \($0) you just bought" } ?? "Track a position you hold",
                    systemImage: "scope"
                ) {
                    isDeclaring = true
                }
                .accessibilityIdentifier("track-position")
            }
            if let declaredNote {
                Label(declaredNote, systemImage: "checkmark.circle").font(.footnote).foregroundStyle(.gain)
            }
            if let typed = strategy.typedStrategy {
                NavigationLink {
                    StrategyRerunView(saved: strategy, original: typed)
                } label: {
                    Label("Test it again, with changes", systemImage: "slider.horizontal.3")
                }
                .accessibilityIdentifier("rerun-strategy")
            }
        } header: {
            Text("Act on it")
        } footer: {
            if !link.canTrade {
                Text(link.isLinked
                    ? "Sending orders from Livermore isn't switched on yet — buy in your brokerage app, then track the position here."
                    : "Link your brokerage from the Actions tab to buy from here. You can track a position you already hold either way.")
            } else if strategy.tracksExits {
                Text("Today's signal above says what the rule wants. You decide the size, see your broker's numbers, and send the order yourself.")
            } else {
                Text("This strategy has no stop or targets, so a position can't be tracked against it.")
            }
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
