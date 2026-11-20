# Livermore for iOS

A native SwiftUI client for the Livermore API. It talks to the FastAPI backend
directly; the website is not in the path.

## Status

What the app does, and how far each part has been checked.

| Area | What a user can do | Checked |
|---|---|---|
| Research | Market strip and a watchlist with sparklines; search; company page in two tabs — **Financials** (the latest 10-Q or 10-K: what changed, flagged; every metric's nine-quarter trend) and **Price** (chart, signals, trend model, key levels, entry and exit test); news & sentiment; supply chain | Price tab against production. Financials against real SEC data through a local backend — the endpoint is PR #376, not yet deployed |
| Live prices | Prices on every screen refresh every 10 s while visible, with "Prices checked 9:18:17 PM" beside them | Against production |
| Build a strategy | Pick one of the website's templates; choose tickers and period; change capital, costs, the rule's numbers, risk level and the stop/targets; run the backtest; change settings and run again | Against production, signed out (one run) |
| Save and re-test | Save a result; open a saved strategy and test it again with changes, saving the result as a new strategy | Sample data only |
| Strategies | Saved strategies, today's signal, open positions revalued on the live quote with stop and next target | Sample data only |
| Act on a strategy | Buy at your broker from a strategy or company page; tell Livermore about a position you hold so its exits are watched | Sample data only |
| Actions | Exits a strategy signalled, each resolved by selling at the broker, recording a sale made elsewhere, or keeping the position; notices | Sample data only |
| Brokerage | Link Robinhood, Schwab or another SnapTrade broker; accounts and holdings; order ticket (fill in → broker's numbers → confirm → receipt) | Sample data only |
| Account | Sign in with a password, Face ID or Google; create an account under the password rules; reset a forgotten password by emailed code; change the password; sign out | Sign-up, the breach refusal, show/hide and Face ID on the simulator against a local backend. Google, the iPhone's suggested password and automatic saving are not yet seen working: see "Signing in" |

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

## Design

One visual system, in `Sources/LivermoreUI/Design/`:

- **`Theme.swift`** — the website's palette (`apps/web/src/app/globals.css`),
  converted from OKLCH, with its own light and dark values: `brand`, `gain`,
  `loss`, `caution`, and the `canvas` / `surface` / `well` layers. Gain and
  loss colours are used for gains and losses and nothing else.
- **`Components.swift`** — `Card`, `StatTile`, `ChangePill`, `Tag`, `Notice`,
  `DetailRow`, `ScoreRing`, `ScoreBar`, `Sparkline`, `LevelBar` (a position
  between its stop and target), the primary and secondary button styles, and
  `bottomBar`, which pins a screen's next step above the tab bar.

Conventions the screens follow:

- **A date or a category sits above every headline** (`eyebrowStyle`), never
  in a footer.
- **Numbers use tabular digits**, so a refreshing price does not jitter.
- **The next step is always on screen**: Run, Save, Trade and Send live in the
  bottom bar rather than at the end of a scroll.
- **Loading shows the page's shape** (`SkeletonBlock`), not a spinner.
- **Long explanations are collapsed to their first sentence** with the rest a
  tap away ("Why", "Before you rely on it").

### Where the price chart's numbers come from

The company chart is built on the device from `/api/data/daily/{symbol}` (the
stock) and the same call for SPY, fetched once per launch and cached
(`PriceHistory`). Ranges, the period return and "vs S&P 500" are all computed
from those closes (`PerformanceSeries`), so the three always describe the same
days and always end on the latest close.

`/api/market/sector-comparison/{symbol}` looks like the endpoint for this and
is not used: for ranges longer than a month its series stops on 2026-09-10,
which made NVDA read "+17.0% past year" when the true figure was −16.4%.

The watchlist and "recently viewed" are kept on the device (`Watchlist`,
UserDefaults). They are not the website's community watchlist.

## The company page: what changed, and where the price stands

Two tabs, both ending in the same card — *Decide yourself* (Buy / Sell
through the linked broker) or *Let a rule decide* (strategies matched to the
setup, each opening ready to backtest on this stock).

The page has three rules, set by Jimmy on 2026-11-17:

1. **No general introduction.** Nothing about what the company is or how it
   makes money. It opens on the latest filing.
2. **No fixed framework.** A topic (demand, cash, dilution, debt) appears only
   when a figure moved enough to raise it. A quiet quarter has a short list.
3. **Facts, not assumptions.** Every sentence is arithmetic on a filed figure
   or a measured price. Nothing says what will happen, and nothing says buy
   or sell. The backend test suite fails a finding containing "will",
   "should", "expect", "buy" or "sell".

### Financials — the latest 10-Q / 10-K

Built from `GET /api/company/{symbol}/filings` (backend PR #376), which reads
the company's own XBRL figures from SEC EDGAR.

| Card | Shows |
|---|---|
| Latest quarter | Form, filing date and period; revenue, operating margin, EPS and free cash flow, each against a year ago and last quarter; a link to the filing on sec.gov |
| What changed this quarter | Rule-based findings, most serious first, tagged *to watch*, *improved* or *to note* — e.g. receivables growing faster than sales, inventory building, profit ahead of cash, share count, debt. Each states the two figures it compared |
| Growth, Profitability, Cash, Balance sheet, Shareholders | 24 metrics; each row has the latest value, the change from a year ago, nine quarters of bars and "9-quarter high / low" where true. Tap for every quarter with its form and filing date |
| How the market prices it | Market value, P/E, EV/EBITDA, P/S, free-cash-flow yield, ROE; the cash-flow stress test |

Fourth quarters are not filed on their own: they are the fiscal year less the
first three quarters. A missing figure is shown as missing, never as zero.

**Until #376 is merged and deployed the tab shows a notice and the annual
figures instead.** The sample account (`-demo`) serves NVIDIA's real analysis
from a bundled copy captured 2026-11-17 (`Demo/filings-nvda.json`), so the
screen can be seen today.

Not covered, because the SEC's company-facts feed does not carry it: segment
and customer-concentration figures, the text of the filing (risk factors,
commitments, guarantees), and companies that file 20-F or 40-F.

### Price — signals, a model, and a test

All computed on the device from the daily history the chart uses.

| Card | Shows | Code |
|---|---|---|
| The setup, Signals | Six direction signals with a tally, and the 14-day RSI reading | `TechnicalRead` |
| Trend model | A log-linear fit over 3, 6 or 12 months: annual rate, R², how many standard deviations today's price sits from the line, and a ±2σ band. It measures the window; it does not project past it | `TrendModel` |
| Key levels | 50- and 200-day averages, 20-day and 52-week highs and lows, the last turning points, each with its distance from the live price; a typical day's range (14-day ATR) | `PriceLevels` |
| Test an entry and exit | Set an entry, a stop and a target. The plan is tried on every trading day of the past five years: how often the target was reached, the stop was hit, or neither within the horizon; the average result; and the same again for days on the same side of the 200-day average as today | `BracketTest` |

The defaults for the test come from the stock: the stop is two typical days'
range away and the target twice the stop. A day that touched both levels
counts as stopped, and each day starts its own trial, so trials overlap —
the card says so. From the result, "Backtest a strategy with this stop and
target" opens the trend-following template with that exit plan filled in.

The cash-flow stress test (`CashFlowModel`, `RevenueShock`, `ValuationView`)
is unchanged: five years of free cash flow at one growth rate, a terminal
value, a discount rate, net cash and a share count, with a sensitivity grid.
`CashFlowModelTests` reproduces a published model's results from its inputs.

The sample account passes public market data (quotes, daily history, the
overview) through to the live API, so the Price tab is live in `-demo` too.

## The portfolio agent

A fifth tab, Agent, between Strategies and Actions. Nothing that existed was
changed: the agent opens the screens that were already there.

| Part | What it does |
|---|---|
| Watching | The backend checks each user's watchlist and broker holdings. With "Watch around the clock" on, it does so twice an hour through the US session whether or not the app is open; "Check now" does it on request |
| What it reports | A day's move past the user's threshold; a holding larger than the user's limit, with the sale that would bring it back; a filing from the last 30 days with items to check; exits waiting on a decision |
| Acting | Each finding offers a screen that already exists: the company page, the Actions tab, or the order ticket with the symbol and size filled in. The ticket still shows the broker's price and still needs the user's confirmation. The agent cannot send an order |
| Asking | "Ask your agent" is a conversation. The agent reads the user's portfolio, their trading record (the website's behaviour analysis), and filings through tools, and can draft an order for review |
| Per user | The move threshold, the position limit, an email switch, and notes in the user's own words that the agent reads before answering |
| While the app is closed | New findings from scheduled checks are emailed, one message per check. There are no push notifications |

Three rules are built in, on the backend: every number comes from code, not
from the model; the agent drafts and the user decides; it reports what
happened under the user's own limits and does not say what they should do.

The watchlist lives on the device, so the app sends it to the backend when it
changes; that list is what the agent watches.

Needs on the backend: the agent endpoints (`/api/agent/*`), and for the
conversation a language model (`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`).
Without a model the checks and findings still work and the conversation says
it is not switched on. `-demo` shows the tab with sample findings and a
scripted sample conversation.

## Signing in

| What | How it works | What it still needs |
|---|---|---|
| Password rules | 12 to 64 characters with a lowercase letter, an uppercase letter, a number and a symbol; no character three times in a row; no run of four (1234, abcd); not your name, your email handle or "Livermore"; typed twice. `PasswordPolicy` ticks the rules off as you type and repeats what is missing just above the keyboard. The backend applies the same rules and also refuses a password found in breach data | Backend PR for the server side. Until it deploys, the app enforces the rules and production does not |
| Seeing what you type | A new password is shown as typed; the eye hides it. A sign-in password is hidden; the eye shows it. Either way the box is an ASCII keyboard with no suggestions, so a shown password is never fed to the keyboard's dictionary or an input method | Nothing |
| AutoFill | The email and password boxes are tagged for the iPhone's password manager, so the Passwords key appears above the keyboard. On the simulator iOS also offers to save the password after a sign-in and after a password change, with no associated domain | Whether a saved password is then suggested for this app by name, rather than picked from the full list, is not yet seen; Apple ties that to the associated domain below |
| iPhone-suggested password | The new-password box is tagged `newPassword` and carries `PasswordPolicy.generatorRules`, so what the iPhone proposes passes the rules | An associated domain: the Associated Domains entitlement (`webcredentials:livermorealpha.com`) and an `apple-app-site-association` file on that domain naming `<Team ID>.com.livermorealpha.app`. Both need an Apple Developer Program team. Apple's documentation says the suggestion is offered only "in apps that have an associated domain". Not built, because there is no Team ID yet |
| Face ID | After a typed sign-in the app asks once whether to keep the password. It is stored in the Keychain behind `biometryCurrentSet`, on this device only; "Sign in with Face ID" then reads it after the face check. Turned off from Account, which deletes it. A password the account no longer accepts is deleted on first use | Nothing. Google accounts have no password, so there is nothing to keep for them |
| Google | `GoogleSignIn` runs Google's installed-app flow (authorization code with PKCE) in the system browser sheet and hands the ID token to the backend. No Google SDK | An iOS OAuth client ID from Google Cloud in `APIEnvironment.googleClientID`, and the same value as `GOOGLE_IOS_CLIENT_ID` on the backend. Without the ID there is no Google button |

**Forgotten password.** "Forgot password?" on the sign-in screen asks for the
address, the backend emails a six-digit code, and the next screen takes the
code and a new password (same rules, same checklist). Finishing signs in and
signs the app out everywhere else. The screen never says whether the address
has an account, because the backend does not. It needs backend PR #377 and,
on the backend, `RESEND_API_KEY`: without it no email is sent. Seen working
on the simulator against #377 running locally, with the code read from the
test database in place of the email; no real email has been sent.

**Changing the password.** Account → Change password asks for the current
password and a new one (same rules, same checklist). The backend signs out
every other device and hands this one a new session, so it stays signed in;
a password kept for Face ID is replaced with the new one. An account that
signs in with Google has no current password and is told to use Forgot
password instead. Needs backend PR #377. Seen working on the simulator
against #377 running locally.

To try Google sign-in before the client ID is committed, or to point the app
at a backend on this Mac (debug builds only):

```bash
xcrun simctl launch booted com.livermorealpha.app -googleClientID <id>.apps.googleusercontent.com
xcrun simctl launch booted com.livermorealpha.app -serverURL http://127.0.0.1:8000
```

The password rules exist twice, in `PasswordPolicy.swift` and the backend's
`password_policy.py`. Their tests check the same list of passwords for the
same verdicts; change both together.

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
screens are showing, and stops in the background. It asks every 10 seconds
while a US session is open (weekdays, 4:00 to 20:00 New York, pre-market
through after-hours) and once a minute the rest of the time, when the price is
the last trade and cannot change (`MarketHours`). Views opt in with
`.liveQuotes([...])` and read `session.quotes.quotes`.

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
    Tests/LivermoreKitTests/      203 tests; `swift test` runs them in a second
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

**The company page no longer shows the scores** (2026-11-17: facts, not
assessments). `StockScoring` and its parity tests stay in the package for
the screens that may use them.

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
- **The Financials tab depends on backend PR #376.** Until it is deployed
  the app shows the annual figures with a notice. It covers companies that
  file 10-Q and 10-K with the SEC; it has no segment, customer-concentration
  or filing-text data.
- **The entry and exit test uses daily highs and lows.** It cannot see the
  order of moves inside a day, which is why a day touching both levels is
  counted as stopped.
- **A strategy page shows its signal and positions, not the web's intraday
  chart or trade log.**
- **Supply chain shows the summary and chokepoint tests only**, not the
  supplier and customer graph.
- **The price chart asks for six years of daily history**
  (`PriceHistory.yearsKept`): the longest range and the plan test read five.
  A backend older than 2026-11-20 ignores `start` and sends everything, which
  the app handles; it is just a bigger download. Fetched once per symbol per
  launch.
- **A company looked at in the last five minutes opens from memory**
  (`RecentValues` on `AppSession`): no skeleton and no request. The backend
  keeps a company page for ten minutes itself, so a second request in that
  time could only return what the first did. Signing in or out clears it.
- **The market strip shows index ETFs** (SPY, QQQ, DIA, IWM), not the indices
  themselves, and says so.

- **Google sign-in refuses an address whose account has a password and has
  never used Google** (the backend's rule; the website's Google sign-in links
  such an account instead).
- **No Sign in with Apple.** The App Store requires it alongside Google
  sign-in; it needs an Apple Developer account.
- **Sessions last 30 days.** The backend's token refresh endpoint is
  server-only, so an expired token signs the user out.
- **No push notifications.** They need an Apple Developer Program membership
  and a device-registration endpoint on the backend.
