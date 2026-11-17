import LivermoreKit
import SwiftUI

/// What a template does, the tickers and period to test it on, and the run.
struct TemplateSetupView: View {
    @Environment(AppSession.self) private var session
    let template: StrategyTemplate
    var presetTicker: String?

    @State private var tickerText = ""
    @State private var range: BacktestRange = .fiveYears
    @State private var isRunning = false
    @State private var failure: APIFailure?
    @State private var outcome: Outcome?

    struct Outcome: Hashable {
        let result: BacktestResult
        let templateID: String
    }

    private var tickers: [String] { StrategyBuilder.tickers(from: tickerText) }

    /// Why the run can't start, or nil when it can.
    private var problem: String? {
        if tickers.isEmpty { return "Enter at least one ticker." }
        if !template.multiTicker && tickers.count > 1 { return "This template tests one ticker at a time." }
        if tickers.count < template.minimumTickers {
            return "This template needs at least \(template.minimumTickers) tickers; you have \(tickers.count)."
        }
        return nil
    }

    var body: some View {
        Form {
            Section("What it tests") {
                Text(template.whatItTests).font(.subheadline)
                if let caveat = template.etfProxyCaveat {
                    Label(caveat, systemImage: "info.circle").font(.footnote).foregroundStyle(.secondary)
                }
            }

            if template.whenInCopy != nil || template.whenOutCopy != nil {
                Section("The rules") {
                    if let entry = template.whenInCopy { RuleText(title: "When it buys", text: entry) }
                    if let exit = template.whenOutCopy { RuleText(title: "When it sells", text: exit) }
                }
            }

            if let context = template.perfContext {
                Section {
                    if let range = context.returnRange { LabeledContent("Typical return", value: range) }
                    if let sharpe = context.sharpeRange { LabeledContent("Risk-adjusted", value: sharpe) }
                    if let worst = context.worstStretch { LabeledContent("Worst stretch", value: worst) }
                } header: {
                    Text("What history suggests")
                } footer: {
                    if let citation = template.academicRef?.citation { Text(citation) }
                }
                .font(.subheadline)
            }

            if let caveats = template.caveats, !caveats.isEmpty {
                Section("Caveats") {
                    ForEach(caveats, id: \.self) { Text($0).font(.footnote) }
                }
            }

            Section {
                TextField(template.multiTicker ? "AAPL, MSFT, NVDA" : "AAPL", text: $tickerText, axis: .vertical)
                    .autocorrectionDisabled()
                    #if os(iOS)
                    .textInputAutocapitalization(.characters)
                    .keyboardType(.asciiCapable)
                    #endif
                    .accessibilityIdentifier("template-tickers")
                Picker("Period", selection: $range) {
                    ForEach(BacktestRange.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
            } header: {
                Text(template.tickerLabel)
            } footer: {
                VStack(alignment: .leading, spacing: 4) {
                    Text(template.universeDescription)
                    if let problem { Text(problem).foregroundStyle(.orange) }
                }
            }

            Section {
                Button(action: run) {
                    HStack {
                        Text(isRunning ? "Running…" : "Run backtest")
                        Spacer()
                        if isRunning { ProgressView() }
                    }
                }
                .disabled(problem != nil || isRunning)
                .accessibilityIdentifier("run-backtest")
            } footer: {
                if case .upgradeRequired(let detail) = failure, !session.isSignedIn {
                    // The backend's line ("Sign up to keep exploring") assumes
                    // a sign-up button beside it; say where to go in the app.
                    Text("\(detail). You've used the one backtest available without an account — sign in from the Account tab to run more.")
                        .foregroundStyle(.orange)
                } else if let failure {
                    Text(failure.message).foregroundStyle(.red)
                } else if !session.isSignedIn {
                    Text("Without an account you can run one backtest. Sign in from the Account tab to run more and to save strategies.")
                }
            }
        }
        .navigationTitle(template.name)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .navigationDestination(item: $outcome) { outcome in
            BacktestResultView(result: outcome.result, templateID: outcome.templateID)
        }
        .onAppear {
            guard tickerText.isEmpty else { return }
            if let presetTicker, !template.multiTicker {
                tickerText = presetTicker
            } else {
                tickerText = template.defaultTickers.joined(separator: ", ")
            }
        }
    }

    private func run() {
        guard problem == nil, !isRunning else { return }
        isRunning = true
        failure = nil
        let strategy = StrategyBuilder.strategy(from: template, tickers: tickers, range: range)
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

private struct RuleText: View {
    let title: String
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            Text(text).font(.subheadline)
        }
    }
}
