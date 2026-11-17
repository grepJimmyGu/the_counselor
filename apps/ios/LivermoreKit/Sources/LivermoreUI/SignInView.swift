import LivermoreKit
import SwiftUI

/// Sign in to an existing account, or create one.
struct SignInView: View {
    @Environment(AppSession.self) private var session

    private enum Mode: String, CaseIterable, Identifiable {
        case signIn = "Sign in"
        case create = "Create account"
        var id: String { rawValue }
    }

    @State private var mode: Mode = .signIn
    @State private var name = ""
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
                    VStack(alignment: .leading, spacing: 8) {
                        Image(systemName: "chart.line.uptrend.xyaxis")
                            .font(.title2.weight(.semibold)).foregroundStyle(.white)
                            .frame(width: 52, height: 52)
                            .background(Color.brand, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        Text("Livermore").font(.largeTitle.weight(.bold))
                        Text("Research a company, test a strategy on it, and act on it through your own broker.")
                            .font(.subheadline).foregroundStyle(.inkSecondary)
                    }
                    .padding(.vertical, 4)
                    // Zero row insets put the text on the clip edge.
                    .padding(.horizontal, 4)
                }
                .listRowBackground(Color.clear)
                .listRowInsets(EdgeInsets())

                Section {
                    Picker("Mode", selection: $mode) {
                        ForEach(Mode.allCases) { Text($0.rawValue).tag($0) }
                    }
                    .pickerStyle(.segmented)
                    .accessibilityIdentifier("auth-mode")
                }
                .listRowBackground(Color.clear)
                .listRowInsets(EdgeInsets())

                Section {
                    if mode == .create {
                        TextField("Name (optional)", text: $name)
                            .textContentType(.name)
                    }
                    TextField("Email", text: $email)
                        .textContentType(.username)
                        .autocorrectionDisabled()
                    #if os(iOS)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                    #endif
                    SecureField("Password", text: $password)
                        .textContentType(mode == .create ? .newPassword : .password)
                        .onSubmit(submit)
                } footer: {
                    VStack(alignment: .leading, spacing: 4) {
                        if mode == .create {
                            Text("At least \(AppSession.minimumPasswordLength) characters.")
                        }
                        if let errorMessage {
                            Text(errorMessage)
                                .foregroundStyle(.loss)
                                .accessibilityIdentifier("sign-in-error")
                        }
                    }
                }

                Section {
                    Button(action: submit) {
                        HStack(spacing: 8) {
                            if isSubmitting { ProgressView().tint(.white) }
                            Text(mode == .create ? "Create account" : "Sign in")
                        }
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(!canSubmit)
                    .listRowInsets(EdgeInsets())
                    .listRowBackground(Color.clear)
                    .accessibilityIdentifier("sign-in-button")
                } footer: {
                    Text(mode == .create
                        ? "A free account saves your strategies, tracks positions against them and lets you link your brokerage. The same account works on livermorealpha.com. Research tool, not advice."
                        : "Use the email and password from your Livermore account. Research tool, not advice.")
                }
            }
            .screenBackground()
            .navigationTitle("")
            .onChange(of: mode) { _, _ in if !isSubmitting { errorMessage = nil } }
        }
    }

    private func submit() {
        guard canSubmit else { return }
        isSubmitting = true
        errorMessage = nil
        Task {
            do throws(SignInError) {
                switch mode {
                case .signIn: try await session.signIn(email: email, password: password)
                case .create: try await session.signUp(email: email, password: password, displayName: name)
                }
            } catch {
                // The address is taken: the next thing to try is signing in.
                if error == .emailTaken { mode = .signIn }
                errorMessage = error.message
            }
            isSubmitting = false
        }
    }
}
