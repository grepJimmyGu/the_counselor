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

    /// Axis labels: "$12.5K", "$1.2M", "$850".
    static func compactMoney(_ v: Double) -> String {
        let a = abs(v)
        if a >= 1e6 { return String(format: "$%.1fM", v / 1e6) }
        if a >= 1e3 { return String(format: "$%.1fK", v / 1e3) }
        return String(format: "$%.0f", v)
    }

    /// A whole-dollar amount in full: "$25,000".
    static func wholeMoney(_ v: Double) -> String {
        v.formatted(.currency(code: "USD").precision(.fractionLength(0)))
    }

    /// Chart axis prices: "$352", "$1.2K", "$0.85".
    static func axisPrice(_ v: Double) -> String {
        let a = abs(v)
        if a >= 10_000 { return String(format: "$%.1fK", v / 1e3) }
        if a >= 100 { return String(format: "$%.0f", v) }
        if a >= 10 { return String(format: "$%.1f", v) }
        return String(format: "$%.2f", v)
    }

    /// A difference between two percentages, in points: "+12.3 pts".
    static func points(_ fraction: Double) -> String {
        String(format: "%+.1f pts", fraction * 100)
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
