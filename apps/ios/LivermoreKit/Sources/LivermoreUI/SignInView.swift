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
    @State private var confirmFocus = 0
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
                if mode == .create { checklist }
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
            HStack(spacing: 12) {
                PasswordField(
                    placeholder: "Password",
                    text: $password,
                    isNew: mode == .create,
                    isRevealed: isRevealed,
                    generatorRules: PasswordPolicy.generatorRules,
                    hasNext: mode == .create,
                    onSubmit: { if mode == .signIn { submit() } else { confirmFocus += 1 } }
                )
                .accessibilityIdentifier("password-field")
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
            if mode == .create {
                PasswordField(
                    placeholder: "Type the password again",
                    text: $confirmation,
                    isNew: true,
                    isRevealed: isRevealed,
                    focusRequest: confirmFocus,
                    onSubmit: submit
                )
                .accessibilityIdentifier("password-confirm-field")
            }
        } footer: {
            if let errorMessage, !errorMessage.isEmpty {
                Text(errorMessage)
                    .foregroundStyle(.loss)
                    .accessibilityIdentifier("sign-in-error")
            }
        }
    }

    /// The rules, ticked off as the password comes to meet them.
    private var checklist: some View {
        Section {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(PasswordRule.required, id: \.self) { rule in
                    ChecklistRow(rule.label, state: password.isEmpty ? .pending : (broken.contains(rule) ? .pending : .met))
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

/// One line above the keyboard: what the password still lacks.
private struct PasswordProgress: View {
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
