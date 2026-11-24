import AuthenticationServices
import LivermoreKit
import SwiftUI

/// Sign in to an existing account, or create one.
struct SignInView: View {
    @Environment(AppSession.self) private var session
    @Environment(\.webAuthenticationSession) private var webAuthenticationSession

    private enum Mode: String, CaseIterable, Identifiable {
        case signIn = "Sign in"
        case create = "Create account"
        var id: String { rawValue }
    }

    @State private var mode: Mode = .signIn
    @State private var name = ""
    @State private var email = ""
    @State private var password = ""
    @State private var confirmation = ""
    /// Hidden while signing in, shown while choosing: a new password is typed
    /// once from nothing, and seeing it is how a typo gets caught.
    @State private var isRevealed = false
    @State private var isBusy = false
    @State private var keyboardIsUp = false
    @State private var isResettingPassword = false
    @State private var errorMessage: String?

    private var trimmedEmail: String { email.trimmingCharacters(in: .whitespaces) }

    private var broken: [PasswordRule] {
        PasswordPolicy.violations(password, email: trimmedEmail, displayName: name)
    }

    private var canSubmit: Bool {
        guard !trimmedEmail.isEmpty, !password.isEmpty, !isBusy else { return false }
        return mode == .signIn || (broken.isEmpty && password == confirmation)
    }

    var body: some View {
        NavigationStack {
            Form {
                header
                Section {
                    Picker("Mode", selection: $mode) {
                        ForEach(Mode.allCases) { Text($0.rawValue).tag($0) }
                    }
                    .pickerStyle(.segmented)
                    .accessibilityIdentifier("auth-mode")
                }
                .listRowBackground(Color.clear)
                .listRowInsets(EdgeInsets())

                if mode == .signIn, let saved = session.biometricEmail, let biometry = session.biometry {
                    Section {
                        Button(action: signInWithBiometrics) {
                            Label("Sign in with \(biometry.name)", systemImage: biometry.symbol)
                        }
                        .buttonStyle(SecondaryButtonStyle())
                        .disabled(isBusy)
                        .listRowInsets(EdgeInsets())
                        .listRowBackground(Color.clear)
                        .accessibilityIdentifier("biometric-sign-in-button")
                    } footer: {
                        Text("Signs in as \(saved).")
                    }
                }

                fields
                if mode == .create {
                    PasswordChecklist(password: password, confirmation: confirmation, broken: broken)
                }
                actions
            }
            .screenBackground()
            .navigationTitle("")
            // The checklist sits under the keyboard while the password is being
            // typed, so what is still missing is repeated just above the keys.
            .safeAreaInset(edge: .bottom, spacing: 0) {
                if mode == .create, keyboardIsUp, !password.isEmpty {
                    PasswordProgress(broken: broken, confirmed: confirmation.isEmpty ? nil : confirmation == password)
                }
            }
            .onKeyboardChange { keyboardIsUp = $0 }
            .sheet(isPresented: $isResettingPassword) {
                ForgotPasswordView(email: trimmedEmail)
            }
            // A message about the last attempt is stale once the password changes.
            .onChange(of: password) { _, _ in if !isBusy { errorMessage = nil } }
            .onChange(of: mode) { _, new in
                isRevealed = new == .create
                confirmation = ""
                if !isBusy { errorMessage = nil }
            }
        }
    }

    private var header: some View {
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
    }

    private var fields: some View {
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
            if mode == .create {
                NewPasswordRows(
                    password: $password, confirmation: $confirmation, isRevealed: $isRevealed, onSubmit: submit
                )
            } else {
                PasswordRow(placeholder: "Password", text: $password, isRevealed: $isRevealed, onSubmit: submit)
                    .accessibilityIdentifier("password-field")
                Button("Forgot password?") { isResettingPassword = true }
                    .font(.subheadline)
                    .accessibilityIdentifier("forgot-password")
            }
        } footer: {
            if let errorMessage, !errorMessage.isEmpty {
                Text(errorMessage)
                    .foregroundStyle(.loss)
                    .accessibilityIdentifier("sign-in-error")
            }
        }
    }

    private var actions: some View {
        Section {
            VStack(spacing: 12) {
                Button(action: submit) {
                    HStack(spacing: 8) {
                        if isBusy { ProgressView().tint(.white) }
                        Text(mode == .create ? "Create account" : "Sign in")
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(!canSubmit)
                .accessibilityIdentifier("sign-in-button")

                if session.google != nil {
                    HStack(spacing: 12) {
                        Rectangle().fill(Color.hairline).frame(height: 1)
                        Text("or").font(.footnote).foregroundStyle(.inkSecondary)
                        Rectangle().fill(Color.hairline).frame(height: 1)
                    }
                    GoogleButton(action: continueWithGoogle)
                        .disabled(isBusy)
                }
            }
            // The row clips to its bounds, which would shave the Google button's outline.
            .padding(.bottom, 1)
            .listRowInsets(EdgeInsets())
            .listRowBackground(Color.clear)
        } footer: {
            Text(mode == .create
                ? "A free account saves your strategies, tracks positions against them and lets you link your brokerage. The same account works on livermorealpha.com. Research tool, not advice."
                : "Use the email and password from your Livermore account. Research tool, not advice.")
        }
    }

    private func submit() {
        guard canSubmit else { return }
        run {
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
        }
    }

    private func signInWithBiometrics() {
        run {
            do throws(SignInError) {
                try await session.signInWithBiometrics()
            } catch {
                errorMessage = error.message
            }
        }
    }

    private func continueWithGoogle() {
        guard let google = session.google else { return }
        run {
            let attempt = google.begin()
            let callback: URL
            do {
                callback = try await webAuthenticationSession.authenticate(
                    using: attempt.url, callbackURLScheme: google.callbackScheme
                )
            } catch {
                // Closing the Google sheet is a choice, not a failure.
                let closed = (error as? ASWebAuthenticationSessionError)?.code == .canceledLogin
                if !closed { errorMessage = SignInError.googleFailed.message }
                return
            }
            let idToken: String
            do throws(GoogleSignInError) {
                idToken = try await google.idToken(from: callback, for: attempt)
            } catch {
                switch error {
                case .cancelled: break
                case .network: errorMessage = SignInError.network.message
                case .rejected: errorMessage = SignInError.googleFailed.message
                }
                return
            }
            do throws(SignInError) {
                try await session.signInWithGoogle(idToken: idToken)
            } catch {
                errorMessage = error.message
            }
        }
    }

    /// One sign-in at a time, whichever button started it.
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
