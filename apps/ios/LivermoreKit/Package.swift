// swift-tools-version: 6.0
import PackageDescription

// All of the app's code lives in this package; the Xcode app target is a thin
// shell around `LivermoreUI`. That keeps every line compilable and testable
// with `swift build` / `swift test`, with or without Xcode.
let package = Package(
    name: "LivermoreKit",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "LivermoreKit", targets: ["LivermoreKit"]),
        .library(name: "LivermoreUI", targets: ["LivermoreUI"]),
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-openapi-generator", from: "1.6.0"),
        .package(url: "https://github.com/apple/swift-openapi-runtime", from: "1.7.0"),
        .package(url: "https://github.com/apple/swift-openapi-urlsession", from: "1.0.2"),
        .package(url: "https://github.com/apple/swift-http-types", from: "1.0.0"),
    ],
    targets: [
        // Generated from the backend's own OpenAPI schema (openapi.json), so a
        // renamed or retyped field is a compile error here, not a runtime one.
        .target(
            name: "LivermoreAPI",
            dependencies: [
                .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
            ],
            plugins: [.plugin(name: "OpenAPIGenerator", package: "swift-openapi-generator")]
        ),
        .target(
            name: "LivermoreKit",
            dependencies: [
                "LivermoreAPI",
                .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
                .product(name: "OpenAPIURLSession", package: "swift-openapi-urlsession"),
                .product(name: "HTTPTypes", package: "swift-http-types"),
            ],
            // The website's strategy templates, exported by scripts/gen_templates.mjs.
            // The second is sample data for the debug build's demo account.
            resources: [.process("Builder/templates.json"), .process("Demo/filings-nvda.json")]
        ),
        .target(name: "LivermoreUI", dependencies: ["LivermoreKit", "LivermoreAPI"]),
        .testTarget(
            name: "LivermoreKitTests",
            dependencies: [
                "LivermoreKit",
                "LivermoreAPI",
                .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
                .product(name: "HTTPTypes", package: "swift-http-types"),
            ]
        ),
    ]
)
