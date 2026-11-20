import Testing

@testable import LivermoreKit

private let draft = OrderDraft(accountID: "a", symbol: "AAPL", size: .sell(shares: 25))
private let other = OrderDraft(accountID: "a", symbol: "AAPL", size: .sell(shares: 10))
private let preview = OrderPreview(action: "SELL", symbol: "AAPL", tradeId: "t-1", units: 25)
private let receipt = OrderReceipt(brokerageOrderId: "B-1", status: "ACCEPTED")

/// A ticket that has been priced for `draft`.
private func pricedTicket() -> OrderTicketState {
    var ticket = OrderTicketState()
    _ = ticket.beginPricing()
    ticket.priced(preview, for: draft, current: draft)
    return ticket
}

@Suite("order ticket: what can happen, and in what order")
struct OrderTicketStateTests {
    @Test("the only way to sent is fill in, price, send")
    func happyPath() {
        var ticket = OrderTicketState()
        #expect(ticket.phase == .editing)
        let step1 = ticket.beginPricing()
        #expect(step1)
        #expect(ticket.isBusy)
        ticket.priced(preview, for: draft, current: draft)
        #expect(ticket.phase == .priced(preview))
        let step2 = ticket.beginSending()
        #expect(step2 == preview)
        #expect(ticket.isBusy)
        ticket.sent(receipt)
        #expect(ticket.phase == .sent(receipt, preview))
        #expect(ticket.isSent)
    }

    @Test("nothing can be sent that has not been priced")
    func noSendWithoutPrice() {
        var ticket = OrderTicketState()
        let step3 = ticket.beginSending()
        #expect(step3 == nil)
        _ = ticket.beginPricing()
        let step4 = ticket.beginSending()
        #expect(step4 == nil)
        // A receipt with no send in flight changes nothing.
        ticket.sent(receipt)
        #expect(ticket.phase == .pricing)
    }

    @Test("editing a priced order throws the price away")
    func editDiscardsPrice() {
        var ticket = pricedTicket()
        ticket.edited()
        #expect(ticket.phase == .editing)
        let step5 = ticket.beginSending()
        #expect(step5 == nil)
    }

    // Regression: an edit while the price was on its way left the ticket in
    // `pricing` for good — the late answer was dropped and nothing moved it on.
    @Test("an edit while pricing returns to editing, and the late answer is ignored")
    func editWhilePricing() {
        var ticket = OrderTicketState()
        _ = ticket.beginPricing()
        ticket.edited()
        #expect(ticket.phase == .editing)
        #expect(!ticket.isBusy)

        // The broker's answer for the old amount arrives now.
        ticket.priced(preview, for: draft, current: other)
        #expect(ticket.phase == .editing)
        // And the changed order can be priced.
        let step6 = ticket.beginPricing()
        #expect(step6)
    }

    @Test("a price for an order that is no longer on screen is not kept")
    func stalePrice() {
        var ticket = OrderTicketState()
        _ = ticket.beginPricing()
        ticket.priced(preview, for: draft, current: other)
        #expect(ticket.phase == .pricing)
    }

    @Test("a second price can't be requested while one is out, or after sending")
    func oneRequestAtATime() {
        var ticket = OrderTicketState()
        let step7 = ticket.beginPricing()
        #expect(step7)
        let step8 = ticket.beginPricing()
        #expect(!step8)

        var sending = pricedTicket()
        _ = sending.beginSending()
        let step9 = sending.beginPricing()
        #expect(!step9)
        sending.sent(receipt)
        let step10 = sending.beginPricing()
        #expect(!step10)
    }

    @Test("an order in flight or sent cannot be edited out from under its request")
    func lockedWhileSending() {
        var ticket = pricedTicket()
        _ = ticket.beginSending()
        ticket.edited()
        #expect(ticket.phase == .sending(preview))
        ticket.sent(receipt)
        ticket.edited()
        #expect(ticket.phase == .sent(receipt, preview))
    }

    @Test("a failed price or send goes back to editing — a failed send must be priced again")
    func failures() {
        var pricing = OrderTicketState()
        _ = pricing.beginPricing()
        pricing.pricingFailed()
        #expect(pricing.phase == .editing)

        var sending = pricedTicket()
        _ = sending.beginSending()
        sending.sendFailed()
        #expect(sending.phase == .editing)
        let step11 = sending.beginSending()
        #expect(step11 == nil)

        // Failure callbacks for requests that are not in flight do nothing.
        var priced = pricedTicket()
        priced.pricingFailed()
        priced.sendFailed()
        #expect(priced.phase == .priced(preview))
    }
}
