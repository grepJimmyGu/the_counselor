import Foundation
import LivermoreAPI
import OpenAPIRuntime

/// Runs backtests and saves the strategies behind them.
public struct BacktestService: Sendable {
    let client: Client

    public init(client: Client) {
        self.client = client
    }

    /// Runs a strategy over its date range.
    ///
    /// Signed in, this is the same call the website makes and counts against
    /// the same weekly quota; `templateID` marks a template run, which the
    /// backend does not hold to the custom-strategy limits.
    ///
    /// Signed out, it uses the anonymous endpoint: one run per visitor, on a
    /// template, after which the backend answers 402 and the app asks the user
    /// to sign in.
    public func run(
        _ strategy: StrategyJSON,
        templateID: String?,
        signedIn: Bool
    ) async throws(APIFailure) -> BacktestResult {
        if signedIn {
            let output = try await APIFailure.perform {
                try await client.runBacktestApiBacktestRunPost(
                    body: .json(.init(strategyJson: strategy, templateId: templateID))
                )
            }
            switch output {
            case .ok(let ok):
                guard case .json(let result) = ok.body else { throw .server(status: 200) }
                return result
            case .unprocessableContent:
                throw .rejected("Livermore couldn't read this strategy. Check the tickers and try again.")
            case .undocumented(let status, let payload):
                throw await APIFailure.from(status: status, payload: payload)
            }
        } else {
            let output = try await APIFailure.perform {
                try await client.anonymousBacktestRunApiAnonymousBacktestRunPost(
                    body: .json(.init(strategyJson: strategy, templateId: templateID ?? "custom"))
                )
            }
            switch output {
            case .ok(let ok):
                guard case .json(let result) = ok.body else { throw .server(status: 200) }
                return result
            case .unprocessableContent:
                throw .rejected("Livermore couldn't read this strategy. Check the tickers and try again.")
            case .undocumented(let status, let payload):
                throw await APIFailure.from(status: status, payload: payload)
            }
        }
    }

    /// Saves a strategy to the signed-in user's account, linked to the
    /// backtest that was just shown.
    public func save(
        title: String,
        strategy: StrategyJSON,
        backtestID: String?
    ) async throws(APIFailure) -> SavedStrategy {
        // The save endpoint takes the strategy as a free-form object, so the
        // typed value is re-encoded into that shape.
        let payload: Components.Schemas.SaveStrategyRequest.StrategyJsonPayload
        do {
            payload = try JSONDecoder().decode(
                Components.Schemas.SaveStrategyRequest.StrategyJsonPayload.self,
                from: JSONEncoder().encode(strategy)
            )
        } catch {
            throw .unreadable
        }
        let output = try await APIFailure.perform {
            try await client.createSavedStrategyApiSavedStrategiesPost(
                body: .json(.init(backtestRecordId: backtestID, isPublic: false, strategyJson: payload, title: title))
            )
        }
        switch output {
        case .created(let created):
            guard case .json(let saved) = created.body else { throw .server(status: 201) }
            return saved
        case .unprocessableContent:
            throw .rejected("Livermore couldn't save this strategy.")
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }
}
