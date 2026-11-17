import LivermoreKit
import SwiftUI

/// One strategy package: what it does, what history suggests, and the few
/// things to set before running it.
struct TemplateSetupView: View {
    @Environment(AppSession.self) private var session
    let template: StrategyTemplate
    var presetTicker: String?
    /// A ready-made group — a stock and its rivals — for strategies that
    /// rank several tickers.
    var presetTickers: [String]?

    @State private var tickerText = ""
    @State private var range: BacktestRange = .fiveYears
    @State private var customization: StrategyCustomization
    @State private var isRunning = false
    @State private var failure: APIFailure?
    @State private var outcome: Outcome?
    @State private var showsCaveats = false
    @FocusState private var tickersFocused: Bool

    struct Outcome: Hashable {
        let result: BacktestResult
        let templateID: String
    }

    /// `presetExitPlan` carries a stop and target chosen elsewhere (the
    /// entry / exit test) into the strategy's settings.
    init(
        template: StrategyTemplate, presetTicker: String? = nil, presetTickers: [String]? = nil,
        presetExitPlan: ExitPlan? = nil
    ) {
        self.template = template
        self.presetTicker = presetTicker ?? (presetTickers?.count == 1 ? presetTickers?.first : nil)
        self.presetTickers = presetTickers
        var settings = StrategyCustomization(strategy: template.strategy)
        if let presetExitPlan, presetExitPlan.problem == nil { settings.exitPlan = presetExitPlan }
        _customization = State(initialValue: settings)
    }

    private var tickers: [String] { StrategyBuilder.tickers(from: tickerText) }

    /// Why the run can't start, or nil when it can.
    private var problem: String? {
        if tickers.isEmpty { return "Enter at least one ticker." }
        if !template.multiTicker && tickers.count > 1 { return "This strategy tests one ticker at a time." }
        if tickers.count < template.minimumTickers {
            return "This strategy needs at least \(template.minimumTickers) tickers; you have \(tickers.count)."
        }
        return customization.problem
    }

    private var settingsSummary: String {
        let changes = customization.changeCount(from: template.strategy)
        return changes == 0 ? "Standard" : "\(changes) change\(changes == 1 ? "" : "s")"
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Metrics.sectionSpacing) {
                hero
                // What to set comes first: the page is a package to run, and
                // the explanation below is there for whoever wants it.
                setup
                howItWorks
                history
            }
            .padding(Metrics.screenPadding)
        }
        .scrollDismissesKeyboard(.interactively)
        .screenBackground()
        // The name is the page's own headline; repeating it in the bar
        // would say it twice.
        .navigationTitle("")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .bottomBar {
            if let message = barMessage {
                Text(message.text).font(.footnote).foregroundStyle(message.tint)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            Button(action: run) {
                HStack(spacing: 8) {
                    if isRunning { ProgressView().tint(.white) }
                    Text(isRunning ? "Running the backtest…" : "Run backtest")
                }
            }
            .buttonStyle(PrimaryButtonStyle())
            .disabled(problem != nil || isRunning)
            .accessibilityIdentifier("run-backtest")
        }
        .navigationDestination(item: $outcome) { outcome in
            BacktestResultView(result: outcome.result, templateID: outcome.templateID)
        }
        .onAppear {
            guard tickerText.isEmpty else { return }
            if let presetTicker, !template.multiTicker {
                tickerText = presetTicker
            } else if let presetTickers, template.multiTicker, presetTickers.count >= template.minimumTickers {
                tickerText = presetTickers.joined(separator: ", ")
            } else {
                tickerText = template.defaultTickers.joined(separator: ", ")
            }
        }
    }

    /// The one line above the button: what is wrong, or what to expect.
    private var barMessage: (text: String, tint: Color)? {
        if case .upgradeRequired(let detail) = failure, !session.isSignedIn {
            // The backend's line assumes a sign-up button beside it; say
            // where to go in the app.
            return ("\(detail). You've used the one backtest available without an account — sign in from the Account tab to run more.", .caution)
        }
        if let failure { return (failure.message, .loss) }
        if let problem { return (problem, .caution) }
        if !session.isSignedIn { return ("One backtest without an account. Sign in to run more and to save.", .inkSecondary) }
        return nil
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .center, spacing: 12) {
                CategoryIcon(category: template.category, size: 52)
                VStack(alignment: .leading, spacing: 2) {
                    Text(template.category).eyebrowStyle()
                    Text(template.name).font(.title2.weight(.bold))
                }
            }
            Text(template.description).font(.subheadline).foregroundStyle(.inkSecondary)
            TemplateTags(template: template)
        }
        .padding(.horizontal, 4)
    }

    private var howItWorks: some View {
        Card("How it works") {
            if let entry = template.whenInCopy {
                RuleLine(title: "Buys when", text: entry, systemImage: "arrow.down.left.circle.fill", tint: .gain)
            }
            if let exit = template.whenOutCopy {
                RuleLine(title: "Sells when", text: exit, systemImage: "arrow.up.right.circle.fill", tint: .loss)
            }
            if template.whenInCopy != nil || template.whenOutCopy != nil { Divider() }
            VStack(alignment: .leading, spacing: 2) {
                Text("What it tests").font(.caption.weight(.semibold)).foregroundStyle(.inkSecondary)
                Text(template.whatItTests).font(.subheadline)
            }
            if let caveat = template.etfProxyCaveat {
                Notice(text: caveat, tint: .caution)
            }
        }
    }

    @ViewBuilder
    private var history: some View {
        let context = template.perfContext
        let caveats = template.caveats ?? []
        if context != nil || !caveats.isEmpty {
            Card("What history suggests") {
                if let context {
                    HStack(spacing: 8) {
                        if let typical = StrategyTemplate.headlineRange(context.returnRange) {
                            StatTile(label: "Typical, per year", value: typical, tint: .gain, compact: true)
                        }
                        if let worst = StrategyTemplate.headlineRange(context.worstStretch) {
                            StatTile(label: "Worst stretch", value: worst, tint: .loss, compact: true)
                        }
                    }
                    if let line = context.returnRange { DetailRow("Return", line) }
                    if let line = context.sharpeRange { DetailRow("Risk-adjusted", line) }
                    if let line = context.worstStretch { DetailRow("Worst stretch", line) }
                }
                if !caveats.isEmpty {
                    DisclosureGroup(isExpanded: $showsCaveats) {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(caveats, id: \.self) { caveat in
                                HStack(alignment: .firstTextBaseline, spacing: 8) {
                                    Image(systemName: "exclamationmark.triangle.fill").font(.caption).foregroundStyle(.caution)
                                    Text(caveat).font(.footnote)
                                }
                            }
                        }
                        .padding(.top, 8)
                    } label: {
                        Text("Before you rely on it (\(caveats.count))").font(.subheadline.weight(.semibold))
                    }
                    .tint(.brand)
                }
                if let citation = template.academicRef?.citation {
                    Text(citation).font(.caption2).foregroundStyle(.inkSecondary)
                }
            }
        }
    }

    private var setup: some View {
        Card("Set it up") {
            VStack(alignment: .leading, spacing: 6) {
                Text(template.tickerLabel).font(.caption.weight(.semibold)).foregroundStyle(.inkSecondary)
                TextField(template.multiTicker ? "AAPL, MSFT, NVDA" : "AAPL", text: $tickerText, axis: .vertical)
                    .font(.body.monospaced())
                    .autocorrectionDisabled()
                    #if os(iOS)
                    .textInputAutocapitalization(.characters)
                    .keyboardType(.asciiCapable)
                    #endif
                    .focused($tickersFocused)
                    .padding(12)
                    .background(Color.well, in: RoundedRectangle(cornerRadius: Metrics.tileRadius, style: .continuous))
                    .accessibilityIdentifier("template-tickers")
                Text(template.universeDescription).font(.caption).foregroundStyle(.inkSecondary)
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Test period").font(.caption.weight(.semibold)).foregroundStyle(.inkSecondary)
                Picker("Period", selection: $range) {
                    ForEach(BacktestRange.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
            }

            NavigationLink {
                StrategyCustomizeView(customization: $customization, original: template.strategy)
            } label: {
                HStack {
                    Image(systemName: "slider.horizontal.3").foregroundStyle(.brand)
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Settings").font(.subheadline.weight(.semibold))
                        Text("Capital, costs, the rule's numbers, risk, stop and targets")
                            .font(.caption).foregroundStyle(.inkSecondary)
                    }
                    Spacer()
                    Text(settingsSummary).font(.subheadline).foregroundStyle(.inkSecondary)
                    Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
                }
                .padding(12)
                .background(Color.well, in: RoundedRectangle(cornerRadius: Metrics.tileRadius, style: .continuous))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("customize-strategy")
        }
    }

    private func run() {
        guard problem == nil, !isRunning else { return }
        tickersFocused = false
        isRunning = true
        failure = nil
        let strategy = customization.apply(
            to: StrategyBuilder.strategy(from: template, tickers: tickers, range: range)
        )
        let signedIn = session.isSignedIn
        Task {
            do throws(APIFailure) {
                let result = try await session.backtests.run(strategy, templateID: template.id, signedIn: signedIn)
                outcome = Outcome(result: result, templateID: template.id)
            } catch {
                if error == .notSignedIn { session.signOut() }
                failure = error
            }
            isRunning = false
        }
    }
}

/// One side of the rule: the rule itself in a sentence, with the reasoning
/// behind it a tap away.
private struct RuleLine: View {
    let title: String
    let text: String
    let systemImage: String
    let tint: Color

    @State private var isExpanded = false

    /// The first sentence, and whatever follows it.
    private var parts: (lead: String, rest: String?) {
        guard let end = text.range(of: ". ") else { return (text, nil) }
        let rest = text[end.upperBound...].trimmingCharacters(in: .whitespacesAndNewlines)
        return (String(text[..<end.lowerBound]) + ".", rest.isEmpty ? nil : rest)
    }

    var body: some View {
        let parts = parts
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: systemImage).font(.title3).foregroundStyle(tint)
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(.caption.weight(.semibold)).foregroundStyle(.inkSecondary)
                Text(parts.lead).font(.subheadline.weight(.medium))
                if let rest = parts.rest {
                    if isExpanded {
                        Text(rest).font(.footnote).foregroundStyle(.inkSecondary)
                    }
                    Button(isExpanded ? "Show less" : "Why") {
                        withAnimation(.easeInOut(duration: 0.2)) { isExpanded.toggle() }
                    }
                    .font(.footnote.weight(.semibold))
                    .buttonStyle(.plain)
                    .foregroundStyle(.brand)
                }
            }
        }
    }
}
