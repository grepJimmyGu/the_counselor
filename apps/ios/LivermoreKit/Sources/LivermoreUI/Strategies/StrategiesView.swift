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
            .screenBackground()
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
            if !positions.isEmpty {
                Section {
                    PositionsSummary(positions: positions, quotes: session.quotes.quotes)
                        .listRowInsets(EdgeInsets())
                        .listRowBackground(Color.clear)
                }
            }
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
                    Text("No saved strategies yet. Tap + to test a template, change it to suit you, and save it. Strategies saved on livermorealpha.com appear here too.")
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
            .foregroundStyle(.caution)
            .listRowBackground(Color.caution.opacity(0.12))
    }
}

// MARK: - Rows

/// What the tracked positions are worth, and how they stand against cost.
struct PositionsSummary: View {
    let positions: [TrackedPosition]
    let quotes: [String: LiveQuote]

    var body: some View {
        var value = 0.0
        var cost = 0.0
        for position in positions {
            let price = quotes[position.symbol.uppercased()]?.price ?? position.latestPrice ?? position.entryPrice
            value += price * position.sharesRemaining
            cost += position.entryPrice * position.sharesRemaining
        }
        let profit = value - cost
        let waiting = positions.reduce(0) { $0 + ($1.unresolvedCount ?? 0) }

        return Card {
            Text("Tracked positions").eyebrowStyle()
            Text(Fmt.price(value)).font(.hero).contentTransition(.numericText(value: value))
            HStack(spacing: 8) {
                ChangePill(fraction: cost > 0 ? profit / cost : nil)
                Text("\(Fmt.signedMoney(profit)) since entry")
                    .font(.subheadline.monospacedDigit()).foregroundStyle(profit.changeColor)
            }
            HStack(spacing: 8) {
                StatTile(label: "Positions", value: "\(positions.count)")
                StatTile(label: "Cost basis", value: Fmt.price(cost))
                StatTile(label: "Waiting on you", value: "\(waiting)", tint: waiting > 0 ? .caution : nil)
            }
        }
        .accessibilityElement(children: .combine)
    }
}

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
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(position.symbol).font(.headline.monospaced())
                    Text("\(Fmt.shares(position.sharesRemaining)) shares · \(position.strategyTitle)")
                        .font(.caption).foregroundStyle(.inkSecondary).lineLimit(1)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 3) {
                    LivePriceText(price: price).font(.subheadline.weight(.semibold))
                    ChangePill(fraction: changeFromEntry, compact: true)
                }
            }

            if position.stop != nil || position.nextTarget != nil {
                LevelBar(
                    stop: position.stop?.price, entry: position.entryPrice,
                    target: position.nextTarget?.price, price: price
                )
            }

            HStack {
                Text("Cost \(Fmt.price(position.entryPrice)) · \(quote == nil ? position.priceNote : "live quote")")
                    .foregroundStyle(.inkSecondary)
                Spacer()
                if let openProfit {
                    Text(Fmt.signedMoney(openProfit)).fontWeight(.semibold).foregroundStyle(openProfit.changeColor)
                }
            }
            .font(.caption.monospacedDigit())

            if let waiting = position.unresolvedCount, waiting > 0 {
                Notice(
                    text: waiting == 1 ? "An exit level was reached. See Actions." : "\(waiting) exit levels were reached. See Actions.",
                    systemImage: "bell.badge.fill", tint: .caution
                )
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }
}

private struct StrategyRow: View {
    let strategy: SavedStrategy
    let openCount: Int

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: strategy.tracksExits ? "scope" : "chart.xyaxis.line")
                .font(.body.weight(.medium)).foregroundStyle(.brand)
                .frame(width: 40, height: 40)
                .background(Color.brand.opacity(0.10), in: RoundedRectangle(cornerRadius: 11, style: .continuous))
            VStack(alignment: .leading, spacing: 4) {
                Text(strategy.title).font(.subheadline.weight(.semibold)).lineLimit(2)
                HStack(spacing: 6) {
                    if openCount > 0 {
                        Tag(openCount == 1 ? "1 position" : "\(openCount) positions", tint: .gain)
                    } else if strategy.tracksExits {
                        Tag("Ready to track", tint: .brand)
                    } else {
                        Tag("No exit plan")
                    }
                    let universe = strategy.universe
                    if !universe.isEmpty {
                        Text(universe.count <= 2 ? universe.joined(separator: ", ") : "\(universe.prefix(2).joined(separator: ", ")) +\(universe.count - 2)")
                            .font(.caption.monospaced()).foregroundStyle(.inkSecondary)
                    }
                }
            }
        }
        .padding(.vertical, 2)
    }
}
