import LivermoreKit
import SwiftUI

/// Step two of the options builder: the plan, already filled in.
///
/// The app chooses a starting expiry and strike so there is a result on
/// screen before the user has decided anything. Every control below changes
/// the same plan in place, and the numbers and the chart follow.
struct OptionPlanView: View {
    @Environment(AppSession.self) private var session
    let symbol: String
    let strategy: OptionStrategy
    /// The default expiry's chain, if the screen before had already loaded it.
    var firstChain: OptionChain?

    @State private var draft: OptionPlanDraft?
    @State private var failure: String?
    /// The expiry being fetched, so its chip can show it while the old plan stays up.
    @State private var loadingExpiration: String?
    @State private var notice: String?
    @State private var isShowingTicket = false
    @State private var savedPlan: OptionPlan?
    @State private var isSaving = false
    @State private var saveError: String?

    var body: some View {
        Group {
            if let draft {
                content(draft)
            } else if let failure {
                ContentUnavailableView {
                    Label("No plan to show", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(failure)
                } actions: {
                    Button("Try again") { Task { await start() } }.buttonStyle(.borderedProminent)
                }
            } else {
                ScrollView {
                    VStack(spacing: Metrics.sectionSpacing) {
                        Card { SkeletonBlock(height: 70) }
                        Card { SkeletonBlock(height: 120) }
                        Card { SkeletonBlock(height: 220) }
                    }
                    .padding(Metrics.screenPadding)
                }
            }
        }
        .screenBackground()
        .navigationTitle("\(symbol) · \(strategy.name)")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task {
            if draft == nil { await start() }
            await keepCurrent()
        }
        .sheet(isPresented: $isShowingTicket) {
            if let draft { OptionTicketView(plan: draft.plan) }
        }
    }

    // MARK: Loading

    private func start() async {
        failure = nil
        if let firstChain, apply(firstChain, near: nil) { return }
        await load(expiration: nil)
    }

    /// Puts `chain` on screen. False when it has no contract this strategy can use.
    @discardableResult
    private func apply(_ chain: OptionChain, near strike: Double?) -> Bool {
        guard let next = OptionPlanDraft(
            strategy: strategy, chain: chain, near: strike, contracts: draft?.contracts ?? 1
        ) else {
            let kind = strategy.optionKind == .call ? "calls" : "puts"
            let message = "There are no \(kind) to choose from for \(OptionText.day(chain.expiration))."
            if draft == nil { failure = message } else { notice = message }
            return false
        }
        draft = next
        notice = nil
        return true
    }

    private func load(expiration: String?) async {
        loadingExpiration = expiration
        defer { loadingExpiration = nil }
        do throws(APIFailure) {
            let chain = try await session.options.chain(symbol, expiration: expiration)
            apply(chain, near: draft?.strike)
        } catch {
            if error == .notSignedIn {
                session.signOut()
            } else if draft == nil {
                failure = OptionsService.message(for: error)
            } else {
                notice = OptionsService.message(for: error)
            }
        }
    }

    /// How often the plan on screen is priced again.
    static let refreshEvery: Duration = .seconds(300)

    /// Prices the plan again every five minutes while the screen is open, so
    /// the estimate follows the stock. The strike, the expiry and the number
    /// of contracts stay as chosen. A look that fails keeps what is there.
    private func keepCurrent() async {
        while !Task.isCancelled {
            try? await Task.sleep(for: Self.refreshEvery)
            // Not under an order ticket, whose limit the user may be copying,
            // and not across an expiry change already under way.
            guard !Task.isCancelled, !isShowingTicket, loadingExpiration == nil, let current = draft else { continue }
            guard let chain = try? await session.options.chain(symbol, expiration: current.chain.expiration),
                  self.draft?.chain.expiration == chain.expiration, !isShowingTicket,
                  let next = OptionPlanDraft(
                      strategy: strategy, chain: chain, near: self.draft?.strike, contracts: self.draft?.contracts ?? 1
                  )
            else { continue }
            self.draft = next
        }
    }

    // MARK: The plan

    private func content(_ draft: OptionPlanDraft) -> some View {
        let plan = draft.plan
        return ScrollView {
            LazyVStack(alignment: .leading, spacing: Metrics.sectionSpacing) {
                if session.isDemo { SampleDataNotice().padding(.horizontal, 4) }
                OptionPricesDate(plan: plan).padding(.horizontal, 4)
                OptionHeadlineCard(plan: plan)
                OptionFiguresGrid(plan: plan)
                // The controls sit between the numbers and the chart, so both
                // can be watched while a strike or an expiry is changed.
                controls(draft)
                PayoffCard(plan: plan, impliedRange: draft.chain.impliedRange)
                quoteCard(draft, plan)
            }
            .padding(Metrics.screenPadding)
            .animation(.snappy(duration: 0.2), value: plan)
        }
        .bottomBar {
            if let saveError {
                Text(saveError).font(.footnote).foregroundStyle(.loss)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack(spacing: 10) {
                Button {
                    isShowingTicket = true
                } label: {
                    Label("Take it to my broker", systemImage: "arrow.up.forward.app")
                }
                .buttonStyle(PrimaryButtonStyle())
                .accessibilityIdentifier("option-ticket")

                Button {
                    Task { await save(plan) }
                } label: {
                    if savedPlan == plan {
                        Label("Saved", systemImage: "checkmark")
                    } else {
                        Label(isSaving ? "Saving…" : "Save", systemImage: "bookmark")
                    }
                }
                .buttonStyle(SecondaryButtonStyle())
                .disabled(isSaving || savedPlan == plan)
                .frame(maxWidth: 130)
                .accessibilityIdentifier("option-save")
            }
        }
    }

    private func controls(_ draft: OptionPlanDraft) -> some View {
        let chain = draft.chain
        let quick = chain.quickExpirations
        // An expiry picked from the full list joins the row so it stays visible.
        let chips = quick.contains { $0.date == chain.expiration } ? quick : quick + [chain.selected].compactMap { $0 }
        let lastIndex = draft.quotes.count - 1
        return Card("Change it") {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    TermButton(term: .expiry).font(.subheadline.weight(.semibold))
                    Spacer()
                    Menu {
                        ForEach(chain.expirations, id: \.date) { expiration in
                            Button(expiration.label) { pick(expiration.date) }
                        }
                    } label: {
                        Label("All dates", systemImage: "calendar").font(.footnote.weight(.semibold))
                    }
                    .accessibilityIdentifier("option-all-dates")
                }
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(chips, id: \.date) { expiration in
                            let isSelected = expiration.date == chain.expiration
                            Button {
                                pick(expiration.date)
                            } label: {
                                HStack(spacing: 6) {
                                    if loadingExpiration == expiration.date { ProgressView().controlSize(.mini) }
                                    Text(expiration.label)
                                }
                                .font(.footnote.weight(.semibold))
                                .padding(.horizontal, 12).frame(minHeight: 36)
                                .foregroundStyle(isSelected ? Color.white : .primary)
                                .background(isSelected ? Color.brand : Color.well, in: Capsule())
                            }
                            .buttonStyle(.plain)
                            .accessibilityAddTraits(isSelected ? .isSelected : [])
                        }
                    }
                }
                if let notice {
                    Text(notice).font(.footnote).foregroundStyle(.caution)
                }
            }

            Divider()

            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline) {
                    TermButton(term: .strike).font(.subheadline.weight(.semibold))
                    Spacer()
                    Text("\(OptionText.strike(draft.strike)) · \(draft.strikeDistance)")
                        .font(.subheadline.monospacedDigit()).foregroundStyle(.inkSecondary)
                        .accessibilityIdentifier("option-strike-value")
                }
                HStack(spacing: 10) {
                    stepButton("minus", label: "Lower strike", disabled: draft.strikeIndex == 0) {
                        self.draft?.strikeIndex -= 1
                    }
                    if lastIndex > 0 {
                        Slider(
                            value: Binding(
                                get: { Double(draft.strikeIndex) },
                                set: { self.draft?.strikeIndex = Int($0.rounded()) }
                            ),
                            in: 0...Double(lastIndex), step: 1
                        )
                        .accessibilityLabel("Strike")
                        .accessibilityValue(OptionText.strike(draft.strike))
                    } else {
                        Spacer()
                    }
                    stepButton("plus", label: "Higher strike", disabled: draft.strikeIndex >= lastIndex) {
                        self.draft?.strikeIndex += 1
                    }
                }
            }

            Divider()

            HStack {
                TermButton(term: .contract).font(.subheadline.weight(.semibold))
                Spacer()
                Text("\(draft.contracts) · \(draft.contracts * 100) shares")
                    .font(.subheadline.monospacedDigit()).foregroundStyle(.inkSecondary)
                HStack(spacing: 8) {
                    stepButton("minus", label: "Fewer contracts", disabled: draft.contracts <= 1) {
                        self.draft?.contracts -= 1
                    }
                    stepButton("plus", label: "More contracts", disabled: draft.contracts >= OptionPlanDraft.maxContracts) {
                        self.draft?.contracts += 1
                    }
                }
            }
        }
    }

    private func stepButton(_ systemImage: String, label: String, disabled: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.footnote.weight(.bold))
                .frame(width: 36, height: 36)
                .background(Color.well, in: Circle())
        }
        .buttonStyle(.plain)
        .foregroundStyle(disabled ? Color.inkSecondary.opacity(0.5) : .brand)
        .disabled(disabled)
        .accessibilityLabel(label)
    }

    private func quoteCard(_ draft: OptionPlanDraft, _ plan: OptionPlan) -> some View {
        let quote = draft.quote
        let estimated = plan.isEstimated
        return Card("This contract at the close") {
            HStack {
                TermButton(term: .bidAsk).font(.subheadline).foregroundStyle(.inkSecondary)
                Spacer()
                Text("\(OptionText.price(quote.bid)) / \(OptionText.price(quote.ask))")
                    .font(.subheadline.weight(.medium).monospacedDigit())
            }
            if estimated, let quoted = quote.quotedMid, let stockThen = draft.chain.quotedUnderlyingPrice {
                DetailRow("Halfway between, at the close", OptionText.price(quoted))
                DetailRow("Estimate now, used in this plan", OptionText.price(quote.mid))
                Notice(
                    text: "\(symbol) closed at \(OptionText.price(stockThen)) and is \(OptionText.price(plan.underlyingPrice)) now. The estimate moves the close's price by what that change, and the time gone, are worth at the volatility the close implied. It is not a quote: a sharp move usually changes volatility too, which this cannot see.",
                    systemImage: "function"
                )
            } else {
                DetailRow("Price used, halfway between", OptionText.price(quote.mid))
            }
            HStack {
                TermButton(term: .openContracts).font(.subheadline).foregroundStyle(.inkSecondary)
                Spacer()
                Text(quote.openInterest.formatted()).font(.subheadline.weight(.medium).monospacedDigit())
            }
            DetailRow("Traded that day", quote.volume.formatted())
            if let thin = quote.thinlyTraded {
                Notice(text: thin, systemImage: "exclamationmark.triangle.fill", tint: .caution)
            }
            if let caution = plan.caution {
                Notice(text: caution)
            }
            if strategy.ownsShares {
                Notice(text: "Worked out as if you hold \(plan.shares) \(symbol) shares at \(OptionText.price(plan.underlyingPrice)). With fewer shares, the option is not covered by them.")
            }
        }
    }

    // MARK: Actions

    private func pick(_ expiration: String) {
        guard expiration != draft?.chain.expiration, loadingExpiration == nil else { return }
        Task { await load(expiration: expiration) }
    }

    private func save(_ plan: OptionPlan) async {
        isSaving = true
        saveError = nil
        defer { isSaving = false }
        do throws(APIFailure) {
            try await session.options.save(plan)
            savedPlan = plan
        } catch {
            if error == .notSignedIn {
                session.signOut()
            } else {
                saveError = error.message
            }
        }
    }
}
