import Foundation
import LivermoreKit
import SwiftUI

enum Fmt {
    /// "$5.1T", "$43.8B", "$920M" — the web's `fmtMoney`.
    static func money(_ v: Double?) -> String {
        guard let v else { return "—" }
        let a = abs(v)
        if a >= 1e12 { return String(format: "$%.1fT", v / 1e12) }
        if a >= 1e9 { return String(format: "$%.1fB", v / 1e9) }
        if a >= 1e6 { return String(format: "$%.0fM", v / 1e6) }
        return String(format: "$%.0f", v)
    }

    static func price(_ v: Double?) -> String {
        guard let v else { return "—" }
        return v.formatted(.currency(code: "USD").precision(.fractionLength(2)))
    }

    /// A fraction as a percentage: 0.151 → "15.1%".
    static func percent(_ v: Double?, signed: Bool = false) -> String {
        guard let v else { return "—" }
        let text = String(format: "%.1f%%", v * 100)
        return signed && v > 0 ? "+" + text : text
    }

    /// A value that is already in percent units: -0.98 → "-0.98%".
    static func percentPoints(_ v: Double?) -> String {
        guard let v else { return "—" }
        return String(format: "%+.2f%%", v)
    }

    /// Share counts: whole numbers without a decimal, fractions as typed.
    static func shares(_ v: Double) -> String {
        v == v.rounded() ? String(Int(v)) : String(format: "%.4g", v)
    }

    /// A dollar gain or loss: "+$412.50", "-$88.10".
    static func signedMoney(_ v: Double) -> String {
        (v < 0 ? "-" : "+") + abs(v).formatted(.currency(code: "USD").precision(.fractionLength(2)))
    }

    static func multiple(_ v: Double?) -> String {
        guard let v else { return "—" }
        return String(format: "%.1fx", v)
    }
}

extension ScoreStatus {
    var color: Color {
        switch self {
        case .strong: .green
        case .neutral: .orange
        case .weak: .red
        }
    }

    var label: String { rawValue.capitalized }
}

extension Double {
    /// Green when up, red when down, grey when flat.
    var changeColor: Color { self > 0 ? .green : self < 0 ? .red : .secondary }
}
