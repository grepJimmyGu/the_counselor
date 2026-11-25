import LivermoreKit
import SwiftUI

/// The plan written out for the user to enter at their own broker.
///
/// Livermore sends nothing. This is the order in the words a broker's option
/// screen uses, with the steps to enter it. Once the user has entered it,
/// a linked account's order list is how the app confirms it is in.
struct OptionTicketView: View {
    @Environment(AppSession.self) private var session
    @Environment(\.dismiss) private var dismiss
    let plan: OptionPlan

    @State private var copied = false
    /// Said when the broker's app could not be brought forward.
    @State private var openNote: String?
    @State private var check = BrokerCheck.idle

    private enum BrokerCheck: Equatable {
        case idle, reading
        case read(PlacedOrderReading)
        case failed(String)
    }

    private var link: BrokerageLink { session.brokerageLink }

    /// The app of the first linked broker Livermore knows how to open.
    private var brokerApp: BrokerApp? {
        link.accounts.lazy
            .compactMap { BrokerApp(institution: $0.institutionName, symbol: plan.symbol) }
            .first
    }

    var body: some View {
        let ticket = OptionTicket(plan: plan)
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: Metrics.sectionSpacing) {
                    OptionPricesDate(plan: plan).padding(.horizontal, 4)
                    Card("Your order") {
                        ForEach(ticket.lines) { line in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(line.action).eyebrowStyle()
                                Text(line.contract).font(.title3.weight(.semibold))
                                    .fixedSize(horizontal: false, vertical: true)
                                Text("\(line.limit) per share\(ticket.isEstimated ? " (estimate)" : "")").font(.subheadline.monospacedDigit())
                                Text(line.contractSymbol).font(.caption.monospaced()).foregroundStyle(.inkSecondary)
                                    .textSelection(.enabled)
                            }
                            .accessibilityElement(children: .combine)
                        }
                        if let requirement = ticket.requirement {
                            Notice(text: requirement, systemImage: "checklist")
                        }
                        if ticket.isEstimated {
                            Notice(text: "\(ticket.priceSource) Set your limit from the price your broker shows.", systemImage: "function")
                        }
                        #if os(iOS)
                        Button {
                            UIPasteboard.general.string = ticket.text
                            copied = true
                        } label: {
                            Label(copied ? "Copied" : "Copy the order", systemImage: copied ? "checkmark" : "doc.on.doc")
                        }
                        .buttonStyle(SecondaryButtonStyle())
                        .accessibilityIdentifier("option-copy-ticket")
                        if let app = brokerApp {
                            Button {
                                UIPasteboard.general.string = ticket.text
                                copied = true
                                open(app)
                            } label: {
                                Label("Copy and open \(app.name)", systemImage: "arrow.up.forward.app")
                            }
                            .buttonStyle(SecondaryButtonStyle())
                            .accessibilityIdentifier("option-open-broker")
                            if let openNote {
                                Text(openNote).font(.footnote).foregroundStyle(.inkSecondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        #endif
                    }

                    Card("How to enter it") {
                        ForEach(Array(ticket.steps.enumerated()), id: \.offset) { index, step in
                            HStack(alignment: .firstTextBaseline, spacing: 10) {
                                Text("\(index + 1)")
                                    .font(.footnote.weight(.bold).monospacedDigit())
                                    .frame(width: 24, height: 24)
                                    .background(Color.brand.opacity(0.12), in: Circle())
                                    .foregroundStyle(.brand)
                                Text(step).font(.subheadline).fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }

                    if link.isLinked, let contract = ticket.lines.first?.contractSymbol, !contract.isEmpty {
                        placedCard(contract: contract)
                    }

                    Card("What this comes to") {
                        ForEach(plan.figures) { figure in
                            DetailRow(figure.label, figure.value)
                        }
                    }

                    Text("Livermore has not sent anything to your broker. \(plan.isEstimated ? "The option price is an estimate, not a quote" : "The numbers are from the last close and will have moved"); the broker's own order screen shows today's.")
                        .font(.footnote).foregroundStyle(.inkSecondary)
                        .padding(.horizontal, 4)
                }
                .padding(Metrics.screenPadding)
            }
            .screenBackground()
            .navigationTitle("Take it to your broker")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .task {
                if link.status == nil { await link.refresh() }
            }
        }
    }

    /// Reads the linked account's orders for this contract. The order itself
    /// is entered at the broker; this only confirms the broker has it.
    private func placedCard(contract: String) -> some View {
        Card("After you place it") {
            Text("Livermore can't send this order, but it can read your broker's order list and tell you whether it is in.")
                .font(.subheadline).foregroundStyle(.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Button {
                checkBroker(for: contract)
            } label: {
                HStack {
                    Label(
                        check == .reading ? "Reading your orders…" : "Check my broker for this order",
                        systemImage: "checkmark.seal"
                    )
                    if check == .reading { ProgressView().padding(.leading, 4) }
                }
            }
            .buttonStyle(SecondaryButtonStyle())
            .disabled(check == .reading)
            .accessibilityIdentifier("option-check-broker")

            switch check {
            case .idle, .reading:
                EmptyView()
            case .read(let reading):
                Notice(text: reading.headline, systemImage: Self.symbol(for: reading.outcome), tint: Self.tint(for: reading.outcome))
                    .accessibilityIdentifier("option-check-result")
                Text(reading.detail).font(.footnote).foregroundStyle(.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            case .failed(let message):
                Notice(text: message, systemImage: "exclamationmark.triangle.fill", tint: .caution)
            }
        }
    }

    private static func symbol(for outcome: PlacedOrderReading.Outcome) -> String {
        switch outcome {
        case .placed, .filled: "checkmark.circle.fill"
        case .differs: "exclamationmark.triangle.fill"
        case .ended: "xmark.circle.fill"
        case .unclear: "questionmark.circle.fill"
        case .notFound: "magnifyingglass"
        }
    }

    private static func tint(for outcome: PlacedOrderReading.Outcome) -> Color {
        switch outcome {
        case .placed, .filled: .gain
        case .differs, .ended: .caution
        case .unclear, .notFound: .inkSecondary
        }
    }

    private func checkBroker(for contract: String) {
        check = .reading
        Task {
            do throws(APIFailure) {
                let lookup = try await session.brokerage.optionOrders(contract: contract)
                check = .read(PlacedOrderReading(plan: plan, lookup: lookup) { link.account(id: $0)?.displayName })
            } catch {
                if error == .notSignedIn { session.signOut() }
                check = .failed(error.message)
            }
        }
    }

    #if os(iOS)
    /// Brings the broker's own app forward. Only its app: if the phone would
    /// open a web page instead, nothing opens and the note says so.
    private func open(_ app: BrokerApp) {
        openNote = nil
        Task {
            let opened = await UIApplication.shared.open(app.url, options: [.universalLinksOnly: true])
            if !opened {
                openNote = "Couldn't open \(app.name) from here. The order is copied; open \(app.name) yourself."
            }
        }
    }
    #endif
}
