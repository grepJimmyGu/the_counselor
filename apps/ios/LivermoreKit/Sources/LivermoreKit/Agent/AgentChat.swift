import Foundation
import Observation

/// One thing the backend said while the agent was answering.
public enum AgentChatEvent: Equatable, Sendable {
    /// More of the answer.
    case token(String)
    /// The agent started looking something up.
    case toolStarted(name: String)
    /// It finished, and may have something for the app to show.
    case toolFinished(name: String, action: AgentAction?)
    case done
    case failed(String)

    /// Reads one line of the stream. The backend sends `data: {json}` lines
    /// with a `type`; anything else (blank lines, types this build does not
    /// know) is nil and skipped.
    public static func parse(line: String) -> AgentChatEvent? {
        guard line.hasPrefix("data: "),
              let json = try? JSONSerialization.jsonObject(with: Data(line.dropFirst(6).utf8)) as? [String: Any]
        else { return nil }
        switch json["type"] as? String {
        case "token":
            guard let text = json["text"] as? String, !text.isEmpty else { return nil }
            return .token(text)
        case "tool_call_start":
            return .toolStarted(name: json["name"] as? String ?? "")
        case "tool_result":
            let action = (json["client"] as? [String: Any]).flatMap(AgentAction.init(json:))
            return .toolFinished(name: json["name"] as? String ?? "", action: action)
        case "done":
            return .done
        case "error":
            return .failed(json["message"] as? String ?? "The agent could not answer.")
        default:
            return nil
        }
    }

    /// What to show while a lookup runs, in the user's terms.
    public static func activity(forTool name: String) -> String {
        switch name {
        case "agent_overview": "Reading your portfolio and watchlist"
        case "agent_trading_behavior": "Reading your trading record"
        case "agent_filing": "Reading the latest filing"
        case "agent_draft_order": "Drafting an order for you to review"
        case "stock_lookup": "Looking up the company"
        default: "Looking that up"
        }
    }
}

/// Sends a message to the agent and streams what comes back.
public struct AgentChatService: Sendable {
    public typealias Opener = @Sendable (URLRequest) async throws -> (AsyncThrowingStream<String, Error>, Int)

    let serverURL: URL
    let token: @Sendable () -> String?
    let open: Opener

    public init(serverURL: URL, token: @escaping @Sendable () -> String?, open: @escaping Opener = AgentChatService.urlSession) {
        self.serverURL = serverURL
        self.token = token
        self.open = open
    }

    func request(conversationID: String, content: String) -> URLRequest {
        var request = URLRequest(url: serverURL.appendingPathComponent("api/agent/chat/\(conversationID)/messages"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        if let token = token() { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["content": content])
        // An answer that calls several tools can take a while to finish.
        request.timeoutInterval = 120
        return request
    }

    public func send(conversationID: String, content: String) -> AsyncStream<AgentChatEvent> {
        let request = request(conversationID: conversationID, content: content)
        return AsyncStream { continuation in
            let task = Task {
                do {
                    let (lines, status) = try await open(request)
                    guard status == 200 else {
                        continuation.yield(.failed(Self.message(forStatus: status)))
                        continuation.finish()
                        return
                    }
                    var finished = false
                    for try await line in lines {
                        guard let event = AgentChatEvent.parse(line: line) else { continue }
                        continuation.yield(event)
                        if event == .done { finished = true }
                        if case .failed = event { finished = true }
                    }
                    // A stream that just stops is not an answer.
                    if !finished { continuation.yield(.failed("The agent stopped before it finished. Try again.")) }
                } catch {
                    continuation.yield(.failed("Couldn't reach your agent. Check your connection and try again."))
                }
                continuation.finish()
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    static func message(forStatus status: Int) -> String {
        switch status {
        case 401: "Your session has ended. Sign in again to talk to your agent."
        case 402: "You've used today's conversations on your plan. They reset tomorrow."
        case 404: "Livermore's server doesn't have the agent yet. It needs a server update."
        default: "Your agent couldn't answer (error \(status)). Try again in a moment."
        }
    }

    public static let urlSession: Opener = { request in
        let (bytes, response) = try await URLSession.shared.bytes(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let lines = AsyncThrowingStream<String, Error> { continuation in
            let task = Task {
                do {
                    for try await line in bytes.lines { continuation.yield(line) }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
        return (lines, status)
    }
}

/// One conversation with the agent, as the screen shows it.
@MainActor
@Observable
public final class AgentConversation {
    public struct Message: Identifiable, Equatable, Sendable {
        public enum Role: Sendable { case user, agent }

        public let id: UUID
        public let role: Role
        public var text: String
        /// Orders the agent drafted in this answer, for the user to review.
        public var drafts: [OrderSuggestion] = []
        /// Set when the answer could not be completed.
        public var failure: String?
    }

    public private(set) var messages: [Message] = []
    public private(set) var isAnswering = false
    /// What the agent is doing right now, while it looks something up.
    public private(set) var activity: String?

    public let id = UUID().uuidString
    private let service: AgentChatService

    public init(service: AgentChatService) {
        self.service = service
    }

    public func send(_ text: String) async {
        let content = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty, !isAnswering else { return }
        isAnswering = true
        messages.append(Message(id: UUID(), role: .user, text: content))
        messages.append(Message(id: UUID(), role: .agent, text: ""))
        let index = messages.count - 1
        for await event in service.send(conversationID: id, content: content) {
            switch event {
            case .token(let text):
                activity = nil
                messages[index].text += text
            case .toolStarted(let name):
                activity = AgentChatEvent.activity(forTool: name)
            case .toolFinished(_, let action):
                if case .reviewOrder(let draft)? = action { messages[index].drafts.append(draft) }
            case .failed(let reason):
                messages[index].failure = reason
            case .done:
                break
            }
        }
        activity = nil
        isAnswering = false
    }
}
