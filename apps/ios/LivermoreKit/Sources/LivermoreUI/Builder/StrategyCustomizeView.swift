import LivermoreKit
import SwiftUI

/// Change a strategy's money, rule numbers, risk level and exit plan before
/// running it.
struct StrategyCustomizeView: View {
    @Binding var customization: StrategyCustomization
    /// The strategy as it was before any change, to count changes against and
    /// to reset to.
    let original: StrategyJSON

    @FocusState private var focused: String?

    private var originalSettings: StrategyCustomization { StrategyCustomization(strategy: original) }

    var body: some View {
        Form {
            Section {
                LabeledContent("Starting capital") {
                    TextField("10,000", value: $customization.initialCapital, format: .currency(code: "USD").precision(.fractionLength(0)))
                        .multilineTextAlignment(.trailing)
                        #if os(iOS)
                        .keyboardType(.numberPad)
                        #endif
                        .focused($focused, equals: "capital")
                        .accessibilityIdentifier("customize-capital")
                }
                CostRow(title: "Commission and fees", bps: $customization.transactionCostBps)
                CostRow(title: "Slippage", bps: $customization.slippageBps)
            } header: {
                Text("Money")
            } footer: {
                Text("Both costs are charged on every buy and every sell. Slippage is the price you give up to the market when an order fills.")
            }

            if !customization.parameters.isEmpty {
                Section {
                    ForEach($customization.parameters) { $parameter in
                        ParameterRow(parameter: $parameter, focused: $focused)
                    }
                } header: {
                    Text("The rule")
                } footer: {
                    Text("Days are trading days: 21 is about a month, 63 a quarter, 252 a year.")
                }
            }

            Section {
                Picker("Risk level", selection: $customization.riskLevel) {
                    if originalSettings.riskLevel == nil {
                        Text("Template").tag(RiskLevel?.none)
                    }
                    Text("Lower").tag(RiskLevel?.some(.low))
                    Text("Medium").tag(RiskLevel?.some(.medium))
                    Text("Higher").tag(RiskLevel?.some(.high))
                }
                .pickerStyle(.segmented)
                .accessibilityIdentifier("customize-risk")
            } header: {
                Text("Risk level")
            } footer: {
                Text(riskExplanation)
            }

            exitPlanSection

            if let problem = customization.problem {
                Section {
                    Label(problem, systemImage: "exclamationmark.triangle")
                        .font(.footnote).foregroundStyle(.caution)
                }
            }

            if customization != originalSettings {
                Section {
                    Button("Reset to the original settings", role: .destructive) {
                        customization = originalSettings
                    }
                }
            }
        }
        .screenBackground()
        .navigationTitle("Settings")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { focused = nil }
            }
        }
        #endif
    }

    private var riskExplanation: String {
        switch customization.riskLevel {
        case .none:
            "Position sizes as the template defines them."
        case .low:
            "Positions are scaled down whenever the strategy's recent swings run above 8% a year. Expect smaller drops and smaller gains."
        case .medium:
            "Positions are scaled down whenever the strategy's recent swings run above 12% a year."
        case .high:
            "No scaling: the strategy is fully invested whenever its rule says to be."
        }
    }

    @ViewBuilder
    private var exitPlanSection: some View {
        Section {
            Toggle("Set a stop and targets", isOn: Binding(
                get: { customization.exitPlan != nil },
                set: { customization.setExitPlan(enabled: $0) }
            ))
            .accessibilityIdentifier("customize-exit-plan")

            if let plan = customization.exitPlan {
                PercentStepper(
                    title: "Sell everything at", sign: "−", value: Binding(
                        get: { plan.stopPercent },
                        set: { customization.exitPlan?.stopPercent = $0 }
                    ), range: 1...50
                )

                Toggle("Take part of the profit early", isOn: Binding(
                    get: { plan.firstTargetPercent != nil },
                    set: { on in
                        // Keep the first target below the final one.
                        let ceiling = plan.finalTargetPercent ?? .infinity
                        customization.exitPlan?.firstTargetPercent = on ? min(15, max(1, ceiling / 2)) : nil
                    }
                ))
                if let first = plan.firstTargetPercent {
                    PercentStepper(
                        title: "First target", sign: "+", value: Binding(
                            get: { first },
                            set: { customization.exitPlan?.firstTargetPercent = $0 }
                        ), range: 1...200
                    )
                    Picker("Sell at the first target", selection: Binding(
                        get: { plan.firstTargetFraction },
                        set: { customization.exitPlan?.firstTargetFraction = $0 }
                    )) {
                        ForEach(fractionChoices(including: plan.firstTargetFraction), id: \.self) { fraction in
                            Text(fractionLabel(fraction)).tag(fraction)
                        }
                    }
                }

                Toggle("Sell the rest at a final target", isOn: Binding(
                    get: { plan.finalTargetPercent != nil },
                    set: { on in
                        customization.exitPlan?.finalTargetPercent = on ? max(30, (plan.firstTargetPercent ?? 0) * 2) : nil
                    }
                ))
                if let final = plan.finalTargetPercent {
                    PercentStepper(
                        title: "Final target", sign: "+", value: Binding(
                            get: { final },
                            set: { customization.exitPlan?.finalTargetPercent = $0 }
                        ), range: 1...500
                    )
                }
            }
        } header: {
            Text("Exit plan")
        } footer: {
            if customization.keepsOriginalLadder {
                Text("This strategy already has an exit plan with more steps than this screen shows. It is used as it is unless you set a new one here.")
            } else {
                Text("Levels are measured from each entry price, and the backtest sells at them. Save a strategy that has an exit plan and Livermore tracks your positions against it and tells you when a level is reached.")
            }
        }
    }

    private func fractionChoices(including current: Double) -> [Double] {
        let standard = [0.25, 1.0 / 3.0, 0.5, 0.75]
        return standard.contains(current) ? standard : (standard + [current]).sorted()
    }

    private func fractionLabel(_ fraction: Double) -> String {
        switch fraction {
        case 0.25: "A quarter"
        case 0.5: "Half"
        case 0.75: "Three quarters"
        default: abs(fraction - 1.0 / 3.0) < 0.005 ? "A third" : "\(Int((fraction * 100).rounded()))%"
        }
    }
}

/// A trading cost in basis points, shown as the percentage a user recognises.
private struct CostRow: View {
    let title: String
    @Binding var bps: Double

    var body: some View {
        Stepper(value: $bps, in: StrategyCustomization.costRange, step: 1) {
            LabeledContent(title, value: bps == 0 ? "None" : String(format: "%.2f%%", bps / 100))
        }
    }
}

private struct PercentStepper: View {
    let title: String
    let sign: String
    @Binding var value: Double
    let range: ClosedRange<Double>

    var body: some View {
        Stepper(value: $value, in: range, step: 1) {
            LabeledContent(title, value: sign + (value == value.rounded() ? "\(Int(value))" : String(format: "%.1f", value)) + "%")
        }
    }
}

private struct ParameterRow: View {
    @Binding var parameter: RuleParameter
    var focused: FocusState<String?>.Binding

    var body: some View {
        switch parameter.unit {
        case .days, .count:
            // Windows run from a week to two years; typing beats tapping a
            // stepper 200 times.
            HStack {
                Text(parameter.label)
                Spacer()
                TextField("", value: Binding(
                    get: { Int(parameter.value) },
                    set: { parameter.value = min(max(Double($0), parameter.range.lowerBound), parameter.range.upperBound) }
                ), format: .number)
                    .multilineTextAlignment(.trailing)
                    .frame(width: 64)
                    #if os(iOS)
                    .keyboardType(.numberPad)
                    #endif
                    .focused(focused, equals: parameter.id)
                    .accessibilityIdentifier("customize-\(parameter.id)")
                if parameter.unit == .days { Text("days").foregroundStyle(.secondary) }
                Stepper(parameter.label, value: $parameter.value, in: parameter.range, step: parameter.step)
                    .labelsHidden()
            }
        case .percent, .multiple:
            Stepper(value: $parameter.value, in: parameter.range, step: parameter.step) {
                LabeledContent(parameter.label, value: parameter.formatted)
            }
        }
    }
}
