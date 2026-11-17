import LivermoreKit
import SwiftUI

/// The user's brokerage link: connect one, see the accounts and what they
/// hold.
struct BrokerageView: View {
    @Environment(AppSession.self) private var session
    @Environment(\.openURL) private var openURL

    @State private var browser: BrowserDestination?
    @State private var isOpeningLink = false
    @State private var linkFailure: APIFailure?

    private var link: BrokerageLink { session.brokerageLink }

    var body: some View {
        List {
            if session.isDemo { SampleDataNotice() }

            if let status = link.status {
                if !status.configured {
                    Section {
                        Label("Brokerage links aren't available right now.", systemImage: "wrench.and.screwdriver")
                            .foregroundStyle(.secondary)
                    }
                } else if !status.isLinked {
                    connectSection(isFirst: true)
                } else {
                    linkedSections(status)
                    connectSection(isFirst: false)
                }
            } else if let failure = link.failure {
                Section {
                    Text(failure.message).foregroundStyle(.secondary)
                    Button("Try again") { Task { await link.refresh() } }
                }
            } else {
                Section { HStack { ProgressView(); Text("Checking your brokerage link…").foregroundStyle(.secondary) } }
            }
        }
        .screenBackground()
        .navigationTitle("Brokerage")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        .sheet(item: $browser, onDismiss: { Task { await link.refresh() } }) { destination in
            SafariSheet(url: destination.url).ignoresSafeArea()
        }
        #endif
        .refreshable { await link.refresh() }
        .task { await link.refresh() }
    }

    private func connectSection(isFirst: Bool) -> some View {
        Section {
            Button(action: startLink) {
                HStack {
                    Label(isFirst ? "Link a brokerage" : "Link another brokerage", systemImage: "link")
                    Spacer()
                    if isOpeningLink { ProgressView() }
                }
            }
            .disabled(isOpeningLink)
            .accessibilityIdentifier("link-brokerage")
        } header: {
            if isFirst { Text("Connect your own broker") }
        } footer: {
            VStack(alignment: .leading, spacing: 6) {
                if let linkFailure { Text(linkFailure.message).foregroundStyle(.loss) }
                if isFirst {
                    Text("You sign in on your broker's own page, through SnapTrade — Robinhood, Charles Schwab and the other brokers it supports. Livermore never sees your brokerage password and cannot withdraw or move money.")
                    Text("Once linked, Livermore can show what you hold and, where your broker allows it, send an order you have reviewed and confirmed. It never places one on its own.")
                } else {
                    Text("When you finish on your broker's page, tap Done to come back here.")
                }
            }
        }
    }

    @ViewBuilder
    private func linkedSections(_ status: BrokerageStatus) -> some View {
        Section {
            ForEach(link.accounts, id: \.id) { account in
                Label(account.displayName, systemImage: "building.columns")
            }
            LabeledContent("Orders from Livermore", value: status.canTrade ? "On" : "Off")
        } header: {
            Text(link.accounts.count == 1 ? "Linked account" : "Linked accounts")
        } footer: {
            VStack(alignment: .leading, spacing: 4) {
                if let loaded = link.loadedAt {
                    // When this was read, in plain view next to the numbers.
                    Text("READ FROM YOUR BROKER \(loaded.formatted(date: .abbreviated, time: .shortened).uppercased())")
                        .font(.caption2.weight(.semibold)).tracking(0.6)
                }
                if !status.canTrade {
                    Text("Sending orders from Livermore isn't switched on yet. You can still see your holdings here; place orders in your brokerage app and record them in Actions.")
                }
                if let failure = link.failure { Text(failure.message).foregroundStyle(.caution) }
            }
        }

        let invested = link.holdings.filter { $0.cashEquivalent != true }
        let cash = link.holdings.filter { $0.cashEquivalent == true }
        Section("Holdings") {
            if invested.isEmpty {
                Text("No stock or fund holdings in the linked accounts.").foregroundStyle(.secondary)
            }
            ForEach(Array(invested.enumerated()), id: \.offset) { _, holding in
                HoldingRow(holding: holding, quote: session.quotes.quotes[holding.symbol.uppercased()])
            }
            if !invested.isEmpty { QuoteFreshnessLabel() }
        }
        .liveQuotes(invested.map(\.symbol))

        if !cash.isEmpty {
            Section {
                ForEach(Array(cash.enumerated()), id: \.offset) { _, holding in
                    LabeledContent(holding.symbol, value: Fmt.price(holding.marketValue ?? holding.units))
                }
            } header: {
                Text("Cash and sweep funds")
            } footer: {
                Text("Your broker classifies these as cash. They are your money, not positions you chose.")
            }
        }
    }

    private func startLink() {
        isOpeningLink = true
        linkFailure = nil
        Task {
            do throws(APIFailure) {
                let url = try await session.brokerage.connectionURL()
                #if os(iOS)
                browser = BrowserDestination(url: url)
                #else
                openURL(url)
                #endif
            } catch {
                if error == .notSignedIn { session.signOut() }
                linkFailure = error
            }
            isOpeningLink = false
        }
    }
}

/// One holding as the broker reports it, revalued on the live quote.
struct HoldingRow: View {
    let holding: BrokerHolding
    let quote: LiveQuote?

    private var price: Double? { quote?.price ?? holding.lastPrice }

    /// Gain on the live quote when there is a cost basis; otherwise the
    /// broker's own figure.
    private var openProfit: Double? {
        if let price, let cost = holding.averagePurchasePrice { return (price - cost) * holding.units }
        return holding.openPnl
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 2) {
                Text(holding.symbol).font(.headline.monospaced())
                Text("\(Fmt.shares(holding.units)) shares" + (holding.averagePurchasePrice.map { " · cost \(Fmt.price($0))" } ?? ""))
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                if let price {
                    Text(Fmt.price(price * holding.units)).font(.subheadline.monospacedDigit())
                }
                if let openProfit {
                    Text(Fmt.signedMoney(openProfit)).font(.caption.monospacedDigit()).foregroundStyle(openProfit.changeColor)
                }
            }
        }
        .accessibilityElement(children: .combine)
    }
}
