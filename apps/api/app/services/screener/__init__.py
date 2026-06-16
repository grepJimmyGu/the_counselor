"""Market Screener backend (PRD-23a).

The machinery that turns a composed reading + a universe into a ranked
basket: resolve a universe -> pre-warm every primitive's latest value
across it (the snapshot) -> filter to the matched basket at scan time ->
backtest + rank the survivors.

Slice 1 (this commit): `universe_resolver`. Snapshot / scan / rank land in
the following slices of PRD-23a.
"""
