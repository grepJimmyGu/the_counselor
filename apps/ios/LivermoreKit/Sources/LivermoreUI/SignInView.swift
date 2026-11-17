import LivermoreKit
import SwiftUI

struct SignInView: View {
    @Environment(AppSession.self) private var session

    @State private var email = ""
    @State private var password = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    private var canSubmit: Bool {
        !email.trimmingCharacters(in: .whitespaces).isEmpty && !password.isEmpty && !isSubmitting
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Email", text: $email)
                        .textContentType(.username)
                        .autocorrectionDisabled()
                    #if os(iOS)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                    #endif
                    SecureField("Password", text: $password)
                        .textContentType(.password)
                        .onSubmit(submit)
                } footer: {
                    if let errorMessage {
                        Text(errorMessage)
                            .foregroundStyle(.red)
                            .accessibilityIdentifier("sign-in-error")
                    }
                }

                Section {
                    Button(action: submit) {
                        HStack {
                            Text("Sign in")
                            if isSubmitting {
                                Spacer()
                                ProgressView()
                            }
                        }
                    }
                    .disabled(!canSubmit)
                    .accessibilityIdentifier("sign-in-button")
                } footer: {
                    Text("Use the email and password from your Livermore account. Research tool, not advice.")
                }
            }
            .navigationTitle("Sign in")
        }
    }

    private func submit() {
        guard canSubmit else { return }
        isSubmitting = true
        errorMessage = nil
        Task {
            do throws(SignInError) {
                try await session.signIn(email: email, password: password)
            } catch {
                errorMessage = error.message
            }
            isSubmitting = false
        }
    }
}
