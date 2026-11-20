import LivermoreAPI
import LivermoreKit
import SwiftUI

/// News and community sentiment for one company. Loaded only when opened: the
/// backend may compute it on demand, so the company page does not ask for it.
struct SentimentView: View {
    @Environment(AppSession.self) private var session
    let symbol: String

    @State private var summary: SentimentSummary?
    @State private var error: ResearchError?

    var body: some View {
        Group {
            if let summary {
                loaded(summary)
            } else if let error {
                ContentUnavailableView {
                    Label("Sentiment unavailable", systemImage: "newspaper")
                } description: {
                    Text(error.message)
                } actions: {
                    Button("Try again") { Task { await load() } }
                }
            } else {
                ProgressView("Reading the news on \(symbol)…")
            }
        }
        .navigationTitle("News & sentiment")
        .task { await load() }
    }

    private func load() async {
        error = nil
        do throws(ResearchError) {
            summary = try await session.research.sentiment(symbol)
        } catch {
            self.error = error
        }
    }

    private func loaded(_ summary: SentimentSummary) -> some View {
        let scores = summary.scores
        return ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                if let asOf = summary.asOfDatetime {
                    Text("AS OF \(asOf.formatted(date: .abbreviated, time: .shortened).uppercased())")
                        .font(.caption2.weight(.semibold)).tracking(0.8).foregroundStyle(.secondary)
                }
                Card(summary.takeaway.takeawayLabel ?? "Takeaway") {
                    if let text = summary.takeaway.takeawaySummary { Text(text).font(.subheadline) }
                    if let action = summary.takeaway.suggestedUserAction {
                        Text(action).font(.subheadline).foregroundStyle(.secondary)
                    }
                }
                Card("Scores") {
                    Grid(horizontalSpacing: 12, verticalSpacing: 10) {
                        GridRow {
                            Stat("Overall signal", score(scores.overallSentimentSignalScore))
                            Stat("News", score(scores.newsSentimentScore))
                        }
                        GridRow {
                            Stat("Community", score(scores.communitySentimentScore))
                            Stat("Attention", score(scores.attentionScore))
                        }
                        GridRow {
                            Stat("Catalyst", score(scores.catalystScore))
                            Stat("Risk", score(scores.riskScore))
                        }
                    }
                    if let label = scores.overallLabel {
                        Text(label).font(.footnote).foregroundStyle(.secondary)
                    }
                }
                if let warnings = summary.warnings, !warnings.isEmpty {
                    Card("Caveats") {
                        ForEach(warnings, id: \.self) { Text("• \($0)").font(.footnote) }
                    }
                }
                if let disclaimer = summary.disclaimer {
                    Text(disclaimer).font(.caption).foregroundStyle(.secondary)
                }
            }
            .padding()
        }
        .background(Color.groupedBackground)
    }

    private func score(_ value: Int?) -> String {
        value.map { "\($0) / 100" } ?? "—"
    }
}
