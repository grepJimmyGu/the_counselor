import LivermoreKit
import SwiftUI

/// A conversation with the agent.
struct AgentChatView: View {
    @Environment(AppSession.self) private var session
    /// A first message to send as the screen opens.
    var starter: String?

    @State private var conversation: AgentConversation?
    @State private var input = ""
    @State private var draft: DraftItem?
    @State private var sentStarter = false
    @FocusState private var inputFocused: Bool

    private static let suggestions = [
        "What needs my attention?",
        "How concentrated is my portfolio?",
        "What does my trading record say about how I sell?",
        "What did NVDA's latest filing show?",
    ]

    private var chatAvailable: Bool { session.agent.profile?.chatAvailable ?? true }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    if !chatAvailable {
                        Notice(
                            text: "The conversation isn't switched on at Livermore's server yet. Your agent's checks and findings work without it.",
                            systemImage: "exclamationmark.triangle.fill", tint: .caution
                        )
                    }
                    if let conversation {
                        if conversation.messages.isEmpty { suggestions }
                        ForEach(conversation.messages) { message in
                            MessageBubble(message: message, onReview: { draft = DraftItem(draft: $0) })
                                .id(message.id)
                        }
                        if let activity = conversation.activity {
                            HStack(spacing: 8) {
                                ProgressView().controlSize(.small)
                                Text(activity).font(.footnote).foregroundStyle(.inkSecondary)
                            }
                            .accessibilityIdentifier("agent-activity")
                        }
                    }
                    Color.clear.frame(height: 1).id("end")
                }
                .padding(Metrics.screenPadding)
            }
            .onChange(of: conversation?.messages.last?.text) { _, _ in
                withAnimation(.easeOut(duration: 0.15)) { proxy.scrollTo("end", anchor: .bottom) }
            }
        }
        .screenBackground()
        .navigationTitle("Your agent")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .safeAreaInset(edge: .bottom, spacing: 0) { inputBar }
        .sheet(item: $draft) { AgentOrderSheet(draft: $0.draft) }
        .task {
            if conversation == nil { conversation = session.newAgentConversation() }
            if let starter, !sentStarter {
                sentStarter = true
                await conversation?.send(starter)
            }
        }
    }

    private var suggestions: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Ask about what you hold and watch. Every figure comes from your own data, and the agent cannot place an order: it drafts, you decide.")
                .font(.subheadline).foregroundStyle(.inkSecondary)
            ForEach(Self.suggestions, id: \.self) { text in
                Button {
                    send(text)
                } label: {
                    Text(text)
                        .font(.subheadline.weight(.medium))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                        .background(Color.surface, in: RoundedRectangle(cornerRadius: Metrics.tileRadius, style: .continuous))
                }
                .buttonStyle(.plain)
                .disabled(!chatAvailable)
            }
        }
    }

    private var inputBar: some View {
        HStack(alignment: .bottom, spacing: 8) {
            TextField("Ask your agent", text: $input, axis: .vertical)
                .lineLimit(1...4)
                .focused($inputFocused)
                .padding(.horizontal, 14).padding(.vertical, 10)
                .background(Color.well, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                .accessibilityIdentifier("agent-input")
            Button(action: sendInput) {
                Image(systemName: "arrow.up.circle.fill").font(.system(size: 32))
            }
            .disabled(input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                || conversation?.isAnswering == true || !chatAvailable)
            .accessibilityLabel("Send")
            .accessibilityIdentifier("agent-send")
        }
        .padding(.horizontal, Metrics.screenPadding)
        .padding(.vertical, 8)
        .background(.bar)
    }

    private func send(_ text: String) {
        guard let conversation else { return }
        Task { await conversation.send(text) }
    }

    /// Sends what is in the box.
    ///
    /// With an input method such as Pinyin, the letters still being composed
    /// are on screen but not yet in `input`: sending straight away sent
    /// "Trim AAPL to" for "Trim AAPL to my limit" and left the rest behind.
    /// Leaving the field ends the composition, so the box is read after that.
    private func sendInput() {
        inputFocused = false
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(80))
            let text = input
            input = ""
            send(text)
        }
    }
}

private struct MessageBubble: View {
    let message: AgentConversation.Message
    let onReview: (OrderSuggestion) -> Void

    private var isUser: Bool { message.role == .user }

    var body: some View {
        VStack(alignment: isUser ? .trailing : .leading, spacing: 8) {
            if !message.text.isEmpty {
                Text(message.text)
                    .font(.body)
                    .foregroundStyle(isUser ? Color.white : Color.primary)
                    .padding(.horizontal, 14).padding(.vertical, 10)
                    .background(isUser ? Color.brand : Color.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .textSelection(.enabled)
            }
            ForEach(Array(message.drafts.enumerated()), id: \.offset) { _, order in
                DraftCard(order: order) { onReview(order) }
            }
            if let failure = message.failure {
                Notice(text: failure, systemImage: "exclamationmark.triangle.fill", tint: .caution)
            }
        }
        .frame(maxWidth: .infinity, alignment: isUser ? .trailing : .leading)
        .padding(isUser ? .leading : .trailing, 40)
    }
}

/// An order the agent drafted. It is a proposal on screen and nothing more
/// until the user opens the ticket and confirms it.
private struct DraftCard: View {
    let order: OrderSuggestion
    let onReview: () -> Void

    private var size: String {
        if let units = order.units { return "\(units.formatted(.number.precision(.fractionLength(0...4)))) shares" }
        if let amount = order.amountUSD { return amount.formatted(.currency(code: "USD").precision(.fractionLength(0...2))) }
        return ""
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("DRAFT ORDER · NOT SENT").font(Font.caption2.weight(.semibold)).tracking(0.6).foregroundStyle(.inkSecondary)
            Text("\(order.side == .buy ? "Buy" : "Sell") \(size) of \(order.symbol)").font(.headline)
            if let reason = order.reason { Text(reason).font(.footnote).foregroundStyle(.inkSecondary) }
            Button("Review the order", action: onReview)
                .buttonStyle(PrimaryButtonStyle())
                .accessibilityIdentifier("draft-review-order")
        }
        .padding(Metrics.cardPadding)
        .background(Color.surface, in: RoundedRectangle(cornerRadius: Metrics.cardRadius, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Metrics.cardRadius, style: .continuous).strokeBorder(Color.hairline))
    }
}
