import LivermoreKit
import SwiftUI

/// The strategy templates a user can run, grouped the way the website groups
/// them.
struct TemplateGalleryView: View {
    /// When opened from a company page, the ticker to test single-stock
    /// templates on.
    var presetTicker: String?

    private var groups: [(category: String, templates: [StrategyTemplate])] {
        let runnable = TemplateCatalog.runnable
        var order: [String] = []
        for template in runnable where !order.contains(template.category) {
            order.append(template.category)
        }
        return order.map { category in (category, runnable.filter { $0.category == category }) }
    }

    var body: some View {
        List {
            if let presetTicker {
                Section {
                    Text("Single-stock templates will be set up on \(presetTicker). Templates that need several tickers start from their own list.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            ForEach(groups, id: \.category) { group in
                Section(group.category) {
                    ForEach(group.templates) { template in
                        NavigationLink {
                            TemplateSetupView(template: template, presetTicker: presetTicker)
                        } label: {
                            TemplateRow(template: template)
                        }
                    }
                }
            }
        }
        .navigationTitle("Strategy templates")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }
}

private struct TemplateRow: View {
    let template: StrategyTemplate

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(template.name).font(.body.weight(.medium))
            Text(template.description).font(.subheadline).foregroundStyle(.secondary).lineLimit(3)
            HStack(spacing: 6) {
                Tag(template.multiTicker ? "\(template.minimumTickers)+ tickers" : "One ticker")
                if let tier = template.evidenceTier { Tag("Evidence \(tier)") }
                if let horizon = template.horizonBadge { Tag(horizon) }
            }
        }
        .padding(.vertical, 2)
    }
}

struct Tag: View {
    let text: String

    init(_ text: String) {
        self.text = text
    }

    var body: some View {
        Text(text)
            .font(.caption2.weight(.medium))
            .padding(.horizontal, 7).padding(.vertical, 2)
            .background(.quaternary, in: Capsule())
    }
}
