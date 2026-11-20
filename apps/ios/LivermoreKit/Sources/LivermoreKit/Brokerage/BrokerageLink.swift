import Foundation
import Observation

/// The user's brokerage link as the app last saw it: whether there is one,
/// which accounts, what they hold. Shared so the Actions tab, a strategy page
/// and an order ticket agree.
@MainActor
@Observable
public final class BrokerageLink {
    /// nil until the first load finishes.
    public private(set) var status: BrokerageStatus?
    public private(set) var accounts: [BrokerAccount] = []
    public private(set) var holdings: [BrokerHolding] = []
    public private(set) var failure: APIFailure?
    public private(set) var loadedAt: Date?
    public private(set) var isLoading = false

    @ObservationIgnored var onSessionExpired: (@MainActor () -> Void)?
    private let service: BrokerageService

    init(service: BrokerageService) {
        self.service = service
    }

    public var isLinked: Bool { status?.isLinked == true }
    public var canTrade: Bool { status?.canTrade == true }

    public func refresh() async {
        isLoading = true
        defer { isLoading = false }
        do throws(APIFailure) {
            let status = try await service.status()
            self.status = status
            failure = nil
            guard status.isLinked else {
                accounts = []
                holdings = []
                loadedAt = .now
                return
            }
            // Accounts and holdings are independent reads of the same link.
            async let accountRows = Result<[BrokerAccount], APIFailure>.capture { [service] () async throws(APIFailure) in
                try await service.accounts()
            }
            async let holdingRows = Result<[BrokerHolding], APIFailure>.capture { [service] () async throws(APIFailure) in
                try await service.holdings()
            }
            switch (await accountRows, await holdingRows) {
            case (.success(let accounts), .success(let holdings)):
                self.accounts = accounts
                self.holdings = holdings
                loadedAt = .now
            case (.failure(let error), _), (_, .failure(let error)):
                failure = error
            }
        } catch {
            if error == .notSignedIn { onSessionExpired?() }
            failure = error
        }
    }

    /// The user's holding of `symbol` at their broker, if any. With the same
    /// stock in two accounts, the larger holding — the one a sell would most
    /// plausibly come from; the ticket shows which account it is.
    public func holding(of symbol: String) -> BrokerHolding? {
        holdings
            .filter { $0.symbol.uppercased() == symbol.uppercased() && $0.cashEquivalent != true && $0.units > 0 }
            .max { $0.units < $1.units }
    }

    public func account(id: String) -> BrokerAccount? {
        accounts.first { $0.id == id }
    }

    func reset() {
        status = nil
        accounts = []
        holdings = []
        failure = nil
        loadedAt = nil
    }
}
