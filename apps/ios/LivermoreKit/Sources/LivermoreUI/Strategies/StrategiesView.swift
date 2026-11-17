import LivermoreAPI
import LivermoreKit
import SwiftUI

/// The user's tracked positions and saved strategies.
struct StrategiesView: View {
    @Environment(AppSession.self) private var session

    private enum Phase {
        case loading
        case loaded
        case failed(APIFailure)
    }

    @State private var phase: Phase = .loading
    @State private var strategies: [SavedStrategy] = []
    @State private var positions: [TrackedPosition] = []
    @State private var loadedAt: Date?

    var body: some View {
        NavigationStack {
            Group {
                if !session.isSignedIn {
                    ContentUnavailableView {
                        Label("Sign in to see your strategies", systemImage: "chart.line.uptrend.xyaxis")
                    } description: {
                        Text("Your saved strategies and the positions Livermore is tracking appear here. Sign in from the Account tab.")
                    } actions: {
                        NavigationLink("Test a strategy template") { TemplateGalleryView() }
                            .buttonStyle(.borderedProminent)
                    }
                } else {
                    switch phase {
                    case .loading:
                        ProgressView("Loading your strategies…")
                    case .failed(let error):
                        ContentUnavailableView {
                            Label("Couldn't load your strategies", systemImage: "exclamationmark.triangle")
                        } description: {
                            Text(error.message)
                        } actions: {
                            Button("Try again") { Task { await load() } }
                        }
                    case .loaded:
                        list
                    }
                }
            }
            .navigationTitle("Strategies")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    NavigationLink {
                        TemplateGalleryView()
                    } label: {
                        Label("New strategy", systemImage: "plus")
                    }
                    .accessibilityIdentifier("new-strategy")
                }
            }
            .navigationDestination(for: SavedStrategy.self) { strategy in
                StrategyDetailView(strategy: strategy, trackedPositions: positions.filter { $0.strategyId == strategy.id })
            }
        }
        // Keyed on the signed-in state so signing in (or out) reloads, while
        // returning from a pushed screen with data already shown does not.
        .task(id: session.isSignedIn) {
            guard session.isSignedIn else {
                strategies = []
                positions = []
                phase = .loading
                return
            }
            if case .loaded = phase {
                // Coming back from the builder may mean a strategy was just
                // saved; refresh quietly rather than show a spinner.
                await load(showSpinner: false)
                return
            }
            await load()
        }
    }

    private var list: some View {
        List {
            if session.isDemo { SampleDataNotice() }
            Section {
                if positions.isEmpty {
                    Text("No open positions. Declare one from a strategy with exit rules and Livermore will watch its stop and targets.")
                        .font(.subheadline).foregroundStyle(.secondary)
                } else {
                    ForEach(positions, id: \.positionId) { position in
                        TrackedPositionRow(position: position, quote: session.quotes.quotes[position.symbol.uppercased()])
                    }
                }
            } header: {
                Text("Open positions")
            } footer: {
                if !positions.isEmpty {
                    // What time these prices were fetched, in plain view.
                    VStack(alignment: .leading, spacing: 4) {
                        QuoteFreshnessLabel()
                        if let loadedAt {
                            Text("Stops and targets as of \(loadedAt.formatted(date: .abbreviated, time: .shortened)). Pull down to refresh.")
                        }
                    }
                }
            }

            Section("Your strategies") {
                if strategies.isEmpty {
                    Text("No saved strategies yet. Build one on livermorealpha.com and it will appear here.")
                        .font(.subheadline).foregroundStyle(.secondary)
                } else {
                    ForEach(strategies, id: \.id) { strategy in
                        NavigationLink(value: strategy) {
                            StrategyRow(strategy: strategy, openCount: positions.count { $0.strategyId == strategy.id })
                        }
                    }
                }
            }
        }
        .liveQuotes(positions.map(\.symbol))
        .refreshable {
            await load(showSpinner: false)
            await session.quotes.refresh()
        }
    }

    private func load(showSpinner: Bool = true) async {
        if showSpinner { phase = .loading }
        let service = session.strategies
        async let strategyRows = Result<[SavedStrategy], APIFailure>.capture { () async throws(APIFailure) in
            try await service.strategies()
        }
        async let positionRows = Result<[TrackedPosition], APIFailure>.capture { () async throws(APIFailure) in
            try await service.openPositions()
        }
        switch (await strategyRows, await positionRows) {
        case (.success(let loadedStrategies), .success(let loadedPositions)):
            strategies = loadedStrategies
            positions = loadedPositions
            loadedAt = .now
            phase = .loaded
        case (.failure(let error), _), (_, .failure(let error)):
            if error == .notSignedIn {
                // The stored token is no longer accepted; the sign-in prompt
                // is more useful than an error with a retry that cannot work.
                session.signOut()
            } else {
                phase = .failed(error)
            }
        }
    }
}

/// Shown wherever the debug build's made-up account data appears, so it is
/// never mistaken for a real account.
struct SampleDataNotice: View {
    var body: some View {
        Label("Sample data — not a real account", systemImage: "testtube.2")
            .font(.footnote.weight(.semibold))
            .foregroundStyle(.orange)
            .listRowBackground(Color.orange.opacity(0.12))
    }
}

// MARK: - Rows

struct TrackedPositionRow: View {
    let position: TrackedPosition
    /// The live quote for the position's symbol, when there is one. Without
    /// it the row shows the price the backend last evaluated the ladder on.
    var quote: LiveQuote?

    private var price: Double? { quote?.price ?? position.latestPrice }

    private var changeFromEntry: Double? {
        guard let quote, position.entryPrice > 0 else { return position.pctChangeFromEntry }
        return quote.price / position.entryPrice - 1
    }

    /// Unrealised gain or loss on the shares still held.
    private var openProfit: Double? {
        guard let price else { return nil }
        return (price - position.entryPrice) * position.sharesRemaining
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(Fmt.shares(position.sharesRemaining)) \(position.symbol)")
                        .font(.headline)
                    Text(position.strategyTitle).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text(Fmt.percent(changeFromEntry, signed: true))
                        .font(.headline.monospacedDigit())
                        .foregroundStyle((changeFromEntry ?? 0).changeColor)
                    if let openProfit {
                        Text(Fmt.signedMoney(openProfit))
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(openProfit.changeColor)
                    }
                }
            }
            HStack(spacing: 4) {
                LivePriceText(price: price)
                Text("· \(quote == nil ? position.priceNote : "live quote") · cost basis \(Fmt.price(position.entryPrice))")
            }
            .font(.caption).foregroundStyle(.secondary)

            if let waiting = position.unresolvedCount, waiting > 0 {
                Label(
                    waiting == 1 ? "A tier fired and is waiting on you." : "\(waiting) tiers fired and are waiting on you.",
                    systemImage: "bell.badge"
                )
                .font(.caption.weight(.medium))
                .padding(.horizontal, 10).padding(.vertical, 6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.orange.opacity(0.15), in: RoundedRectangle(cornerRadius: 8))
            }

            if position.stop != nil || position.nextTarget != nil {
                HStack(alignment: .top) {
                    TierCell(title: "Stop", tier: position.stop, signed: false, missing: "none set")
                    TierCell(title: "Next target", tier: position.nextTarget, signed: true, missing: "all hit")
                }
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }
}

private struct TierCell: View {
    let title: String
    let tier: TierMarker?
    let signed: Bool
    let missing: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title.uppercased()).font(.caption2.weight(.semibold)).tracking(0.6).foregroundStyle(.secondary)
            if let tier {
                Text(Fmt.price(tier.price)).font(.subheadline.monospacedDigit())
                Text("\(Fmt.percent(tier.distancePct, signed: signed)) away").font(.caption2).foregroundStyle(.secondary)
            } else {
                Text(missing).font(.subheadline).foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct StrategyRow: View {
    let strategy: SavedStrategy
    let openCount: Int

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(strategy.title).font(.body).lineLimit(2)
                Text("Saved \(strategy.createdAt.formatted(date: .abbreviated, time: .omitted))")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            if openCount > 0 {
                Text(openCount == 1 ? "1 open" : "\(openCount) open")
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 8).padding(.vertical, 3)
                    .background(.green.opacity(0.15), in: Capsule())
            } else if strategy.tracksExits {
                Text("Can track").font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}
