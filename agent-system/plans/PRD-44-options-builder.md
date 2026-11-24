# PRD-44 — Options builder (iOS), step 1

**Status:** BUILT 2026-11-20, in one PR. Not merged; not yet seen against a
real account (section 9).
**Date:** 2026-11-20
**Scope:** step 1 of four. Step 2 = placing through the connected broker,
step 3 = the agent proposes plans from holdings, step 4 = backtesting.

---

## 1. What this is, and what it is not

A person on a company page picks what they want from the stock, and the app
shows a real call or put that does it: what it costs, the most they can
lose, the most they can make, where they break even, and a payoff chart.
They save it and get a ticket they can enter in their own broker.

It is not order placement, not a backtest, not a recommendation, and not a
pricing model. It changes no existing screen; it adds one row to the company
page and one section to the Strategies tab.

## 2. The standard

Jimmy, 2026-11-20: build for the simplest interpretation, so that a
first-time user can learn it and finish without a bottleneck.

What that means in this build:

- **No typing, no option chain table.** Every choice is a tap or a slider
  over real contracts.
- **A result on the second screen.** The app picks a default expiry and
  strike; the user adjusts them on the result screen and the numbers and
  chart change as they move.
- **Every number has one plain sentence.** "You pay $1,423 now." "If NVDA is
  at or below $125 on Jan 15." "NVDA needs to rise 10.9% from $125.53."
- **Terms are explained where they appear, not before.** Tapping "Strike",
  "Expiry", "Contracts", "Breakeven", "Bid and ask", "Open contracts" or
  "What is a call?" shows one sentence (`OptionTerm`). No intro screen.
- **Facts, not assumptions.** Everything on the result screen is arithmetic
  on quoted prices. No probability of profit, no price before expiry; both
  need a pricing model.
- **Nothing the user cannot finish.** A strategy that needs 100 shares says
  so on its card and still shows the numbers. The ticket ends in numbered
  steps for entering the order at a broker.

## 3. The flow

Company page → "Options" → goal → plan → ticket: four taps, no typing.

**Screen 1 — "What do you want from NVDA?"** Four cards:

| Card | Strategy | Needs |
|---|---|---|
| I think it will go up | Buy a call | Cash for the fee |
| I think it will go down | Buy a put | Cash for the fee |
| Earn income on shares I own | Sell a covered call | 100 shares |
| Protect shares I own | Buy a protective put | 100 shares |

The chain is fetched while this screen is read, so the next one appears at
once, and a stock with no options says so before a card is chosen.

**Screen 2 — the plan.** Top to bottom:

1. The date the prices are from.
2. One sentence that states the whole trade.
3. Four numbers, each with its sentence: cost (or cash received), most you
   can lose, most you can make, breakeven with the move needed.
4. Controls: expiry chips (the monthly expiries about 1, 3 and 6 months out,
   plus "All dates"), a strike slider over real strikes with − and +, a
   contracts stepper. They sit between the numbers and the chart so both can
   be watched while something is changed.
5. Payoff chart: profit or loss at expiry against the share price, with the
   close, the breakeven, and a shaded band for the range option prices imply
   (section 6). Under it, a "what if" slider: "If NVDA is at $160.00 on
   Jan 15, you make $2,077."
6. The contract's quote: bid and ask, the price used, open contracts, volume.
7. A plain note when a contract is thinly traded, and what a covered call's
   buyer can do before expiry.
8. Two buttons, always on screen: "Take it to my broker" and Save.

**Screen 3 — the ticket.** The order in broker wording ("Buy to open
1 NVDA Jan 15, 2027 $125 call", "Limit $14.23 per share"), the exchange's
contract symbol, a copy button, what must already be in the account, five
numbered steps for entering it, and a line saying nothing has been sent.

**Defaults** (changeable on screen 2; they are starting points, not advice):

- Expiry: the first monthly expiry at least 30 days out.
- Strike, buying a call or put: the strike nearest the stock's price.
- Strike, covered call: the first strike at least 5% above it.
- Strike, protective put: the first strike at least 5% below it.
- Price per contract: the midpoint of bid and ask.

**Why the chart has a slider and is not dragged.** On iOS 26 a sideways drag
anywhere on a pushed screen is the system's "go back". Dragging on the chart
closed the plan. A slider is not taken that way.

## 4. The numbers

One engine covers every strategy (`OptionPayoff`). A plan is a list of legs
(stock, call or put; bought or sold; strike; quantity; entry price). Profit
at expiry for a share price S is the sum over legs, so it is a straight-line
graph with corners at the strikes. Max gain, max loss and breakevens come
from the corners and the slope past the last one, so spreads and collars
need no engine change later; the tests already cover a spread, a straddle
and an uncovered call.

Per contract of 100 shares, with P = premium, K = strike, S0 = the close:

| Strategy | Cash now | Most you can lose | Most you can make | Breakeven |
|---|---|---|---|---|
| Buy a call | pay 100·P | 100·P | no limit | K + P |
| Buy a put | pay 100·P | 100·P | 100·(K − P) | K − P |
| Covered call | receive 100·P | 100·(S0 − P) | 100·(K − S0 + P) | S0 − P |
| Protective put | pay 100·P | 100·(S0 − K + P) | no limit | S0 + P |

A bought put's maximum, 100·(K − P), is reached only with the stock at $0,
so the app does not headline it (changed 2026-11-20 after Jimmy's first
look). That tile reads "What you can make: $100 per $1 fall" and keeps the
maximum as small print under it.

Covered call and protective put measure the shares from the close.
Measuring from the user's own cost basis is step 3, when holdings are in.

**Thinly traded** is stated when open interest is under 100 contracts or the
bid-ask gap is over 10% of the midpoint. The note gives the numbers.

## 5. Data

Alpha Vantage `HISTORICAL_OPTIONS`: the full chain at the last close.

**Checked 2026-11-20 with the project's own key:**

- It returns real chains (NVDA 4,494 contracts, 3 MB, in about half a
  second). The live endpoint, `REALTIME_OPTIONS`, is not on the plan: it
  answers with a "premium" notice **and made-up sample rows** (symbol
  XXYYZZ). The client treats anything but a plain success as an error.
- **Class shares have no separator.** BRK-B and BRK.B are "Invalid/empty
  symbol"; BRKB works (`option_root`).
- **A full chain can arrive with one side missing.** That evening AAPL and
  SPY came back with every call and no puts, while NVDA, MSFT, AMD, KO and
  JPM were whole. Asking for the one expiry (`expiration=`) returned both
  sides. The service refetches a one-sided expiry on its own; if that fails
  too, what there is gets sent and the app says there are no puts to choose
  from for that date.

**Every price is from the same close.** The stock's price on the plan is its
close on the day the option prices are from (the provider's daily series),
not the live quote: mixing a live share price with last night's option
prices puts the wrong contract "at the money" on any day the stock has
moved. The live quote is only the fallback. The date is shown at the top of
the plan and the ticket.

Live prices need Alpha Vantage's 600 or 1,200 requests-per-minute plan and a
small change to the client. **Licence question for Jimmy to raise with them:**
their notice describes live option data as for "personal non-professional
use" and sends commercial users to their sales contact.

## 6. What option prices imply (the band on the chart)

For the chosen expiry, take the call and the put at the strike nearest the
stock's price. Their combined midpoint price divided by the stock's price is
the move the market is charging for. The band is the close plus and minus
that amount. It is labelled as what option prices imply, with a one-sentence
explanation that says it is not a forecast. No band is drawn when the
nearest strike with both a call and a put is more than 5% from the price.

## 7. Backend

New, nothing existing changes:

- `app/services/alpha_vantage.py` — `fetch_option_chain(symbol, expiration=None)`,
  `option_root`.
- `app/services/options/chain_service.py` — parses and cleans the chain
  (drops non-standard contracts, contracts with no ask, crossed quotes),
  keeps one chain per symbol for half an hour with the single-flight cache
  from `app/core/concurrency.py`, remembers a stock with no options for six
  hours and a failing provider for a minute, and cuts a chain to one expiry
  within 35% of the stock's price.
- `app/api/routes/options.py`, signed-in users only:
  - `GET /api/options/{symbol}/chain?expiration=` — one expiry (the default
    one without the parameter) plus the list of every expiry with days left,
    a monthly flag and the implied move. 7–31 KB, against the 3 MB chain.
    404 when the stock has no options, 503 when prices cannot be fetched.
  - `POST / GET /api/options/plans`, `DELETE /api/options/plans/{id}`.
- `app/models/option_plan.py` — `option_plans`: user, symbol, strategy, legs
  (JSON), the stock price and date the plan was built on. A new table, so
  `create_all` makes it; no column migration.

No new environment variable.

## 8. iOS

- `LivermoreKit/Options/` — `OptionPayoff.swift` (the engine),
  `OptionStrategy.swift` (the four strategies, defaults, the terms),
  `OptionPlan.swift` (the sentences, the ticket), `OptionsService.swift`
  (the API, the draft being built).
- `LivermoreUI/Options/` — `OptionGoalView`, `OptionPlanView`,
  `OptionPieces` (headline, numbers, payoff chart), `OptionTicketView`,
  `SavedOptionPlanView`.
- `CompanyView.swift` — one new row, "Options", under "More on …".
- `StrategiesView.swift` — one new section, "Option plans". If the plans
  cannot be read the rest of the tab still loads.
- `DemoTransport.swift` and `Demo/option-chains-nvda.json` — NVIDIA's real
  chain from 2026-11-20, so the whole flow runs in `-demo`.

The engine lives in Swift so the chart follows the sliders with no network
round trip. The Python twin arrives with step 3 (the agent), and both should
run the same file of worked examples so they cannot drift.

## 9. What was checked, and what was not

Checked:

- Backend: 31 tests on a recorded chain; the full suite passes apart from
  one file that stalls on unchanged `main` in a fresh worktree too
  (`test_market_pulse_warmup_no_live_overlay.py`).
- Against the real provider, in process: AAPL, NVDA, BRK-B and SPY, twelve
  requests at once each. One provider fetch per symbol, identical answers,
  0.8–1.4 s the first time and 2–3 ms after.
- iOS: 32 new tests (235 in the package). The app's own decoder was run
  over those four real responses and built all four plans on each.
- In the simulator with sample data, light and dark: goal → plan → change
  expiry and strike → "what if" slider → term popover → ticket → copy →
  save → the Strategies section → open → delete.

Not checked:

- The app against the deployed backend with a real account. The endpoints do
  not exist in production until this is merged.
- A real broker's option order screen against the ticket's wording.
- Postgres: the new table has only been created on SQLite locally; CI's
  migration smoke test covers Postgres.

## 10. Traps that applied

- Trap 13: the route gives its database connection back before awaiting.
- Trap 22: caches and single-flight come from `concurrency.py`.
- Trap 14: the provider call was run with the real key before the app work.
- A provider error's text can contain the request URL, which holds the API
  key. The service logs the kind of failure, never the text; a test pins it.
- Date stamps visible: the as-of date is the first line of the plan.

## 11. Using the option data to inform users

Each is a statement of what the data says, never a signal label. Alpha
Vantage's docs call a put/call ratio under 0.6 bullish and over 1.0 bearish;
that is a rule of thumb, and the evidence for it has not been checked, so
the app would show the number against the stock's own history instead.

| # | What the user sees | Data | State |
|---|---|---|---|
| A | "Option prices imply $98.92 to $152.14 by Jan 15" | Chain already fetched | Built |
| B | Before earnings: implied move against the size of past earnings-day moves | Chain plus an earnings calendar, which the backend does not have | Not started |
| C | For a holding: "Protecting your 200 shares below $135 until Jan 15 costs $840" and "Selling the $165 call pays $620" | Chain plus brokerage holdings | With step 3 |
| D | "Options activity" card: put/call ratio today against its past year; contracts that traded many times their open interest; strikes holding the most open contracts | `HISTORICAL_PUT_CALL_RATIO`, `HISTORICAL_VOLUME_OPEN_INTEREST_RATIO` | Not started |
| E | "Options are priced higher than 85% of days in the past year" | A year of daily readings, stored going forward | Not started |
| F | Screener filters on the above across the whole universe | About 2,500 calls a day | Later |

Recommended order: C (personal, and it fits the agent), then D, then E.

## 12. Slices

Planned as three PRs; built as one, because each depended on the one before
and this session does not merge, so they could not land in turn, and stacked
PRs lose backend CI.

## 12a. What step 2 (send it through the linked broker) has to deal with

Found on 2026-11-23 while tracing a failed share order on a real Schwab
link. All of it is from SnapTrade's own docs and the installed SDK
(13.0.3); none of it has run against a live trading connection.

- **Links are read-only unless trading is asked for.** `connectionType`
  defaults to `read`, and Livermore never set it, so no link made through the
  app could place any order. The share ticket now offers to re-authorise the
  account's link for trading (`reconnect` + `connectionType=trade`), which is
  SnapTrade's documented upgrade. Option orders need the same thing.
- **Which brokers can trade at all is narrower than which can connect.** On
  a commercial key (SnapTrade's broker access guide): E*TRADE, Moomoo,
  Public, tastytrade, Webull, Wealthsimple and Trading 212 are read and
  trade. **Schwab, Fidelity, Robinhood, Interactive Brokers and Vanguard are
  read-only.** Schwab trades only after Livermore itself is approved for
  Schwab's commercial Trader API ("case-by-case") and its keys are handed to
  SnapTrade. For those brokers the copy-out ticket is not a stopgap; it is
  the way an order gets placed.
- **The calls.** Preview is `trading.get_option_impact` (up to four legs).
  Placing is `trading.place_mleg_order`, with one leg for a single option:
  `instrument.symbol` is the OCC symbol **padded to 21 characters**
  (`NVDA  270115C00125000`; ours is stored unpadded), the action is
  `BUY_TO_OPEN` / `SELL_TO_OPEN`, `units` is contracts.
- **The preview is not bound to the order.** Shares go preview → trade id →
  `place_order(trade_id)`, so what is sent is what was priced.
  `place_mleg_order` takes the order itself, not an id. To keep the rule in
  `test_snaptrade_readonly_guard.py` (no order the user did not see priced)
  the backend has to hold the previewed option order and place exactly that.
- **Preview support and trading support are separate per broker**, so some
  option orders will have to be confirmed on our own arithmetic, labelled as
  an estimate.
- **The ticket's limit is the last close.** On 2026-11-23 NVDA was at $166
  against a $125.53 close; a $125 call carried a $14.23 limit that could
  never fill. The ticket says to check the live price; step 2 has to fetch
  one (`trading.get_user_account_option_quotes`) before it prices anything.

### 12b. Brokers that take no orders: the hand-off, confirmed (built 2026-11-23)

Jimmy decided not to apply for Schwab's trading API for now, so for Schwab,
Robinhood, Fidelity, Interactive Brokers and Vanguard the ticket is how an
order gets placed. Two additions close the loop without any trading
permission:

- **Copy and open the broker** (`BrokerApp`): Schwab's trade ticket or
  Robinhood's stock page, opened only if the broker's app takes it. Neither
  address accepts an order or, for Schwab, a symbol.
- **Check my broker for this order** (`PlacedOrderReading`, backend
  `find_option_orders`, `GET /api/snaptrade/orders/option`): matches on the
  contract symbol with the padding removed, reads the live 24-hour list and
  the week-long daily copy, and says which it could read.

Nothing is stored: a plan is not marked "placed", the ticket asks the broker
each time. Persisting it (and showing it on a saved plan) is the next step if
the read proves reliable on real accounts.

## 13. Decisions

Answered by Jimmy, 2026-11-20: a premium Alpha Vantage plan (so last-close
prices); four cards; open to every registered user; saved plans in a new
section of the Strategies tab.

Still open:

1. The "Options" row sits low on a long company page, under "More on …".
   Giving it a place higher up, or in the bottom bar, would change existing
   layout, so it was not done.
2. The licence question in section 5.
3. The order in section 11.
