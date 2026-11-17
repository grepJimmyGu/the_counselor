import LivermoreKit
import SwiftUI

/// One order, from "how much" to the broker's receipt.
///
/// Three steps, and no way to skip the middle one: fill it in, see the
/// broker's own numbers for it, then send it. Changing anything after pricing
/// discards the price, so what is sent is always what was shown.
struct OrderTicketView: View {
    enum Side: Equatable {
        /// Sell from a holding at the broker; `suggested` is what the rule
        /// asked for, capped at what is held.
        case sell(holding: BrokerHolding, suggested: Double?)
        case buy(suggestedDollars: Double?)
    }

    @Environment(AppSession.self) private var session
    @Environment(\.dismiss) private var dismiss

    let symbol: String
    let side: Side
    /// Why this order is being placed, shown above it ("Stop tier reached…").
    var reason: String?
    /// Called once the broker has accepted the order.
    var onSent: (OrderReceipt, OrderPreview) -> Void = { _, _ in }

    fileprivate enum Phase: Equatable {
        case editing
        case pricing
        case priced(OrderPreview)
        case sending(OrderPreview)
        case sent(OrderReceipt, OrderPreview)
    }

    @State private var amount: Double?
    @State private var accountID = ""
    @State private var phase: Phase = .editing
    @State private var failure: APIFailure?
    @State private var isConfirming = false
    @FocusState private var amountFocused: Bool

    private var link: BrokerageLink { session.brokerageLink }
    private var isSell: Bool { if case .sell = side { true } else { false } }

    private var heldShares: Double? {
        if case .sell(let holding, _) = side { holding.units } else { nil }
    }

    private var draft: OrderDraft {
        OrderDraft(
            accountID: accountID, symbol: symbol,
            size: isSell ? .sell(shares: amount ?? 0) : .buy(dollars: amount ?? 0)
        )
    }

    /// Why the order can't be priced, or nil when it can.
    private var problem: String? {
        if let problem = draft.problem { return problem }
        if let heldShares, let amount, amount > heldShares {
            return "You hold \(Fmt.shares(heldShares)) shares of \(symbol) in this account."
        }
        return nil
    }

    private var accountName: String {
        link.account(id: accountID)?.displayName ?? "your broker"
    }

    private var orderLine: String {
        guard let amount else { return "\(isSell ? "SELL" : "BUY") \(symbol)" }
        return isSell
            ? "SELL \(Fmt.shares(amount)) \(symbol)"
            : "BUY \(Fmt.wholeMoney(amount)) of \(symbol)"
    }

    var body: some View {
        NavigationStack {
            Form {
                if session.isDemo {
                    Section { SampleDataNotice() } footer: { Text("This is the sample account. Nothing is sent to any broker.") }
                }

                if case .sent(let receipt, let preview) = phase {
                    sentSection(receipt, preview)
                } else {
                    orderSection
                    if case .priced(let preview) = phase { pricedSection(preview) }
                    if case .sending(let preview) = phase { pricedSection(preview) }
                    actionSection
                }
            }
            .navigationTitle(isSell ? "Sell \(symbol)" : "Buy \(symbol)")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Done") { amountFocused = false }
                }
            }
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(phase.isSent ? "Close" : "Cancel") { dismiss() }
                }
            }
            .confirmationDialog(
                "Send this order to \(accountName)?",
                isPresented: $isConfirming,
                titleVisibility: .visible
            ) {
                Button("Send order — \(orderLine)") { send() }
                Button("Not yet", role: .cancel) {}
            } message: {
                Text("\(orderLine) at the market price, good for today. This places a real trade in your brokerage account.")
            }
            .liveQuotes([symbol])
            .task { await prepare() }
            .interactiveDismissDisabled(phase.isBusy)
        }
    }

    // MARK: Sections

    private var orderSection: some View {
        Section {
            if let reason {
                Text(reason).font(.subheadline).foregroundStyle(.secondary)
            }
            if isSell {
                LabeledContent("From", value: accountName)
            } else if link.accounts.count > 1 {
                Picker("Account", selection: $accountID) {
                    ForEach(link.accounts, id: \.id) { Text($0.displayName).tag($0.id) }
                }
            } else {
                LabeledContent("Account", value: accountName)
            }

            LabeledContent(isSell ? "Shares to sell" : "Amount to invest") {
                TextField(
                    isSell ? "0" : "$0",
                    value: $amount,
                    format: isSell ? .number.precision(.fractionLength(0...4)) : .number.precision(.fractionLength(0...2))
                )
                .multilineTextAlignment(.trailing)
                #if os(iOS)
                .keyboardType(.decimalPad)
                #endif
                .focused($amountFocused)
                .accessibilityIdentifier("order-amount")
            }

            if let quote = session.quotes.quotes[symbol.uppercased()] {
                LabeledContent("Last price") {
                    VStack(alignment: .trailing, spacing: 2) {
                        LivePriceText(price: quote.price)
                        if let amount, amount > 0 {
                            Text(isSell
                                ? "about \(Fmt.wholeMoney(amount * quote.price))"
                                : "about \(Fmt.shares((amount / quote.price * 10_000).rounded(.down) / 10_000)) shares")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
        } header: {
            Text("Market order · good for today")
        } footer: {
            VStack(alignment: .leading, spacing: 4) {
                if let heldShares {
                    Text("You hold \(Fmt.shares(heldShares)) shares in this account.")
                }
                QuoteFreshnessLabel()
            }
        }
        .onChange(of: amount) { _, _ in invalidatePrice() }
        .onChange(of: accountID) { _, _ in invalidatePrice() }
    }

    private func pricedSection(_ preview: OrderPreview) -> some View {
        Section {
            Text(orderLine).font(.headline.monospaced())
            if let units = preview.units, !isSell {
                LabeledContent("Shares", value: Fmt.shares(units))
            }
            LabeledContent("Estimated commission", value: Fmt.price(preview.estimatedCommission))
            LabeledContent("Cash after", value: Fmt.price(preview.remainingCash))
        } header: {
            Text("Your broker's numbers")
        } footer: {
            Text("These are your broker's own figures for this order. A market order fills at the price available when it reaches the exchange, which can differ from the last price above.")
        }
    }

    private var actionSection: some View {
        Section {
            switch phase {
            case .editing, .pricing:
                Button(action: price) {
                    HStack {
                        Text(phase == .pricing ? "Asking your broker…" : "See the cost before sending")
                        Spacer()
                        if phase == .pricing { ProgressView() }
                    }
                }
                .disabled(problem != nil || phase == .pricing)
                .accessibilityIdentifier("price-order")
            case .priced, .sending:
                Button {
                    isConfirming = true
                } label: {
                    HStack {
                        Text(phase.isBusy ? "Sending…" : "Send order to \(accountName)")
                            .fontWeight(.semibold)
                        Spacer()
                        if phase.isBusy { ProgressView() }
                    }
                }
                .disabled(phase.isBusy)
                .accessibilityIdentifier("send-order")
            case .sent:
                EmptyView()
            }
        } footer: {
            VStack(alignment: .leading, spacing: 4) {
                if let failure {
                    Text(failure.message).foregroundStyle(.red)
                } else if let problem, amount != nil {
                    Text(problem).foregroundStyle(.orange)
                }
                Text("Livermore sends the order to your broker and nothing else. It never trades on its own.")
            }
        }
    }

    private func sentSection(_ receipt: OrderReceipt, _ preview: OrderPreview) -> some View {
        Section {
            Label("Order sent to \(accountName)", systemImage: "checkmark.circle.fill")
                .font(.headline).foregroundStyle(.green)
            Text(orderLine).font(.subheadline.monospaced())
            if let status = receipt.status { LabeledContent("Broker status", value: status) }
            if let id = receipt.brokerageOrderId { LabeledContent("Order reference", value: id) }
        } footer: {
            Text("It will appear in your brokerage account as your broker fills it. The fill price is your broker's — check it there.")
        }
    }

    // MARK: Actions

    private func prepare() async {
        if link.status == nil { await link.refresh() }
        switch side {
        case .sell(let holding, let suggested):
            accountID = holding.accountId
            if amount == nil { amount = min(suggested ?? holding.units, holding.units) }
        case .buy(let dollars):
            if accountID.isEmpty { accountID = link.accounts.first?.id ?? "" }
            if amount == nil { amount = dollars }
        }
    }

    /// A price describes one order. Change the order and it no longer does.
    private func invalidatePrice() {
        if case .priced = phase { phase = .editing }
        failure = nil
    }

    private func price() {
        guard problem == nil else { return }
        amountFocused = false
        failure = nil
        phase = .pricing
        let draft = draft
        Task {
            do throws(APIFailure) {
                let preview = try await session.brokerage.preview(draft)
                // Only if the order on screen is still the one that was priced.
                if phase == .pricing, draft == self.draft { phase = .priced(preview) }
            } catch {
                if error == .notSignedIn { session.signOut() }
                failure = error
                phase = .editing
            }
        }
    }

    private func send() {
        guard case .priced(let preview) = phase else { return }
        failure = nil
        phase = .sending(preview)
        Task {
            do throws(APIFailure) {
                let receipt = try await session.brokerage.place(preview)
                phase = .sent(receipt, preview)
                onSent(receipt, preview)
                await link.refresh()
            } catch {
                if error == .notSignedIn { session.signOut() }
                failure = error
                // The old price may be stale or spent; make them price again
                // rather than retry a send that just failed.
                phase = .editing
            }
        }
    }
}

private extension OrderTicketView.Phase {
    var isSent: Bool { if case .sent = self { true } else { false } }
    var isBusy: Bool {
        switch self {
        case .pricing, .sending: true
        default: false
        }
    }
}
