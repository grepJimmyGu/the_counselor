import SwiftUI

#if canImport(UIKit)
import UIKit

/// A password box whose text can be shown or hidden without losing focus or
/// what was typed, and which tells the iPhone what kind of password it holds.
///
/// A UIKit text field rather than `SecureField` for two reasons SwiftUI has no
/// answer to: swapping a `SecureField` for a `TextField` drops the keyboard and
/// the cursor, and the rules the iPhone's password generator follows
/// (`passwordRules`) can only be set on a `UITextField`.
struct PasswordField: UIViewRepresentable {
    let placeholder: String
    @Binding var text: String
    /// A password being chosen, as opposed to one being entered to sign in.
    /// The iPhone offers to generate and save the first and to fill the second.
    var isNew = false
    var isRevealed = false
    /// Apple's password-rule syntax, for the generator. New passwords only.
    var generatorRules: String?
    /// True when Return moves on to another box rather than finishing.
    var hasNext = false
    /// Change this to move the cursor here.
    var focusRequest = 0
    var onSubmit: () -> Void = {}

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> UITextField {
        let field = UITextField()
        field.placeholder = placeholder
        field.delegate = context.coordinator
        field.addTarget(context.coordinator, action: #selector(Coordinator.changed(_:)), for: .editingChanged)
        // A shown password is an ordinary text field to the keyboard, which
        // would otherwise run it through word suggestions, an input method
        // such as Pinyin, and its learned dictionary. A hidden one never is.
        field.keyboardType = .asciiCapable
        field.autocapitalizationType = .none
        field.autocorrectionType = .no
        field.spellCheckingType = .no
        field.inlinePredictionType = .no
        // Otherwise "--" becomes a dash and a typed quote becomes a curly one,
        // and the password saved is not the password typed.
        field.smartDashesType = .no
        field.smartQuotesType = .no
        field.smartInsertDeleteType = .no
        field.font = .preferredFont(forTextStyle: .body)
        field.adjustsFontForContentSizeCategory = true
        field.setContentHuggingPriority(.defaultLow, for: .horizontal)
        field.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        return field
    }

    func updateUIView(_ field: UITextField, context: Context) {
        let coordinator = context.coordinator
        coordinator.parent = self
        if field.text != text { field.text = text }
        field.returnKeyType = hasNext ? .next : .done
        if coordinator.focusRequest != focusRequest {
            coordinator.focusRequest = focusRequest
            // Not during the view update that asked for it.
            DispatchQueue.main.async { field.becomeFirstResponder() }
        }
        let contentType: UITextContentType = isNew ? .newPassword : .password
        if field.textContentType != contentType { field.textContentType = contentType }
        field.passwordRules = isNew ? generatorRules.map { UITextInputPasswordRules(descriptor: $0) } : nil
        if field.isSecureTextEntry == isRevealed {
            field.isSecureTextEntry = !isRevealed
            // UIKit swaps in a different font when secure entry changes.
            field.font = .preferredFont(forTextStyle: .body)
        }
    }

    final class Coordinator: NSObject, UITextFieldDelegate {
        var parent: PasswordField
        var focusRequest: Int

        init(_ parent: PasswordField) {
            self.parent = parent
            self.focusRequest = parent.focusRequest
        }

        @objc func changed(_ field: UITextField) {
            parent.text = field.text ?? ""
        }

        func textField(_ field: UITextField, shouldChangeCharactersIn range: NSRange, replacementString string: String) -> Bool {
            // A hidden field that already holds text is wiped by UIKit on the
            // next keystroke after it regains focus or is hidden again. Apply
            // the edit by hand so hiding the password never costs the user it.
            guard field.isSecureTextEntry, let current = field.text, !current.isEmpty,
                  let swiftRange = Range(range, in: current)
            else { return true }
            field.text = current.replacingCharacters(in: swiftRange, with: string)
            parent.text = field.text ?? ""
            let offset = range.location + (string as NSString).length
            if let position = field.position(from: field.beginningOfDocument, offset: offset) {
                field.selectedTextRange = field.textRange(from: position, to: position)
            }
            return false
        }

        func textFieldShouldReturn(_ field: UITextField) -> Bool {
            // Moving on keeps the keyboard up instead of dropping and raising it.
            if !parent.hasNext { field.resignFirstResponder() }
            parent.onSubmit()
            return true
        }
    }
}

extension View {
    /// Reports the on-screen keyboard coming and going.
    func onKeyboardChange(_ action: @escaping (Bool) -> Void) -> some View {
        onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillShowNotification)) { _ in action(true) }
            .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillHideNotification)) { _ in action(false) }
    }
}

#else

extension View {
    func onKeyboardChange(_ action: @escaping (Bool) -> Void) -> some View { self }
}

/// The Mac build exists so the package compiles and tests without a simulator;
/// nothing ships from it, so the plain SwiftUI fields are enough.
struct PasswordField: View {
    let placeholder: String
    @Binding var text: String
    var isNew = false
    var isRevealed = false
    var generatorRules: String?
    var hasNext = false
    var focusRequest = 0
    var onSubmit: () -> Void = {}

    var body: some View {
        Group {
            if isRevealed {
                TextField(placeholder, text: $text)
            } else {
                SecureField(placeholder, text: $text)
            }
        }
        .onSubmit(onSubmit)
    }
}

#endif
