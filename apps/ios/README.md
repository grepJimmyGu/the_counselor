# Livermore for iOS

A native SwiftUI client for the Livermore API. It talks to the FastAPI backend
directly; the website is not in the path.

## Status

What the app does, and how far each part has been checked.

| Area | What a user can do | Checked |
|---|---|---|
| Research | Search; company page with live price, the three scores, 90-day chart, financials, business, market position; news & sentiment; supply chain | Against production |
| Live prices | Prices on every screen refresh every 10 s while visible, with "Prices checked 9:18:17 PM" beside them | Against production |
| Build a strategy | Pick one of the website's templates; choose tickers and period; change capital, costs, the rule's numbers, risk level and the stop/targets; run the backtest; change settings and run again | Against production, signed out (one run) |
| Save and re-test | Save a result; open a saved strategy and test it again with changes, saving the result as a new strategy | Sample data only |
| Strategies | Saved strategies, today's signal, open positions revalued on the live quote with stop and next target | Sample data only |
| Act on a strategy | Buy at your broker from a strategy or company page; tell Livermore about a position you hold so its exits are watched | Sample data only |
| Actions | Exits a strategy signalled, each resolved by selling at the broker, recording a sale made elsewhere, or keeping the position; notices | Sample data only |
| Brokerage | Link Robinhood, Schwab or another SnapTrade broker; accounts and holdings; order ticket (fill in → broker's numbers → confirm → receipt) | Sample data only |
| Account | Sign in, create an account, sign out | Wrong-password path against production; nothing that creates or uses a real account |

**"Sample data only" means the screens and the full flow run, but against
fixtures.** Launching a debug build with `-demo` signs in a made-up user and
answers every account endpoint from `DemoData`; the screens are marked "Sample
data". The fixtures are run through the real decoder in the tests, so they
cannot drift from the schema. The sample account reaches the network for six
public read-only calls (quotes, search, company data) and nothing else — it
cannot send an order.

```bash
xcrun simctl launch booted com.livermorealpha.app -demo
```

**Still to be seen against a real account:** a successful sign-in and
sign-up, saving a strategy, the signed-in backtest, the Strategies and
Actions tabs with real data, linking a real brokerage, and a real order. The
first five need someone to sign in on the device; the last two also need the
backend's SnapTrade keys and, for orders, `SNAPTRADE_TRADING_ENABLED=true`.

Research and one backtest work without an account, as on the website.

## How orders work

Livermore is a guide; the user's broker executes. Three rules are built into
the code, not left to the screens:

1. **Nothing is sent without a preview.** `BrokerageService.place` takes a
   preview and sends only its id. There is no call that places an order from a
   symbol and a quantity. The ticket's steps are a tested state machine
   (`OrderTicketState`): sent is reachable only through fill in → price → send.
2. **What is sent is what was shown.** Changing the amount or the account on
   a ticket discards the broker's price; the Send button is not there again
   until the new order has been priced.
3. **Livermore never assumes.** A sell ticket is prefilled only with a
   rule's own share count. Where an earlier exit tier's outcome is unknown,
   no share count is stated at all (`UnresolvedExit.quantity`).

Order placement has its own switch on the backend (`snaptrade_trading_enabled`,
off by default), separate from the read-only link. With it off the app shows
holdings, says orders aren't switched on, and offers "place it in your
brokerage app, then record it here" — never a button that would fail.

## How live prices work

`QuoteStore` polls `GET /api/live/quotes` for the union of symbols the visible
screens are showing, every 10 seconds, and stops in the background. Views opt
in with `.liveQuotes([...])` and read `session.quotes.quotes`.

How fresh a price can be is set by the backend's per-symbol cache — 30 seconds
today — not by the poll. PR #374 (`feat(api): fresher live quotes`) makes that
configurable (`LIVE_QUOTE_TTL_SECONDS`) and adds an optional Alpha Vantage
real-time source. Once it is deployed, refresh `openapi.json`: the response
gains `ttl_seconds` (the right poll interval) and, per quote, `as_of` (when
the price itself is from), which the app should use in place of its fixed 10 s
and its "checked at" label.

There is no streaming. Tick-by-tick prices need a WebSocket feed and a data
licence that covers redistribution; neither exists yet.

## Risk level and exits — what the backtester honours

The customise screen is a port of the website's risk presets
(`lib/strategy-picker/risk-presets.ts`), held to it by a fixture generated
from the web code:

```bash
node apps/ios/scripts/gen_risk_golden.mjs
```

Of the fields a preset writes, the backtester acts on the volatility target
only. `stop_loss_pct`, `take_profit_pct` and `max_drawdown_stop` are stored on
the strategy but nothing in `apps/api/app/services/backtester/` reads them. So
the app describes a risk level by what it changes, and offers a stop and
targets through the exit ladder (`ExitPlan`), which the engine does apply and
which is also what makes a saved strategy trackable.

## Layout

```
apps/ios/
  Livermore.xcodeproj             the app target; open this in Xcode
  App/LivermoreApp.swift          the app target's only file
  LivermoreKit/                   Swift package — all of the app's code
    Sources/LivermoreAPI/         client generated from openapi.json
    Sources/LivermoreKit/         everything that isn't a screen:
      AppSession, APIFailure        session, Keychain storage, shared errors
      Research/                     research calls, QuoteStore (live prices)
      Scoring/                      the company scores (ported from the web)
      Builder/                      templates, customisation, backtests
      Strategies/                   saved strategies, positions, signals
      Actions/                      exits waiting on the user, notices
      Brokerage/                    SnapTrade link, holdings, order tickets
      Demo/                         the sample account (debug builds only)
    Sources/LivermoreUI/          SwiftUI screens, same folders
    Tests/LivermoreKitTests/      95 tests; `swift test` runs them in a second
  scripts/refresh_openapi.py      refreshes openapi.json from the backend
  scripts/gen_scoring_golden.mjs  regenerates the scoring parity fixture
  scripts/gen_templates.mjs       regenerates the strategy templates
  scripts/gen_risk_golden.mjs     regenerates the risk-preset parity fixture
```

## Build and test the package (no Xcode needed)

```bash
cd apps/ios/LivermoreKit
swift build
swift test
```

Six extra tests make read-only calls to production. They are off by default:

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

## The strategy templates are a copy — regenerate when the web's change

The template catalogue is data in `apps/web/src/lib/contracts.ts`
(`researchTemplates`); the backend does not serve it. The app ships an export:

```bash
node apps/ios/scripts/gen_templates.mjs           # rewrite templates.json
node apps/ios/scripts/gen_templates.mjs --check   # exit 1 if it is stale
```

`TemplateCatalogTests` checks that every exported template decodes into the
generated `StrategyJSON` type. A template run sends exactly what the web sends
(`buildStrategyFromTemplate`): the template's rules with the universe, dates
and name replaced.

Signed out, the backend allows one backtest per visitor; the app then asks
the user to sign in.

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

- **Strategies are built from the website's templates, then changed.** The
  website's signal composer (build a rule from individual signals) is not in
  the app. A strategy composed there appears in the app, is tracked, and can
  be acted on; it can be re-tested here only if it uses nothing this build
  lacks a type for.
- **One rule's numbers are editable.** Templates carry a single rule; a
  saved strategy with several shows the first.
- **Orders are market orders, good for the day.** The backend also accepts
  limit orders; the ticket does not offer them yet.
- **The brokerage sign-in returns to the website**, not to the app (the
  backend builds the return address from a site path, deliberately). The user
  taps Done on the in-app browser and the app re-reads the link.
- **The company page shows the scores and the backend's summaries, not the
  web's written interpretation** (the bull and bear cases and the analyst
  summary in `interpretation.ts`). Those are not ported.
- **A strategy page shows its signal and positions, not the web's intraday
  chart or trade log.**
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
