import LivermoreKit
import SwiftUI

/// Resetting a forgotten password: ask for a code by email, then type the code
/// and a new password. Finishing signs the user in.
struct ForgotPasswordView: View {
    @Environment(AppSession.self) private var session
    @Environment(\.dismiss) private var dismiss

    private enum Step { case email, code }

    @State private var step: Step = .email
    @State private var email: String
    @State private var code = ""
    @State private var password = ""
    @State private var confirmation = ""
    @State private var isRevealed = true
    @State private var isBusy = false
    @State private var keyboardIsUp = false
    @State private var errorMessage: String?
    /// How many codes this screen has asked for, to say so after a resend.
    @State private var codesSent = 0

    init(email: String) {
        _email = State(initialValue: email)
    }

    private var trimmedEmail: String { email.trimmingCharacters(in: .whitespaces) }

    private var broken: [PasswordRule] {
        PasswordPolicy.violations(password, email: trimmedEmail)
    }

    private var canReset: Bool {
        code.count == Self.codeLength && broken.isEmpty && password == confirmation && !isBusy
    }

    private static let codeLength = 6

    var body: some View {
        NavigationStack {
            Form {
                switch step {
                case .email: emailStep
                case .code: codeStep
                }
            }
            .screenBackground()
            .navigationTitle("Reset password")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                if step == .code, keyboardIsUp, !password.isEmpty {
                    PasswordProgress(broken: broken, confirmed: confirmation.isEmpty ? nil : confirmation == password)
                }
            }
            .onKeyboardChange { keyboardIsUp = $0 }
            .onChange(of: password) { _, _ in if !isBusy { errorMessage = nil } }
            .onChange(of: code) { _, new in
                let digits = String(new.filter { ("0"..."9").contains($0) }.prefix(Self.codeLength))
                if digits != new { code = digits }
                if !isBusy { errorMessage = nil }
            }
        }
    }

    @ViewBuilder private var emailStep: some View {
        Section {
            TextField("Email", text: $email)
                .textContentType(.username)
                .autocorrectionDisabled()
            #if os(iOS)
                .keyboardType(.emailAddress)
                .textInputAutocapitalization(.never)
            #endif
                .onSubmit(sendCode)
        } footer: {
            VStack(alignment: .leading, spacing: 6) {
                Text("We'll email a 6-digit code to this address. Typing it back lets you choose a new password.")
                errorText
            }
        }
        Section {
            Button(action: sendCode) {
                HStack(spacing: 8) {
                    if isBusy { ProgressView().tint(.white) }
                    Text("Email me a code")
                }
            }
            .buttonStyle(PrimaryButtonStyle())
            .disabled(trimmedEmail.isEmpty || isBusy)
            .listRowInsets(EdgeInsets())
            .listRowBackground(Color.clear)
            .accessibilityIdentifier("reset-send-code")
        }
    }

    @ViewBuilder private var codeStep: some View {
        Section {
            TextField("6-digit code", text: $code)
                .textContentType(.oneTimeCode)
                .font(.title3.monospacedDigit())
            #if os(iOS)
                .keyboardType(.numberPad)
            #endif
                .accessibilityIdentifier("reset-code")
        } header: {
            Text("Code from the email")
        } footer: {
            // The backend does not say whether the address has an account,
            // so neither does this.
            Text("If \(trimmedEmail) has a Livermore account, \(codesSent > 1 ? "a new code" : "a code") is on its way. It works for 15 minutes. Check the spam folder if it has not arrived.")
        }
        Section {
            NewPasswordRows(
                password: $password, confirmation: $confirmation, isRevealed: $isRevealed,
                placeholder: "New password", onSubmit: reset
            )
        } header: {
            Text("New password")
        } footer: {
            errorText
        }
        PasswordChecklist(password: password, confirmation: confirmation, broken: broken)
        Section {
            VStack(spacing: 12) {
                Button(action: reset) {
                    HStack(spacing: 8) {
                        if isBusy { ProgressView().tint(.white) }
                        Text("Set new password")
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(!canReset)
                .accessibilityIdentifier("reset-confirm")

                Button("Send a new code", action: sendCode)
                    .buttonStyle(SecondaryButtonStyle())
                    .disabled(isBusy)
                    .accessibilityIdentifier("reset-resend")
            }
            .listRowInsets(EdgeInsets())
            .listRowBackground(Color.clear)
        } footer: {
            Text("Setting a new password signs the app out on every other device.")
        }
    }

    @ViewBuilder private var errorText: some View {
        if let errorMessage, !errorMessage.isEmpty {
            Text(errorMessage)
                .foregroundStyle(.loss)
                .accessibilityIdentifier("reset-error")
        }
    }

    private func sendCode() {
        guard !trimmedEmail.isEmpty else { return }
        run {
            do throws(SignInError) {
                try await session.requestPasswordReset(email: email)
                codesSent += 1
                code = ""
                step = .code
            } catch {
                errorMessage = error == .invalidInput
                    ? "Enter a valid email address."
                    : error.message(whileTryingTo: "send the code")
            }
        }
    }

    private func reset() {
        guard canReset else { return }
        run {
            do throws(SignInError) {
                try await session.resetPassword(email: email, code: code, newPassword: password)
                dismiss()
            } catch {
                errorMessage = error.message(whileTryingTo: "set the new password")
            }
        }
    }

    private func run(_ work: @escaping @MainActor () async -> Void) {
        guard !isBusy else { return }
        isBusy = true
        errorMessage = nil
        Task {
            await work()
            isBusy = false
        }
    }
}
