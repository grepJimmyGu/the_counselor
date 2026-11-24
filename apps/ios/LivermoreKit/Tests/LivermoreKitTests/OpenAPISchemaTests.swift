import Foundation
import Testing

/// The generator silently drops any property whose schema includes
/// `{"type": "null"}` — which is how FastAPI writes every `Optional` field.
/// `scripts/refresh_openapi.py` rewrites them; this fails if a schema is ever
/// checked in without going through it. Before the rewrite, `UserPublic` was
/// generated with 2 of its 5 fields.
@Suite("openapi.json")
struct OpenAPISchemaTests {
    private static let schemaURL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()  // LivermoreKitTests
        .deletingLastPathComponent()  // Tests
        .deletingLastPathComponent()  // LivermoreKit
        .appendingPathComponent("Sources/LivermoreAPI/openapi.json")

    private static func nullSchemas(in node: Any, path: String = "#") -> [String] {
        if let dict = node as? [String: Any] {
            if dict["type"] as? String == "null" { return [path] }
            if let kinds = dict["type"] as? [String], kinds.contains("null") { return [path] }
            return dict.flatMap { nullSchemas(in: $0.value, path: "\(path)/\($0.key)") }
        }
        if let list = node as? [Any] {
            return list.enumerated().flatMap { nullSchemas(in: $0.element, path: "\(path)/\($0.offset)") }
        }
        return []
    }

    @Test("has no null schemas left for the generator to drop")
    func noNullSchemas() throws {
        let doc = try JSONSerialization.jsonObject(with: Data(contentsOf: Self.schemaURL))
        #expect(Self.nullSchemas(in: doc).prefix(5) == [])
    }

    @Test("still describes every path the generator is configured to build")
    func configuredPathsExist() throws {
        let doc = try JSONSerialization.jsonObject(with: Data(contentsOf: Self.schemaURL)) as? [String: Any]
        let paths = try #require(doc?["paths"] as? [String: Any])
        let config = try String(
            contentsOf: Self.schemaURL.deletingLastPathComponent().appendingPathComponent("openapi-generator-config.yaml"),
            encoding: .utf8
        )
        let wanted = config.split(separator: "\n")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { $0.hasPrefix("- /") }
            .map { String($0.dropFirst(2)) }
        #expect(!wanted.isEmpty)
        #expect(wanted.filter { paths[$0] == nil } == [])
    }
}
