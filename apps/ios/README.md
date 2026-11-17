# Livermore for iOS

A native SwiftUI client for the Livermore API. It talks to the FastAPI backend
directly; the website is not in the path.

## Status

| Slice | What | State |
|---|---|---|
| 1 | Project, generated API client, sign-in, tab shell | **Built.** Compiles and passes tests on macOS. Not yet run on iOS — see below. |
| 2 | Research: search and the company page | Not started |
| 3 | Strategies: enabled strategies, open positions, signals | Not started |
| 4 | Brokerage link and the Actions inbox | Not started |

**Not yet run on a phone or simulator.** The machine this was written on has
no Xcode, so there is no iOS SDK to build against. The code is plain SwiftUI
that compiles for macOS with the command-line toolchain; the first build under
Xcode may still surface iOS-only issues, and no screen has been looked at.

## Layout

```
apps/ios/
  App/LivermoreApp.swift          the app target's only file (9 lines)
  LivermoreKit/                   Swift package — all of the app's code
    Sources/LivermoreAPI/         client generated from openapi.json
    Sources/LivermoreKit/         session, Keychain storage, auth middleware
    Sources/LivermoreUI/          SwiftUI screens
    Tests/LivermoreKitTests/
  scripts/refresh_openapi.py      refreshes openapi.json from the backend
```

## Build and test (no Xcode needed)

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

## Creating the Xcode project (once Xcode is installed)

1. File → New → Project → iOS App, named `Livermore`, saved in `apps/ios/`.
2. Replace the generated `LivermoreApp.swift` and `ContentView.swift` with
   `App/LivermoreApp.swift`.
3. File → Add Package Dependencies → Add Local → `apps/ios/LivermoreKit`, and
   add the `LivermoreUI` product to the app target.
4. Set the deployment target to iOS 17.

## Known limits

- **Sign-in is email and password only.** Google sign-in needs an iOS client
  id; Sign in with Apple needs an Apple Developer account.
- **Sessions last 30 days.** The backend's token refresh endpoint is
  server-only, so an expired token signs the user out.
- **No push notifications.** They need an Apple Developer Program membership
  and a device-registration endpoint on the backend.
