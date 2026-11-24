import Foundation

/// Where an order ticket is, and the only moves allowed from there.
///
/// This is the one path in the app that ends in a real trade, so the rules
/// are kept out of the screen and under test:
///
///   editing ──price──▶ pricing ──answer──▶ priced ──send──▶ sending ──▶ sent
///      ▲                  │                   │                │
///      └──── any edit ────┴──── any edit ─────┘      failure ──┘ (back to editing)
///
/// - A price describes one order. Any edit discards it, including one made
///   while the price is still on its way.
/// - Sending is only possible from `priced`, and sends that preview.
/// - Nothing moves a ticket out of `sending` or `sent` except the broker's
///   answer.
public struct OrderTicketState: Equatable, Sendable {
    public enum Phase: Equatable, Sendable {
        case editing
        case pricing
        case priced(OrderPreview)
        case sending(OrderPreview)
        case sent(OrderReceipt, OrderPreview)
    }

    public private(set) var phase: Phase = .editing

    public init() {}

    /// A request is in flight; the order must not change under it.
    public var isBusy: Bool {
        switch phase {
        case .pricing, .sending: true
        case .editing, .priced, .sent: false
        }
    }

    public var isSent: Bool {
        if case .sent = phase { true } else { false }
    }

    /// The amount or the account changed.
    public mutating func edited() {
        switch phase {
        case .priced, .pricing: phase = .editing
        case .editing, .sending, .sent: break
        }
    }

    /// Returns false when a price can't be asked for from here.
    public mutating func beginPricing() -> Bool {
        guard phase == .editing else { return false }
        phase = .pricing
        return true
    }

    /// The broker priced `draft`. Kept only if the ticket is still waiting
    /// for a price and still shows that order.
    public mutating func priced(_ preview: OrderPreview, for draft: OrderDraft, current: OrderDraft) {
        guard phase == .pricing, draft == current else { return }
        phase = .priced(preview)
    }

    public mutating func pricingFailed() {
        if phase == .pricing { phase = .editing }
    }

    /// The preview to send, or nil when there is nothing priced to send.
    public mutating func beginSending() -> OrderPreview? {
        guard case .priced(let preview) = phase else { return nil }
        phase = .sending(preview)
        return preview
    }

    public mutating func sent(_ receipt: OrderReceipt) {
        guard case .sending(let preview) = phase else { return }
        phase = .sent(receipt, preview)
    }

    /// A failed send goes back to editing, not to `priced`: the old price may
    /// be stale or spent, so the order is priced again before a retry.
    public mutating func sendFailed() {
        if case .sending = phase { phase = .editing }
    }
}
