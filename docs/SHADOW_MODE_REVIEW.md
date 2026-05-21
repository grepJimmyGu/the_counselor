# Shadow-mode review checklist

Before flipping `GATING_ENABLED=true` (or after any change to `TIER_CAPS` /
gate boundary math), walk this checklist. Skipping it on May 20-21 surfaced
the 5.0027-yr boundary bug in front of a real user — the shadow logs would
have shown it days earlier.

---

## 1. Aggregate gate fires from the last 24 hours

```bash
railway logs --service the_counselor | grep gate_event | \
  sed 's/.*code=\([a-z_]*\).*/\1/' | sort | uniq -c | sort -rn
```

Read the counts. **Any code firing in shadow mode is a code that would
402 in enforcement mode.** If the count is surprising — a code firing
for users you didn't expect to gate — that's the bug.

For each surprising code:

```bash
railway logs --service the_counselor | grep "gate_event code=<code_name>" | tail -20
```

Look at the `current` / `limit` values. If they look "obviously wrong"
(e.g., a "5.0 yr" current vs a "5 yr" limit), the gate math has a
boundary issue that needs fixing before enforcement.

## 2. Synthetic Scout smoke test

Sign up a fresh Scout account (or use one you can wipe). Walk the
top user paths and check that NO modal fires for normal-looking inputs:

- [ ] Run a stock template at default settings — succeeds
- [ ] Run a custom strategy with a 5-ticker S&P 500 universe over the
      default 5-year window — succeeds (this is the boundary case)
- [ ] Run a custom strategy with 6 tickers — modal fires
      (`universe_too_large`)
- [ ] Run a custom strategy over a 6-year window — modal fires
      (`history_too_long`)
- [ ] Visit `/stocks/AAPL` — succeeds (S&P 500)
- [ ] Visit `/stocks/SMCI` — modal fires (`market_pulse_ticker_out_of_scope`)
- [ ] Run robustness with `parameter_sensitivity` selected — modal fires
      (Scout has no robustness tests)

## 3. Postgres invariants (CI also enforces these)

```bash
PG_TEST_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres \
  pytest apps/api/tests/test_postgres_migrations.py -q
```

Should be 8 green tests. If any fail, the schema has drifted from the
gate's assumptions (column types, FK constraints, orphan rows).

Also run the operational orphan check directly against production:

```bash
DATABASE_URL=$(railway variables --service the_counselor --json | jq -r '.DATABASE_URL') \
  python apps/api/scripts/check_orphan_users.py
```

Should print `0 orphans`. If not, sync-user heal at
`apps/api/app/api/routes/auth.py:380-389` will catch them on next login,
but it's better to see the list before flipping enforcement.

## 4. Flip the flag

When everything above looks clean:

```bash
railway variables --service the_counselor --set GATING_ENABLED=true
```

After flipping, watch `paywall_hit` events in PostHog (if configured) or
keep watching `gate_event` lines in Railway logs for at least 1 hour.
The two metrics should now move in lockstep — if `paywall_hit` count
exceeds `gate_event` count, something is bypassing the structured log
path and that's a bug.
