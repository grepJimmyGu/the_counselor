import LivermoreKit
import SwiftUI

/// Test a saved strategy again — on today's data, and with any changes — and
/// keep the result as a new strategy if it is better.
struct StrategyRerunView: View {
    @Environment(AppSession.self) private var session
    let saved: SavedStrategy
    let original: StrategyJSON

    @State private var range: BacktestRange = .fiveYears
    @State private var customization: StrategyCustomization
    @State private var isRunning = false
    @State private var failure: APIFailure?
    @State private var outcome: TemplateSetupView.Outcome?

    init(saved: SavedStrategy, original: StrategyJSON) {
        self.saved = saved
        self.original = original
        _customization = State(initialValue: StrategyCustomization(strategy: original))
    }

    private var settingsSummary: String {
        let changes = customization.changeCount(from: original)
        return changes == 0 ? "As saved" : "\(changes) change\(changes == 1 ? "" : "s")"
    }

    var body: some View {
        Form {
            Section {
                LabeledContent("Tickers", value: original.universe.joined(separator: ", "))
                Picker("Period", selection: $range) {
                    ForEach(BacktestRange.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
            } header: {
                Text(saved.title)
            } footer: {
                Text("The test ends today and looks back over the period you choose.")
            }

            Section {
                NavigationLink {
                    StrategyCustomizeView(customization: $customization, original: original)
                } label: {
                    LabeledContent("Settings", value: settingsSummary)
                }
                .accessibilityIdentifier("customize-strategy")
            } footer: {
                Text("Change the rule's numbers, the risk level, or the stop and targets, and see what it would have done.")
            }

            Section {
                Button(action: run) {
                    HStack {
                        Text(isRunning ? "Running…" : "Run backtest")
                        Spacer()
                        if isRunning { ProgressView() }
                    }
                }
                .disabled(customization.problem != nil || isRunning)
                .accessibilityIdentifier("run-backtest")
            } footer: {
                VStack(alignment: .leading, spacing: 4) {
                    if let problem = customization.problem { Text(problem).foregroundStyle(.orange) }
                    if let failure { Text(failure.message).foregroundStyle(.red) }
                    Text("Saving the result keeps it as a new strategy; “\(saved.title)” is not changed.")
                }
            }
        }
        .navigationTitle("Test again")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .navigationDestination(item: $outcome) { outcome in
            BacktestResultView(result: outcome.result, templateID: nil)
        }
    }

    private func run() {
        guard customization.problem == nil, !isRunning else { return }
        isRunning = true
        failure = nil
        var strategy = customization.apply(to: StrategyBuilder.redated(original, range: range))
        if customization.changeCount(from: original) > 0, !strategy.strategyName.hasSuffix("(adjusted)") {
            // Saved under its own name, so the two can be told apart.
            strategy.strategyName += " (adjusted)"
        }
        Task {
            do throws(APIFailure) {
                // No template id: a saved strategy is the user's own, so it
                // runs under their plan's custom-strategy limits.
                let result = try await session.backtests.run(strategy, templateID: nil, signedIn: true)
                outcome = .init(result: result, templateID: "")
            } catch {
                if error == .notSignedIn { session.signOut() }
                failure = error
            }
            isRunning = false
        }
    }
}
