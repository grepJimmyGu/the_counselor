import LivermoreKit
import SwiftUI

/// Changing the password while signed in: the current one, then a new one.
struct ChangePasswordView: View {
    @Environment(AppSession.self) private var session
    @Environment(\.dismiss) private var dismiss

    @State private var current = ""
    @State private var password = ""
    @State private var confirmation = ""
    @State private var isCurrentRevealed = false
    @State private var isRevealed = true
    @State private var isBusy = false
    @State private var keyboardIsUp = false
    @State private var errorMessage: String?
    @State private var didChange = false

    private var broken: [PasswordRule] {
        guard case .signedIn(let user) = session.state else { return [] }
        return PasswordPolicy.violations(
            password, email: user.email.isEmpty ? nil : user.email, displayName: user.displayName
        )
    }

    private var canSubmit: Bool {
        !current.isEmpty && broken.isEmpty && password == confirmation && !isBusy
    }

    var body: some View {
        Form {
            Section {
                PasswordRow(placeholder: "Current password", text: $current, isRevealed: $isCurrentRevealed)
                    .accessibilityIdentifier("current-password-field")
            } header: {
                Text("Current password")
            } footer: {
                Text("Asked again so that an unlocked phone is not enough to change it.")
            }
            Section {
                NewPasswordRows(
                    password: $password, confirmation: $confirmation, isRevealed: $isRevealed,
                    placeholder: "New password", onSubmit: submit
                )
            } header: {
                Text("New password")
            } footer: {
                if let errorMessage, !errorMessage.isEmpty {
                    Text(errorMessage)
                        .foregroundStyle(.loss)
                        .accessibilityIdentifier("change-password-error")
                }
            }
            PasswordChecklist(password: password, confirmation: confirmation, broken: broken)
            Section {
                Button(action: submit) {
                    HStack(spacing: 8) {
                        if isBusy { ProgressView().tint(.white) }
                        Text("Change password")
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(!canSubmit)
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
                .accessibilityIdentifier("change-password-button")
            } footer: {
                Text("Changing your password signs the app out on every other device. This one stays signed in.")
            }
        }
        .screenBackground()
        .navigationTitle("Change password")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if keyboardIsUp, !password.isEmpty {
                PasswordProgress(broken: broken, confirmed: confirmation.isEmpty ? nil : confirmation == password)
            }
        }
        .onKeyboardChange { keyboardIsUp = $0 }
        .onChange(of: current) { _, _ in if !isBusy { errorMessage = nil } }
        .onChange(of: password) { _, _ in if !isBusy { errorMessage = nil } }
        .alert("Password changed", isPresented: $didChange) {
            Button("OK") { dismiss() }
        } message: {
            Text("Use the new password the next time you sign in.")
        }
    }

    private func submit() {
        guard canSubmit else { return }
        isBusy = true
        errorMessage = nil
        Task {
            do throws(SignInError) {
                try await session.changePassword(current: current, new: password)
                didChange = true
            } catch {
                errorMessage = error.message
            }
            isBusy = false
        }
    }
}
