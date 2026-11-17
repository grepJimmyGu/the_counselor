import LivermoreKit
import SwiftUI

/// The strategy library: every template a user can run, as a card that says
/// what it does, what it needs and what history suggests.
struct TemplateGalleryView: View {
    /// When opened from a company page, the ticker to test single-stock
    /// templates on.
    var presetTicker: String?

    @State private var category: String?

    private var categories: [String] {
        var order: [String] = []
        for template in TemplateCatalog.runnable where !order.contains(template.category) {
            order.append(template.category)
        }
        return order
    }

    private var shown: [StrategyTemplate] {
        TemplateCatalog.runnable.filter { category == nil || $0.category == category }
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: Metrics.sectionSpacing) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Strategy library").font(.largeTitle.weight(.bold))
                    Text(presetTicker.map { "Rules-based strategies you can test on \($0), change to suit you, and save." }
                        ?? "Rules-based strategies from the research literature. Test one on your tickers, change it to suit you, and save it.")
                        .font(.subheadline).foregroundStyle(.inkSecondary)
                }
                .padding(.horizontal, 4)

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        FilterChip(title: "All", isOn: category == nil) { category = nil }
                        ForEach(categories, id: \.self) { name in
                            FilterChip(title: name, isOn: category == name) { category = name }
                        }
                    }
                    .padding(.horizontal, 4)
                }
                .sensoryFeedback(.selection, trigger: category)

                if let presetTicker {
                    let single = shown.filter { !$0.multiTicker }
                    let basket = shown.filter(\.multiTicker)
                    if !single.isEmpty {
                        Text("Runs on \(presetTicker) alone").eyebrowStyle().padding(.horizontal, 4)
                        cards(single)
                    }
                    if !basket.isEmpty {
                        Text("Needs a basket of tickers").eyebrowStyle().padding(.horizontal, 4).padding(.top, 4)
                        cards(basket)
                    }
                } else {
                    cards(shown)
                }

                Text("Past performance ranges come from published research on each strategy. They are not forecasts. Research tool, not advice.")
                    .font(.caption2).foregroundStyle(.inkSecondary).padding(.horizontal, 4)
            }
            .padding(Metrics.screenPadding)
        }
        .screenBackground()
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }

    private func cards(_ templates: [StrategyTemplate]) -> some View {
        ForEach(templates) { template in
            NavigationLink {
                TemplateSetupView(template: template, presetTicker: presetTicker)
            } label: {
                TemplateCard(template: template)
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("template-\(template.id)")
        }
    }
}

private struct FilterChip: View {
    let title: String
    let isOn: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.subheadline.weight(.semibold))
                .padding(.horizontal, 14).padding(.vertical, 8)
                .foregroundStyle(isOn ? Color.white : .primary)
                .background(isOn ? Color.brand : Color.surface, in: Capsule())
                .overlay(Capsule().strokeBorder(Color.hairline.opacity(isOn ? 0 : 0.8), lineWidth: 0.5))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(isOn ? .isSelected : [])
    }
}

private struct TemplateCard: View {
    let template: StrategyTemplate

    var body: some View {
        Card {
            HStack(alignment: .top, spacing: 12) {
                CategoryIcon(category: template.category)
                VStack(alignment: .leading, spacing: 3) {
                    Text(template.category).eyebrowStyle()
                    Text(template.name).font(.headline)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
            }
            Text(template.summary).font(.subheadline).foregroundStyle(.inkSecondary).lineLimit(3)

            let typical = StrategyTemplate.headlineRange(template.perfContext?.returnRange)
            let worst = StrategyTemplate.headlineRange(template.perfContext?.worstStretch)
            if typical != nil || worst != nil {
                HStack(spacing: 8) {
                    if let typical { StatTile(label: "Typical, per year", value: typical, tint: .gain, compact: true) }
                    if let worst { StatTile(label: "Worst stretch", value: worst, tint: .loss, compact: true) }
                }
            }
            TemplateTags(template: template)
        }
        .contentShape(Rectangle())
    }
}

/// What a template needs and how well supported it is, as tags.
struct TemplateTags: View {
    let template: StrategyTemplate

    var body: some View {
        HStack(spacing: 6) {
            Tag(template.multiTicker ? "\(template.minimumTickers)+ tickers" : "One ticker", systemImage: "number")
            if let horizon = template.horizonBadge { Tag(horizon, systemImage: "clock") }
            if let tier = template.evidenceTier {
                Tag("Evidence \(tier)", tint: tier == "A" ? .gain : tier == "B" ? .brand : .caution, systemImage: "checkmark.seal.fill")
            }
            if template.availability == "proxy" { Tag("ETF proxy", tint: .caution) }
        }
    }
}

/// A category's mark: the same icon and colour wherever the strategy appears.
struct CategoryIcon: View {
    let category: String
    var size: CGFloat = 44

    private var symbol: String {
        switch category {
        case "Momentum": "arrow.up.right"
        case "Rotation": "arrow.triangle.2.circlepath"
        case "Reversal": "arrow.uturn.backward"
        case "Arbitrage": "arrow.left.arrow.right"
        case "Factor": "square.stack.3d.up"
        case "Carry": "shippingbox"
        default: "function"
        }
    }

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: size * 0.42, weight: .semibold))
            .foregroundStyle(.brand)
            .frame(width: size, height: size)
            .background(Color.brand.opacity(0.10), in: RoundedRectangle(cornerRadius: size * 0.27, style: .continuous))
            .accessibilityHidden(true)
    }
}
