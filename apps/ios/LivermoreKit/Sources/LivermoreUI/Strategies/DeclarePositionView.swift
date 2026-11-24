import LivermoreKit
import SwiftUI

/// "I hold this" — a real position the user wants watched against a
/// strategy's stop and targets. Livermore never assumes ownership; it tracks
/// what it is told.
struct DeclarePositionView: View {
    @Environment(AppSession.self) private var session
    @Environment(\.dismiss) private var dismiss
    let strategy: SavedStrategy
    /// Filled in when the screen follows an order the user just sent.
    var presetSymbol: String?
    let onDeclared: () -> Void

    @State private var symbol = ""
    @State private var shares: Double?
    @State private var entryPrice: Double?
    @State private var isSaving = false
    @State private var failure: APIFailure?

    private var link: BrokerageLink { session.brokerageLink }
    private var universe: [String] { strategy.universe }

    /// Holdings at the user's broker that this strategy trades — one tap
    /// fills the form with the broker's own share count and cost.
    private var matchingHoldings: [BrokerHolding] {
        let wanted = Set(universe.map { $0.uppercased() })
        return link.holdings.filter { wanted.contains($0.symbol.uppercased()) && $0.cashEquivalent != true && $0.units > 0 }
    }

    private var problem: String? {
        if symbol.trimmingCharacters(in: .whitespaces).isEmpty { return "Enter the ticker." }
        guard let shares, shares > 0 else { return "Enter how many shares you hold." }
        guard let entryPrice, entryPrice > 0 else { return "Enter the average price you paid." }
        return nil
    }

    var body: some View {
        NavigationStack {
            Form {
                if !matchingHoldings.isEmpty {
                    Section {
                        ForEach(Array(matchingHoldings.enumerated()), id: \.offset) { _, holding in
                            Button {
                                symbol = holding.symbol.uppercased()
                                shares = holding.units
                                entryPrice = holding.averagePurchasePrice
                            } label: {
                                LabeledContent {
                                    Text("\(Fmt.shares(holding.units)) shares" + (holding.averagePurchasePrice.map { " at \(Fmt.price($0))" } ?? ""))
                                } label: {
                                    Text(holding.symbol).font(.headline.monospaced())
                                }
                            }
                            .foregroundStyle(.primary)
                        }
                    } header: {
                        Text("From your brokerage")
                    } footer: {
                        Text("Tap one to use your broker's share count and cost basis.")
                    }
                }

                Section {
                    if universe.count > 1 {
                        Picker("Ticker", selection: $symbol) {
                            ForEach(universe, id: \.self) { Text($0).tag($0) }
                        }
                    } else {
                        LabeledContent("Ticker") {
                            TextField("AAPL", text: $symbol)
                                .multilineTextAlignment(.trailing)
                                .autocorrectionDisabled()
                                #if os(iOS)
                                .textInputAutocapitalization(.characters)
                                .keyboardType(.asciiCapable)
                                #endif
                        }
                    }
                    LabeledContent("Shares") {
                        TextField("0", value: $shares, format: .number.precision(.fractionLength(0...4)))
                            .multilineTextAlignment(.trailing)
                            #if os(iOS)
                            .keyboardType(.decimalPad)
                            #endif
                            .accessibilityIdentifier("declare-shares")
                    }
                    LabeledContent("Average price paid") {
                        TextField("$0.00", value: $entryPrice, format: .number.precision(.fractionLength(0...4)))
                            .multilineTextAlignment(.trailing)
                            #if os(iOS)
                            .keyboardType(.decimalPad)
                            #endif
                            .accessibilityIdentifier("declare-price")
                    }
                } header: {
                    Text("The position you hold")
                } footer: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Stops and targets are measured from the price you paid, so use your real average cost.")
                        if let failure { Text(failure.message).foregroundStyle(.loss) }
                    }
                }

                Section {
                    Button(action: save) {
                        HStack {
                            Text(isSaving ? "Saving…" : "Track this position").fontWeight(.semibold)
                            Spacer()
                            if isSaving { ProgressView() }
                        }
                    }
                    .disabled(problem != nil || isSaving)
                    .accessibilityIdentifier("declare-position")
                } footer: {
                    Text("Livermore watches it against “\(strategy.title)” and puts an action in your inbox when a level is reached. It does not place any order.")
                }
            }
            .screenBackground()
            .navigationTitle("Track a position")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            }
            .task {
                if symbol.isEmpty { symbol = (presetSymbol ?? universe.first ?? "").uppercased() }
                if link.status == nil { await link.refresh() }
            }
        }
    }

    private func save() {
        guard problem == nil, let shares, let entryPrice else { return }
        isSaving = true
        failure = nil
        Task {
            do throws(APIFailure) {
                try await session.actions.declarePosition(
                    strategyID: strategy.id, symbol: symbol.trimmingCharacters(in: .whitespaces),
                    shares: shares, entryPrice: entryPrice
                )
                dismiss()
                onDeclared()
            } catch {
                if error == .notSignedIn { session.signOut() }
                failure = error
            }
            isSaving = false
        }
    }
}
