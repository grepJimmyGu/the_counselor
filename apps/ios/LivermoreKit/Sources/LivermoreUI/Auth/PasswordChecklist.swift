import LivermoreKit
import SwiftUI

/// A password box with the eye that shows or hides it.
struct PasswordRow: View {
    let placeholder: String
    @Binding var text: String
    @Binding var isRevealed: Bool
    var isNew = false
    var hasNext = false
    var focusRequest = 0
    var onSubmit: () -> Void = {}

    var body: some View {
        HStack(spacing: 12) {
            PasswordField(
                placeholder: placeholder,
                text: $text,
                isNew: isNew,
                isRevealed: isRevealed,
                generatorRules: isNew ? PasswordPolicy.generatorRules : nil,
                hasNext: hasNext,
                focusRequest: focusRequest,
                onSubmit: onSubmit
            )
            Button {
                isRevealed.toggle()
            } label: {
                Image(systemName: isRevealed ? "eye.slash" : "eye")
                    .foregroundStyle(.inkSecondary)
                    .frame(minWidth: 28, minHeight: 28)
            }
            .buttonStyle(.borderless)
            .accessibilityLabel(isRevealed ? "Hide password" : "Show password")
            .accessibilityIdentifier("password-reveal")
        }
    }
}

/// The two boxes for choosing a password: the password, and the same again.
/// Return in the first moves to the second; Return in the second submits.
struct NewPasswordRows: View {
    @Binding var password: String
    @Binding var confirmation: String
    @Binding var isRevealed: Bool
    var placeholder = "Password"
    var onSubmit: () -> Void = {}

    @State private var confirmFocus = 0

    var body: some View {
        PasswordRow(
            placeholder: placeholder, text: $password, isRevealed: $isRevealed,
            isNew: true, hasNext: true, onSubmit: { confirmFocus += 1 }
        )
        .accessibilityIdentifier("password-field")
        PasswordField(
            placeholder: "Type the password again",
            text: $confirmation,
            isNew: true,
            isRevealed: isRevealed,
            focusRequest: confirmFocus,
            onSubmit: onSubmit
        )
        .accessibilityIdentifier("password-confirm-field")
    }
}

/// The rules, ticked off as the password comes to meet them.
struct PasswordChecklist: View {
    let password: String
    let confirmation: String
    let broken: [PasswordRule]

    var body: some View {
        Section {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(PasswordRule.required, id: \.self) { rule in
                    ChecklistRow(rule.label, state: password.isEmpty || broken.contains(rule) ? .pending : .met)
                }
                ChecklistRow(
                    "Typed the same both times",
                    state: confirmation.isEmpty ? .pending : (confirmation == password ? .met : .broken)
                )
                // Things to leave out only appear once one of them is in the password.
                ForEach(broken.filter { !PasswordRule.required.contains($0) }, id: \.self) { rule in
                    ChecklistRow("Leave out: \(rule.label.lowercasedFirst)", state: .broken)
                }
            }
            .padding(.vertical, 2)
            .accessibilityIdentifier("password-checklist")
        } header: {
            Text("The password needs")
        } footer: {
            Text("It is also checked against passwords exposed in known data breaches.")
        }
    }
}

/// One line above the keyboard: what the password still lacks.
struct PasswordProgress: View {
    let broken: [PasswordRule]
    /// Nil until something has been typed in the second box.
    let confirmed: Bool?

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: isReady ? "checkmark.circle.fill" : "circle.dashed")
                .foregroundStyle(isReady ? Color.gain : Color.inkSecondary)
            Text(message).foregroundStyle(isReady ? Color.primary : Color.inkSecondary)
            Spacer(minLength: 0)
        }
        .font(.footnote)
        .padding(.horizontal, Metrics.screenPadding)
        .padding(.vertical, 10)
        .background(.bar)
        .overlay(alignment: .top) { Rectangle().fill(Color.hairline.opacity(0.6)).frame(height: 0.5) }
        .accessibilityIdentifier("password-progress")
    }

    private var isReady: Bool { broken.isEmpty && confirmed == true }

    private var message: String {
        let missing = broken.filter(PasswordRule.required.contains).map(\.short)
        if !missing.isEmpty { return "Still needs: " + missing.joined(separator: ", ") }
        if let avoid = broken.first { return "Leave out: " + avoid.label.lowercasedFirst }
        switch confirmed {
        case nil: return "Meets the rules. Type it again below."
        case false?: return "The two entries don't match yet."
        case true?: return "Meets the rules, and both entries match."
        }
    }
}

private extension PasswordRule {
    /// The rule in a word or two, for the line above the keyboard.
    var short: String {
        switch self {
        case .length: "\(PasswordPolicy.minLength)+ characters"
        case .lowercase: "lowercase"
        case .uppercase: "uppercase"
        case .number: "number"
        case .symbol: "symbol"
        case .repeat, .sequence, .personal: label.lowercasedFirst
        }
    }
}

private struct ChecklistRow: View {
    enum State { case pending, met, broken }

    let text: String
    let state: State

    init(_ text: String, state: State) {
        self.text = text
        self.state = state
    }

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: symbol).foregroundStyle(tint)
            Text(text).foregroundStyle(state == .pending ? Color.inkSecondary : Color.primary)
        }
        .font(.subheadline)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(text): \(spoken)")
    }

    private var symbol: String {
        switch state {
        case .pending: "circle"
        case .met: "checkmark.circle.fill"
        case .broken: "xmark.circle.fill"
        }
    }

    private var tint: Color {
        switch state {
        case .pending: .inkSecondary
        case .met: .gain
        case .broken: .loss
        }
    }

    private var spoken: String {
        switch state {
        case .pending: "not yet"
        case .met: "done"
        case .broken: "not allowed"
        }
    }
}

private extension String {
    var lowercasedFirst: String { prefix(1).lowercased() + dropFirst() }
}
