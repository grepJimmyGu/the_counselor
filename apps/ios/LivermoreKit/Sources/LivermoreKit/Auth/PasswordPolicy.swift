import Foundation

/// One rule a new password must pass.
public enum PasswordRule: String, CaseIterable, Sendable {
    case length, lowercase, uppercase, number, symbol
    case `repeat`, sequence, personal

    /// What the password must contain. Shown as a checklist while typing.
    public static let required: [PasswordRule] = [.length, .lowercase, .uppercase, .number, .symbol]

    /// How the rule reads in the checklist, as the thing to have or avoid.
    public var label: String {
        switch self {
        case .length: "\(PasswordPolicy.minLength) to \(PasswordPolicy.maxLength) characters"
        case .lowercase: "A lowercase letter"
        case .uppercase: "An uppercase letter"
        case .number: "A number"
        case .symbol: "A symbol, such as ! or -"
        case .repeat: "The same character three times in a row"
        case .sequence: "A run of four, such as 1234 or abcd"
        case .personal: "Your name, your email or the word Livermore"
        }
    }
}

/// The rules a new password must pass.
///
/// The backend's `password_policy.py` is the copy that decides; this one lets
/// the form tick the rules off as the user types. Keep the two in step, or the
/// server refuses a password the form called good.
public enum PasswordPolicy {
    public static let minLength = 12
    public static let maxLength = 64
    /// bcrypt reads no further, so a longer password would have its tail ignored.
    static let maxBytes = 72
    static let maxRepeat = 2
    static let maxRun = 3
    static let serviceName = "livermore"
    /// A shorter name or email handle turns up inside ordinary words by accident.
    static let minPersonalLength = 4

    /// Tells the iPhone's password generator what to produce, so the password
    /// it proposes passes these rules. Apple's rule syntax:
    /// developer.apple.com/documentation/security/customizing-password-autofill-rules
    public static let generatorRules =
        "required: upper; required: lower; required: digit; required: [-!@#$%^&*_+=.?]; "
        + "max-consecutive: \(maxRepeat); minlength: \(minLength); maxlength: \(maxLength);"

    /// The rules `password` breaks, in the order they are listed.
    public static func violations(_ password: String, email: String? = nil, displayName: String? = nil) -> [PasswordRule] {
        // Unicode scalars, not Characters: the backend counts code points.
        let scalars = Array(password.unicodeScalars)
        var failed: [PasswordRule] = []
        if !(minLength...maxLength).contains(scalars.count) || password.utf8.count > maxBytes {
            failed.append(.length)
        }
        if !scalars.contains(where: \.properties.isLowercase) { failed.append(.lowercase) }
        if !scalars.contains(where: \.properties.isUppercase) { failed.append(.uppercase) }
        if !scalars.contains(where: isASCIIDigit) { failed.append(.number) }
        if !scalars.contains(where: isSymbol) { failed.append(.symbol) }
        if hasRepeat(scalars) { failed.append(.repeat) }
        if hasRun(scalars) { failed.append(.sequence) }
        let lowered = password.lowercased()
        if personalWords(email: email, displayName: displayName).contains(where: lowered.contains) {
            failed.append(.personal)
        }
        return failed
    }

    private static func isASCIIDigit(_ scalar: Unicode.Scalar) -> Bool {
        ("0"..."9").contains(scalar)
    }

    private static func isLetter(_ scalar: Unicode.Scalar) -> Bool {
        switch scalar.properties.generalCategory {
        case .uppercaseLetter, .lowercaseLetter, .titlecaseLetter, .modifierLetter, .otherLetter: true
        default: false
        }
    }

    /// Anything that is not a letter, a number or white space.
    private static func isSymbol(_ scalar: Unicode.Scalar) -> Bool {
        !isLetter(scalar) && scalar.properties.numericType == nil && !scalar.properties.isWhitespace
    }

    private static func hasRepeat(_ scalars: [Unicode.Scalar]) -> Bool {
        var streak = 1
        for (previous, current) in zip(scalars, scalars.dropFirst()) {
            streak = current == previous ? streak + 1 : 1
            if streak > maxRepeat { return true }
        }
        return false
    }

    /// Four neighbours in a row, up or down: 1234, dcba, WXYZ.
    private static func hasRun(_ scalars: [Unicode.Scalar]) -> Bool {
        // 0 for anything that cannot be part of a run, so kinds never match by accident.
        func kind(_ scalar: Unicode.Scalar) -> Int {
            guard scalar.isASCII else { return 0 }
            if isASCIIDigit(scalar) { return 1 }
            return scalar.properties.isAlphabetic ? 2 : 0
        }
        func folded(_ scalar: Unicode.Scalar) -> Int {
            let value = Int(scalar.value)
            return ("A"..."Z").contains(scalar) ? value + 32 : value
        }
        var streak = 1
        var direction = 0
        for (previous, current) in zip(scalars, scalars.dropFirst()) {
            let step = folded(current) - folded(previous)
            if kind(previous) != 0, kind(previous) == kind(current), abs(step) == 1 {
                streak = step == direction ? streak + 1 : 2
                direction = step
            } else {
                streak = 1
                direction = 0
            }
            if streak > maxRun { return true }
        }
        return false
    }

    private static func personalWords(email: String?, displayName: String?) -> [String] {
        var words = [serviceName]
        if let email, let handle = email.split(separator: "@", maxSplits: 1, omittingEmptySubsequences: false).first {
            // "jordan.lee@..." names both the whole handle and each part of it.
            words.append(String(handle))
            words += handle.split { !($0.isASCII && ($0.isLetter || $0.isNumber)) }.map(String.init)
        }
        if let displayName {
            words += displayName.split(whereSeparator: \.isWhitespace).map(String.init)
        }
        return words.filter { $0.unicodeScalars.count >= minPersonalLength }.map { $0.lowercased() }
    }
}
