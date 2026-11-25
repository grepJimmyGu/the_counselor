import LivermoreKit
import SwiftUI

/// How long a test covers and when it ends: a tap for the common lengths, a
/// month at a time for any other, and the dates it comes to in plain view.
struct BacktestPeriodPicker: View {
    @Binding var period: BacktestPeriod
    /// The longest period on offer here, and how far back it may end: a
    /// screen with less history than a strategy test has offers less.
    var longestMonths = BacktestPeriod.lengthLimits.upperBound
    var earliestEndMonthsAgo = BacktestPeriod.endLimits.upperBound

    private var span: String {
        "\(Fmt.tradingDay(period.start())) to \(Fmt.tradingDay(period.end()))"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                ForEach(BacktestPeriod.quickLengths.filter { $0.months <= longestMonths }, id: \.months) { choice in
                    let isSelected = period.months == choice.months
                    Button {
                        period.months = choice.months
                    } label: {
                        Text(choice.label)
                            .font(.subheadline.weight(.semibold))
                            .frame(maxWidth: .infinity, minHeight: 32)
                            .foregroundStyle(isSelected ? Color.white : .primary)
                            .background(isSelected ? Color.brand : Color.well, in: Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(isSelected ? .isSelected : [])
                    .accessibilityIdentifier("period-\(choice.label)")
                }
            }

            // + is always more: a longer test, a later end.
            Stepper(
                onIncrement: period.canLengthen && period.months < longestMonths ? { period.months += 1 } : nil,
                onDecrement: period.canShorten ? { period.months -= 1 } : nil
            ) {
                VStack(alignment: .leading, spacing: 1) {
                    Text("Length").font(.caption).foregroundStyle(.inkSecondary)
                    Text(period.lengthText).font(.subheadline.weight(.semibold).monospacedDigit())
                }
            }
            .accessibilityIdentifier("period-length")

            Stepper(
                onIncrement: period.canEndLater ? { period.endsMonthsAgo -= 1 } : nil,
                onDecrement: period.canEndEarlier && period.endsMonthsAgo < earliestEndMonthsAgo ? { period.endsMonthsAgo += 1 } : nil
            ) {
                VStack(alignment: .leading, spacing: 1) {
                    Text("Ends").font(.caption).foregroundStyle(.inkSecondary)
                    Text(period.endsToday ? "Today" : Fmt.tradingDay(period.end()))
                        .font(.subheadline.weight(.semibold).monospacedDigit())
                }
            }
            .accessibilityIdentifier("period-end")

            Text(span)
                .font(.caption.weight(.semibold).monospacedDigit())
                .foregroundStyle(.inkSecondary)
                .accessibilityIdentifier("period-span")
        }
    }
}
