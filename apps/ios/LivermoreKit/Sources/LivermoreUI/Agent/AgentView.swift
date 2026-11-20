import LivermoreKit
import SwiftUI

/// The user's portfolio agent: what it is watching, what it has found, and
/// a way to ask it things. Everything it offers to do opens a screen that
/// already exists: a company page, the Actions tab, or the order ticket.
struct AgentView: View {
    @Environment(AppSession.self) private var session
    @Environment(TabRouter.self) private var router

    @State private var draft: DraftItem?
    @State private var showSettings = false

    private var agent: AgentStore { session.agent }
    private var watched: [String] { session.watchlist.entries.map(\.symbol) }

    var body: some View {
        NavigationStack {
            Group {
                if !session.isSignedIn {
                    ContentUnavailableView {
                        Label("Sign in to meet your agent", systemImage: "sparkles")
                    } description: {
                        Text("It watches your watchlist and your holdings, tells you what changed, and helps you act on your own rules.")
                    }
                } else {
                    content
                }
            }
            .screenBackground()
            .navigationTitle("Agent")
            .toolbar {
                if session.isSignedIn {
                    ToolbarItem(placement: .primaryAction) {
                        Button { showSettings = true } label: { Image(systemName: "slider.horizontal.3") }
                            .accessibilityLabel("Agent settings")
                            .accessibilityIdentifier("agent-settings")
                    }
                }
            }
            .sheet(isPresented: $showSettings) { AgentSettingsView() }
            .sheet(item: $draft) { AgentOrderSheet(draft: $0.draft) }
        }
        .task(id: session.isSignedIn) {
            guard session.isSignedIn else { return }
            await agent.load()
            await agent.syncWatchlist(watched)
            // The first time, look straight away so the screen is not empty.
            if agent.lastChecked == nil, agent.failure == nil { await agent.check() }
        }
        .onChange(of: watched) { _, symbols in
            Task { await agent.syncWatchlist(symbols) }
        }
    }

    private var content: some View {
        ScrollView {
            VStack(spacing: Metrics.sectionSpacing) {
                statusCard
                askCard
                if let failure = agent.failure {
                    Notice(text: failure.message, systemImage: "exclamationmark.triangle.fill", tint: .caution)
                }
                ForEach(agent.notes, id: \.self) { Notice(text: $0) }
                if agent.insights.isEmpty {
                    emptyState
                } else {
                    ForEach(agent.insights, id: \.id) { insight in
                        InsightCard(insight: insight, onReview: { draft = DraftItem(draft: $0) }, onOpenActions: { router.tab = .actions })
                    }
                }
            }
            .padding(Metrics.screenPadding)
        }
        .refreshable { await agent.check() }
    }

    private var statusCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 12) {
                Toggle(isOn: Binding(
                    get: { agent.profile?.enabled ?? false },
                    set: { on in Task { await agent.update(enabled: on) } }
                )) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Watch around the clock").font(.headline)
                        Text(agent.profile?.enabled == true
                            ? "Checks twice an hour while US markets are open, whether or not the app is open."
                            : "Off. It looks only when you ask it to.")
                            .font(.footnote).foregroundStyle(.inkSecondary)
                    }
                }
                .disabled(agent.profile == nil)
                .accessibilityIdentifier("agent-enabled")

                HStack(spacing: 8) {
                    Tag("\(watched.count) on your watchlist", systemImage: "eye")
                    if session.brokerageLink.isLinked {
                        Tag("Holdings linked", tint: .gain, systemImage: "building.columns")
                    }
                }
                if let checked = agent.lastChecked {
                    Text("LAST CHECKED \(checked.formatted(date: .abbreviated, time: .shortened))".uppercased())
                        .font(Font.caption2.weight(.semibold)).tracking(0.6).foregroundStyle(.inkSecondary)
                        .accessibilityIdentifier("agent-last-checked")
                }
                Button {
                    Task { await agent.check() }
                } label: {
                    HStack(spacing: 8) {
                        if agent.isChecking { ProgressView() }
                        Text(agent.isChecking ? "Checking" : "Check now")
                    }
                }
                .buttonStyle(SecondaryButtonStyle())
                .disabled(agent.isChecking)
                .accessibilityIdentifier("agent-check")
            }
        }
    }

    private var askCard: some View {
        NavigationLink {
            AgentChatView()
        } label: {
            HStack(spacing: 12) {
                Image(systemName: "sparkles")
                    .font(.title3).foregroundStyle(.white)
                    .frame(width: 40, height: 40)
                    .background(Color.brand, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                VStack(alignment: .leading, spacing: 2) {
                    Text("Ask your agent").font(.headline).foregroundStyle(Color.primary)
                    Text("About your portfolio, your watchlist, a filing, or how you trade.")
                        .font(.footnote).foregroundStyle(.inkSecondary)
                        .multilineTextAlignment(.leading)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(.inkSecondary)
            }
            .padding(Metrics.cardPadding)
            .background(Color.surface, in: RoundedRectangle(cornerRadius: Metrics.cardRadius, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("agent-ask")
    }

    private var emptyState: some View {
        Card {
            VStack(alignment: .leading, spacing: 6) {
                Text("Nothing to report").font(.headline)
                Text("Your agent tells you when something on your watchlist or in your holdings moves past your alert, when a holding grows past your limit, when a new filing has something to check, and when a strategy's exit is waiting on you.")
                    .font(.subheadline).foregroundStyle(.inkSecondary)
            }
        }
    }
}

/// One thing the agent found, with what it offers to open.
private struct InsightCard: View {
    @Environment(AppSession.self) private var session
    let insight: AgentInsight
    let onReview: (OrderSuggestion) -> Void
    let onOpenActions: () -> Void

    private var tint: Color {
        switch insight.severity {
        case "watch": .caution
        case "good": .gain
        default: .inkSecondary
        }
    }

    private var kind: String {
        switch insight.kind {
        case "price_move": "Price move"
        case "concentration": "Position size"
        case "filing": "New filing"
        case "exits_waiting": "Exits waiting"
        default: "Note"
        }
    }

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Tag(kind, tint: tint)
                    Spacer()
                    Text(insight.createdAt.formatted(date: .abbreviated, time: .shortened).uppercased())
                        .font(Font.caption2.weight(.semibold)).tracking(0.6).foregroundStyle(.inkSecondary)
                }
                Text(insight.title).font(.headline)
                Text(insight.body).font(.subheadline).foregroundStyle(.inkSecondary)
                actionButton
                HStack {
                    NavigationLink {
                        AgentChatView(starter: "Tell me more about this: \(insight.title)")
                    } label: {
                        Label("Ask about this", systemImage: "sparkles").font(.subheadline.weight(.semibold))
                    }
                    Spacer()
                    Button("Dismiss") { Task { await session.agent.dismiss(insight) } }
                        .font(.subheadline).foregroundStyle(.inkSecondary)
                        .accessibilityIdentifier("insight-dismiss")
                }
            }
        }
        .accessibilityIdentifier("insight-\(insight.kind)")
    }

    @ViewBuilder private var actionButton: some View {
        switch insight.suggestedAction {
        case .openCompany(let symbol)?:
            NavigationLink {
                CompanyView(symbol: symbol)
            } label: {
                Text("Open \(symbol)").frame(maxWidth: .infinity)
            }
            .buttonStyle(SecondaryButtonStyle())
        case .reviewOrder(let order)?:
            Button("Review the order") { onReview(order) }
                .buttonStyle(PrimaryButtonStyle())
                .accessibilityIdentifier("insight-review-order")
        case .openActions?:
            Button("Open Actions", action: onOpenActions)
                .buttonStyle(SecondaryButtonStyle())
        case nil:
            EmptyView()
        }
    }
}

struct DraftItem: Identifiable {
    let id = UUID()
    let draft: OrderSuggestion
}

/// Opens the existing order ticket with the agent's draft filled in. The
/// ticket still shows the broker's price and still needs the user's
/// confirmation: a draft changes what is typed in for them, nothing else.
struct AgentOrderSheet: View {
    @Environment(AppSession.self) private var session
    @Environment(\.dismiss) private var dismiss
    let draft: OrderSuggestion

    private var link: BrokerageLink { session.brokerageLink }

    var body: some View {
        Group {
            if link.status == nil, link.isLoading {
                ProgressView()
            } else if !link.isLinked {
                unavailable("Link a brokerage in Account to review this order. The agent can draft it; only you can send it, through your own broker.")
            } else {
                switch draft.side {
                case .sell:
                    if let holding = link.holding(of: draft.symbol) {
                        OrderTicketView(
                            symbol: draft.symbol, side: .sell(holding: holding, suggested: draft.units),
                            reason: draft.reason
                        )
                    } else {
                        unavailable("Your broker shows no \(draft.symbol) to sell.")
                    }
                case .buy:
                    OrderTicketView(symbol: draft.symbol, side: .buy(suggestedDollars: dollars), reason: draft.reason)
                }
            }
        }
        .task { if link.status == nil { await link.refresh() } }
    }

    /// Buys are sized in dollars. A draft in shares is priced at the live quote.
    private var dollars: Double? {
        if let amount = draft.amountUSD { return amount }
        guard let units = draft.units, let price = session.quotes.quotes[draft.symbol]?.price else { return nil }
        return (units * price).rounded()
    }

    private func unavailable(_ text: String) -> some View {
        VStack(spacing: 16) {
            Notice(text: text)
            Button("Close") { dismiss() }.buttonStyle(SecondaryButtonStyle())
        }
        .padding(Metrics.screenPadding)
        .presentationDetents([.medium])
    }
}
