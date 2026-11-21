import LivermoreKit
import SwiftUI

/// The plan written out for the user to enter at their own broker.
///
/// Livermore sends nothing. This is the order in the words a broker's option
/// screen uses, with the steps to enter it.
struct OptionTicketView: View {
    @Environment(\.dismiss) private var dismiss
    let plan: OptionPlan

    @State private var copied = false

    var body: some View {
        let ticket = OptionTicket(plan: plan)
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: Metrics.sectionSpacing) {
                    OptionPricesDate(asOf: plan.asOf).padding(.horizontal, 4)
                    Card("Your order") {
                        ForEach(ticket.lines) { line in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(line.action).eyebrowStyle()
                                Text(line.contract).font(.title3.weight(.semibold))
                                    .fixedSize(horizontal: false, vertical: true)
                                Text("\(line.limit) per share").font(.subheadline.monospacedDigit())
                                Text(line.contractSymbol).font(.caption.monospaced()).foregroundStyle(.inkSecondary)
                                    .textSelection(.enabled)
                            }
                            .accessibilityElement(children: .combine)
                        }
                        if let requirement = ticket.requirement {
                            Notice(text: requirement, systemImage: "checklist")
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

                    Card("What this comes to") {
                        ForEach(plan.figures) { figure in
                            DetailRow(figure.label, figure.value)
                        }
                    }

                    Text("Livermore has not sent anything to your broker. The numbers are from the last close and will have moved; the broker's own order screen shows today's.")
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
        }
    }
}
