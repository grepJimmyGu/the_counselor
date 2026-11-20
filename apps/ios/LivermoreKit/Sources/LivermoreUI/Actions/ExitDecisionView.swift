import LivermoreKit
import SwiftUI

#if os(iOS)
import UIKit
#endif

/// One exit a strategy signalled: what the rule says, the evidence, and the
/// three things the user can do about it — sell through their broker, record
/// a sale they made elsewhere, or keep the position.
struct ExitDecisionView: View {
    @Environment(AppSession.self) private var session
    @Environment(\.dismiss) private var dismiss
    let exit: UnresolvedExit

    @State private var isSelling = false
    @State private var isRecording = false
    @State private var isHolding = false
    @State private var isConfirmingHold = false
    @State private var failure: APIFailure?
    @State private var copied = false
    /// Set once an order went to the broker, so the sale can be recorded
    /// without asking the user to retype it.
    @State private var sentOrder: OrderPreview?

    private var link: BrokerageLink { session.brokerageLink }
    private var holding: BrokerHolding? { link.holding(of: exit.symbol) }
    private var quote: LiveQuote? { session.quotes.quotes[exit.symbol.uppercased()] }

    private var exactShares: Double? {
        if case .exact(let shares) = exit.quantity, shares > 0 { shares } else { nil }
    }

    private var ticketLine: String {
        exactShares.map { "SELL \(Fmt.shares($0)) \(exit.symbol)" } ?? "SELL \(exit.symbol)"
    }

    var body: some View {
        List {
            if session.isDemo { SampleDataNotice() }

            Section {
                VStack(alignment: .leading, spacing: 6) {
                    Text("\(exit.barDate ?? exit.signaledAt.map { String($0.prefix(10)) } ?? "—") · \(exit.strategyTitle)".uppercased())
                        .font(.caption2.weight(.semibold)).tracking(0.8).foregroundStyle(.secondary)
                    Text("\(exit.symbol) — \(exit.headline)").font(.title3.weight(.semibold))
                }
            }

            Section {
                switch exit.quantity {
                case .exact:
                    Text(ticketLine).font(.title2.weight(.bold).monospaced())
                case .ambiguous(let ifSold, let ifNot):
                    Text("SELL — \(exit.symbol)").font(.title2.weight(.bold).monospaced())
                    Text("You haven't told Livermore what you sold at the earlier tier, so it won't state a share count.")
                        .font(.subheadline).foregroundStyle(.secondary)
                    LabeledContent("If that tier was sold", value: "\(Fmt.shares(ifSold)) shares")
                    LabeledContent("If it was not", value: "up to \(Fmt.shares(ifNot)) shares")
                }
                LabeledContent(exit.tierLabel ?? "Exit tier", value: exit.action == "sell_all" ? "Sell all" : "Partial exit")
                #if os(iOS)
                Button(copied ? "Copied" : "Copy this ticket", systemImage: copied ? "checkmark" : "doc.on.doc") {
                    UIPasteboard.general.string = ticketText
                    copied = true
                }
                .font(.subheadline)
                #endif
            } header: {
                Text("What the rule says")
            }

            Section {
                LabeledContent("Price that met the rule") {
                    Text(Fmt.price(exit.price) + (exit.pctChange.map { " (\(Fmt.percent($0, signed: true)))" } ?? ""))
                        .monospacedDigit()
                }
                LabeledContent("Your entry", value: Fmt.price(exit.entryPrice))
                LabeledContent("You hold", value: "\(Fmt.shares(exit.sharesRemaining)) of \(Fmt.shares(exit.sharesInitial)) shares")
                if let quote {
                    LabeledContent("Price now") {
                        VStack(alignment: .trailing, spacing: 2) {
                            LivePriceText(price: quote.price)
                            Text(Fmt.percent(quote.price / exit.entryPrice - 1, signed: true) + " from entry")
                                .font(.caption).foregroundStyle((quote.price - exit.entryPrice).changeColor)
                        }
                    }
                }
            } header: {
                Text("The evidence")
            } footer: {
                VStack(alignment: .leading, spacing: 4) {
                    Text(exit.priceCaveat)
                    if quote != nil { QuoteFreshnessLabel() }
                }
            }

            decisionSection
        }
        .screenBackground()
        .navigationTitle(exit.symbol)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .liveQuotes([exit.symbol])
        .task { if link.status == nil { await link.refresh() } }
        .sheet(isPresented: $isSelling) {
            if let holding {
                OrderTicketView(
                    symbol: exit.symbol,
                    side: .sell(holding: holding, suggested: exactShares),
                    reason: "\(exit.headline) — \(exit.strategyTitle)"
                ) { _, preview in
                    sentOrder = preview
                }
            }
        }
        .sheet(isPresented: $isRecording) {
            RecordSaleView(exit: exit, suggestedShares: sentOrder?.units ?? exactShares, priceNow: quote?.price) {
                dismiss()
            }
        }
        .confirmationDialog("Keep \(exit.symbol)?", isPresented: $isConfirmingHold, titleVisibility: .visible) {
            Button("I'm keeping it") { hold() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Livermore records that you saw this signal and chose to hold. It stops asking about this tier; later tiers still alert you.")
        }
    }

    @ViewBuilder
    private var decisionSection: some View {
        Section {
            if sentOrder != nil {
                Label("Your order went to your broker.", systemImage: "paperplane.fill").foregroundStyle(.gain)
                Button("Record this sale", systemImage: "square.and.pencil") { isRecording = true }
                    .fontWeight(.semibold)
                    .accessibilityIdentifier("record-sale")
            } else {
                if link.canTrade, let holding, exactShares != nil {
                    Button {
                        isSelling = true
                    } label: {
                        Label("Sell at \(link.account(id: holding.accountId)?.displayName ?? "your broker")", systemImage: "arrow.up.right.circle.fill")
                            .fontWeight(.semibold)
                    }
                    .accessibilityIdentifier("sell-at-broker")
                }
                Button("I sold it — record the sale", systemImage: "square.and.pencil") { isRecording = true }
                    .accessibilityIdentifier("record-sale")
                Button {
                    isConfirmingHold = true
                } label: {
                    HStack {
                        Label("I'm keeping it", systemImage: "hand.raised")
                        Spacer()
                        if isHolding { ProgressView() }
                    }
                }
                .disabled(isHolding)
                .accessibilityIdentifier("hold-position")
            }
        } header: {
            Text("Your decision")
        } footer: {
            VStack(alignment: .leading, spacing: 4) {
                if let failure { Text(failure.message).foregroundStyle(.loss) }
                Text(brokerNote)
            }
        }
    }

    /// Why the broker button is or isn't there.
    private var brokerNote: String {
        if sentOrder != nil {
            return "Recording the sale tells Livermore the position is smaller, so it stops watching shares you no longer hold."
        }
        guard let status = link.status else { return "Nothing is sold unless you send the order yourself." }
        if !status.isLinked {
            return "Link your brokerage from the Actions tab to send this order from here. Until then, place it in your brokerage app and record it."
        }
        if !status.canTrade {
            return "Sending orders from Livermore isn't switched on yet. Place this in your brokerage app, then record it here."
        }
        if holding == nil {
            return "Your linked accounts don't show \(exit.symbol). If you hold it elsewhere, sell it there and record it here."
        }
        if exactShares == nil {
            return "The share count isn't certain, so there's no one-tap order. Decide the size, sell in your brokerage app, and record it."
        }
        return "You'll see your broker's numbers for the order before anything is sent."
    }

    private var ticketText: String {
        let tier = exit.tierLabel ?? "Exit tier"
        let move = exit.pctChange.map { " (\(Fmt.percent($0, signed: true)) from entry)" } ?? ""
        return "\(ticketLine)\n\(tier)\(move) — \(exit.strategyTitle)\n\(exit.priceCaveat)"
    }

    private func hold() {
        isHolding = true
        failure = nil
        Task {
            do throws(APIFailure) {
                try await session.inbox.hold(exit)
                dismiss()
            } catch {
                if error == .notSignedIn { session.signOut() }
                failure = error
            }
            isHolding = false
        }
    }
}

/// "I sold" — the user's own fill, which is what Livermore reduces the
/// tracked position by.
struct RecordSaleView: View {
    @Environment(AppSession.self) private var session
    @Environment(\.dismiss) private var dismiss
    let exit: UnresolvedExit
    let suggestedShares: Double?
    let priceNow: Double?
    let onRecorded: () -> Void

    @State private var shares: Double?
    @State private var fillPrice: Double?
    @State private var isSaving = false
    @State private var failure: APIFailure?

    private var problem: String? {
        guard let shares, shares > 0 else { return "Enter how many shares you sold." }
        if shares > exit.sharesRemaining + 1e-6 {
            return "Livermore is tracking \(Fmt.shares(exit.sharesRemaining)) shares on this position."
        }
        if let fillPrice, fillPrice <= 0 { return "Enter the price you sold at, or leave it empty." }
        return nil
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    LabeledContent("Shares sold") {
                        TextField("0", value: $shares, format: .number.precision(.fractionLength(0...4)))
                            .multilineTextAlignment(.trailing)
                            #if os(iOS)
                            .keyboardType(.decimalPad)
                            #endif
                            .accessibilityIdentifier("sale-shares")
                    }
                    LabeledContent("Price you got") {
                        TextField(Fmt.price(exit.price), value: $fillPrice, format: .number.precision(.fractionLength(0...4)))
                            .multilineTextAlignment(.trailing)
                            #if os(iOS)
                            .keyboardType(.decimalPad)
                            #endif
                            .accessibilityIdentifier("sale-price")
                    }
                } header: {
                    Text("\(exit.symbol) · \(exit.tierLabel ?? "Exit tier")")
                } footer: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Use the fill from your broker. Left empty, the price that met the rule (\(Fmt.price(exit.price))) is recorded instead.")
                        if let problem, shares != nil { Text(problem).foregroundStyle(.caution) }
                        if let failure { Text(failure.message).foregroundStyle(.loss) }
                    }
                }

                Section {
                    Button(action: save) {
                        HStack {
                            Text(isSaving ? "Recording…" : "Record the sale").fontWeight(.semibold)
                            Spacer()
                            if isSaving { ProgressView() }
                        }
                    }
                    .disabled(problem != nil || isSaving)
                    .accessibilityIdentifier("confirm-sale")
                } footer: {
                    Text("This updates Livermore's record of your position. It does not place an order.")
                }
            }
            .screenBackground()
            .navigationTitle("Record a sale")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            }
            .onAppear {
                if shares == nil { shares = suggestedShares.map { min($0, exit.sharesRemaining) } }
            }
        }
    }

    private func save() {
        guard problem == nil, let shares else { return }
        isSaving = true
        failure = nil
        Task {
            do throws(APIFailure) {
                try await session.inbox.confirm(exit, sharesSold: shares, fillPrice: fillPrice)
                dismiss()
                onRecorded()
            } catch {
                if error == .notSignedIn { session.signOut() }
                failure = error
            }
            isSaving = false
        }
    }
}
