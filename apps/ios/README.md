# Livermore for iOS

A native SwiftUI client for the Livermore API. It talks to the FastAPI backend
directly; the website is not in the path.

## Status

| Slice | What | State |
|---|---|---|
| 1 | Project, generated API client, sign-in, tab shell | **Built and run** in the iOS 27.2 simulator |
| 2 | Research: search and the company page | **Built and run** — see below |
| 3 | Strategies: enabled strategies, open positions, signals | Not started |
| 4 | Brokerage link and the Actions inbox | Not started |

**Seen running** on an iPhone 17 simulator against the production API: search,
the company page (live price, the three scores, 90-day chart, financials,
business, market position), News & sentiment, Supply chain, and the
wrong-password message on sign-in.

**Not yet seen:** a successful sign-in and the Account screen behind it — that
needs a real account's password.

Research works without an account, as it does on the website; the backend
serves the anonymous tier. Sign-in lives in the Account tab.

## Layout

```
apps/ios/
  Livermore.xcodeproj             the app target; open this in Xcode
  App/LivermoreApp.swift          the app target's only file
  LivermoreKit/                   Swift package — all of the app's code
    Sources/LivermoreAPI/         client generated from openapi.json
    Sources/LivermoreKit/         session, Keychain storage, research calls, scoring
    Sources/LivermoreUI/          SwiftUI screens
    Tests/LivermoreKitTests/
  scripts/refresh_openapi.py      refreshes openapi.json from the backend
  scripts/gen_scoring_golden.mjs  regenerates the scoring parity fixture
```

## Build and test the package (no Xcode needed)

```bash
cd apps/ios/LivermoreKit
swift build
swift test
```

Two extra tests make read-only calls to production. They are off by default:

```bash
LIVERMORE_LIVE_TESTS=1 swift test --filter LiveAPITests
```

## The API client is generated — do not hand-write models

`Sources/LivermoreAPI/openapi.json` is the backend's own schema, and
`swift-openapi-generator` turns it into the client at build time. A field the
backend renames or retypes becomes a compile error here.

To pick up backend changes:

```bash
python3 apps/ios/scripts/refresh_openapi.py
```

Always use the script, never a plain download. FastAPI writes every optional
field in a form the generator silently drops; the script rewrites them (559
fields at the time of writing) and `OpenAPISchemaTests` fails if that step is
skipped.

To call a new endpoint, add its path to
`Sources/LivermoreAPI/openapi-generator-config.yaml`. Only listed paths are
generated.

## The company scores are a port — keep them in step with the web

The website computes Asset health, Valuation and Market trend in the browser
(`apps/web/src/lib/evaluation/scoring.ts`); there is no endpoint for them.
`StockScoring.swift` is a line-for-line port, held to the original by
`StockScoringParityTests`, which replays 401 cases produced by running the
TypeScript itself.

If `scoring.ts` changes:

```bash
node apps/ios/scripts/gen_scoring_golden.mjs   # regenerate the fixture
cd apps/ios/LivermoreKit && swift test          # fails until Swift matches
```

The lasting fix is to compute the scores on the backend so there is one copy.

## Build the app

```bash
cd apps/ios
xcodebuild -project Livermore.xcodeproj -scheme Livermore \
  -destination 'generic/platform=iOS Simulator' \
  -skipPackagePluginValidation build
```

`-skipPackagePluginValidation` lets the command line run the OpenAPI generator
plugin without a prompt; in Xcode, choose "Trust & Enable" the first time.

The project uses a file-system-synchronised `App/` group, so files added to
that folder join the target without editing the project file. Nearly all code
belongs in `LivermoreKit/` instead.

## Known limits

- **The company page shows the scores and the backend's summaries, not the
  web's written interpretation** (the bull and bear cases and the analyst
  summary in `interpretation.ts`). Those are not ported.
- **Supply chain shows the summary and chokepoint tests only**, not the
  supplier and customer graph.
- **The price chart is the 90-day series from the trend endpoint.**
  `/api/data/daily/{symbol}` ignores its `start` parameter and returns the
  whole history (6,802 bars for AAPL), which is too heavy for a phone.

- **Sign-in is email and password only.** Google sign-in needs an iOS client
  id; Sign in with Apple needs an Apple Developer account.
- **Sessions last 30 days.** The backend's token refresh endpoint is
  server-only, so an expired token signs the user out.
- **No push notifications.** They need an Apple Developer Program membership
  and a device-registration endpoint on the backend.
