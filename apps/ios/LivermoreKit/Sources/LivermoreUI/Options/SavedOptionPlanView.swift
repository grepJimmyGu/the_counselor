import LivermoreKit
import SwiftUI

/// One row of the Strategies tab's option plans.
struct SavedOptionPlanRow: View {
    let saved: SavedOptionPlan

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "arrow.triangle.branch")
                .font(.body.weight(.medium)).foregroundStyle(.brand)
                .frame(width: 40, height: 40)
                .background(Color.brand.opacity(0.10), in: RoundedRectangle(cornerRadius: 11, style: .continuous))
            if let plan = saved.plan {
                VStack(alignment: .leading, spacing: 4) {
                    Text(plan.title).font(.subheadline.weight(.semibold)).lineLimit(2)
                    HStack(spacing: 6) {
                        Tag(plan.strategy.name, tint: .brand)
                        Text("\(plan.paysNow ? "Pay" : "Receive") \(OptionText.dollars(plan.cashNow))")
                            .font(.caption.monospacedDigit()).foregroundStyle(.inkSecondary)
                    }
                }
            } else {
                // Saved by a newer version of Livermore than this one.
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(saved.symbol) option plan").font(.subheadline.weight(.semibold))
                    Text("Update the app to open this plan.").font(.caption).foregroundStyle(.inkSecondary)
                }
            }
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
    }
}

/// A saved plan, as it was when it was built.
struct SavedOptionPlanView: View {
    @Environment(AppSession.self) private var session
    @Environment(\.dismiss) private var dismiss
    let saved: SavedOptionPlan
    /// Called after the plan is deleted, so the list can drop it.
    var onDelete: () -> Void = {}

    @State private var isShowingTicket = false
    @State private var isConfirmingDelete = false
    @State private var error: String?

    var body: some View {
        Group {
            if let plan = saved.plan {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: Metrics.sectionSpacing) {
                        if session.isDemo { SampleDataNotice().padding(.horizontal, 4) }
                        OptionPricesDate(plan: plan).padding(.horizontal, 4)
                        OptionHeadlineCard(plan: plan)
                        OptionFiguresGrid(plan: plan)
                        PayoffCard(plan: plan)
                        Card {
                            Notice(text: "These are the prices from the day you built the plan. To see today's, build it again from \(plan.symbol)'s page.")
                            if let caution = plan.caution { Notice(text: caution) }
                            if let error { Text(error).font(.footnote).foregroundStyle(.loss) }
                        }
                    }
                    .padding(Metrics.screenPadding)
                }
                .bottomBar {
                    Button {
                        isShowingTicket = true
                    } label: {
                        Label("Take it to my broker", systemImage: "arrow.up.forward.app")
                    }
                    .buttonStyle(PrimaryButtonStyle())
                }
                .sheet(isPresented: $isShowingTicket) { OptionTicketView(plan: plan) }
                .navigationTitle(plan.symbol)
            } else {
                ContentUnavailableView {
                    Label("This plan needs a newer app", systemImage: "arrow.down.app")
                } description: {
                    Text("It was saved by a newer version of Livermore. Update the app to open it.")
                }
            }
        }
        .screenBackground()
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button("Delete", systemImage: "trash", role: .destructive) { isConfirmingDelete = true }
            }
        }
        .confirmationDialog("Delete this plan?", isPresented: $isConfirmingDelete, titleVisibility: .visible) {
            Button("Delete plan", role: .destructive) { Task { await delete() } }
        } message: {
            Text("This removes it from Livermore. It does not change anything at your broker.")
        }
    }

    private func delete() async {
        do throws(APIFailure) {
            try await session.options.delete(id: saved.id)
            onDelete()
            dismiss()
        } catch {
            if error == .notSignedIn { session.signOut() } else { self.error = error.message }
        }
    }
}
