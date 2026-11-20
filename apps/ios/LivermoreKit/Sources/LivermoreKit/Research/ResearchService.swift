import Foundation
import LivermoreAPI
import OpenAPIRuntime

public typealias CompanyOverview = Components.Schemas.CompanyOverviewResponse
public typealias CompanyTrend = Components.Schemas.TrendSection
public typealias LiveQuote = Components.Schemas.LiveQuoteOut
public typealias SymbolMatch = Components.Schemas.SymbolSearchItem
public typealias SentimentSummary = Components.Schemas.SentimentSummaryResponse
public typealias SupplyChainSummary = Components.Schemas.SupplyChainSummaryResponse

public typealias ResearchError = APIFailure

/// Read-only company research calls.
public struct ResearchService: Sendable {
    let client: Client

    public init(client: Client) {
        self.client = client
    }

    // MARK: Search

    public func search(_ query: String) async throws(ResearchError) -> [SymbolMatch] {
        let query = query.trimmingCharacters(in: .whitespaces)
        guard !query.isEmpty else { return [] }
        let output = try await APIFailure.perform { try await client.searchSymbolsApiSymbolsSearchGet(query: .init(query: query)) }
        switch output {
        case .ok(let ok):
            guard case .json(let items) = ok.body else { throw .server(status: 200) }
            return Self.rank(items, for: query)
        case .unprocessableContent:
            return []
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    /// The search endpoint returns foreign listings first — "AAPL" comes back
    /// as Toronto and São Paulo depositary lines before Apple itself — and the
    /// company page only covers US tickers. So: an exact ticker match first,
    /// then US listings, then the rest, keeping the backend's order within
    /// each group.
    static func rank(_ items: [SymbolMatch], for query: String) -> [SymbolMatch] {
        let wanted = query.uppercased()
        func tier(_ item: SymbolMatch) -> Int {
            if item.symbol.uppercased() == wanted { return 0 }
            return isUSListing(item) ? 1 : 2
        }
        return items.enumerated()
            .sorted { (tier($0.element), $0.offset) < (tier($1.element), $1.offset) }
            .map(\.element)
    }

    public static func isUSListing(_ item: SymbolMatch) -> Bool {
        if let region = item.region { return region == "United States" }
        return !item.symbol.contains(".")
    }

    // MARK: Company

    public func overview(_ symbol: String) async throws(ResearchError) -> CompanyOverview {
        let output = try await APIFailure.perform {
            try await client.getCompanyOverviewApiCompanySymbolOverviewGet(path: .init(symbol: symbol))
        }
        switch output {
        case .ok(let ok):
            guard case .json(let overview) = ok.body else { throw .server(status: 200) }
            return overview
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    public func trend(_ symbol: String) async throws(ResearchError) -> CompanyTrend {
        let output = try await APIFailure.perform {
            try await client.getCompanyTrendApiCompanySymbolTrendGet(path: .init(symbol: symbol))
        }
        switch output {
        case .ok(let ok):
            guard case .json(let trend) = ok.body else { throw .server(status: 200) }
            return trend
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    public func quotes(_ symbols: [String]) async throws(ResearchError) -> [String: LiveQuote] {
        guard !symbols.isEmpty else { return [:] }
        let output = try await APIFailure.perform {
            try await client.getLiveQuotesApiLiveQuotesGet(query: .init(symbols: symbols.joined(separator: ",")))
        }
        switch output {
        case .ok(let ok):
            guard case .json(let response) = ok.body else { throw .server(status: 200) }
            return response.quotes.additionalProperties
        case .unprocessableContent:
            return [:]
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    public func sentiment(_ symbol: String) async throws(ResearchError) -> SentimentSummary {
        let output = try await APIFailure.perform {
            try await client.getSentimentSummaryApiSentimentSymbolSummaryGet(path: .init(symbol: symbol))
        }
        switch output {
        case .ok(let ok):
            guard case .json(let summary) = ok.body else { throw .server(status: 200) }
            return summary
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    public func supplyChain(_ symbol: String) async throws(ResearchError) -> SupplyChainSummary {
        let output = try await APIFailure.perform {
            try await client.getSummaryApiSupplyChainSymbolSummaryGet(path: .init(symbol: symbol))
        }
        switch output {
        case .ok(let ok):
            guard case .json(let summary) = ok.body else { throw .server(status: 200) }
            return summary
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }
}
