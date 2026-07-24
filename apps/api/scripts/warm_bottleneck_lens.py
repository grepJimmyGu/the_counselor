"""Warm the bottleneck lens for the curated candidate set (Phase 3 scale).

For each symbol: POST /{sym}/refresh (extraction: 10-K/8-K/10-Q/S-1/20-F) then
POST /{sym}/thesis/refresh (the graded thesis). Both run SERVER-SIDE on Railway and
persist to Postgres; this script only triggers them and waits — so it can run from
anywhere. Idempotent: re-run to refresh (already-warm rows are overwritten). The
endpoints are rate-limited 1/hr/symbol, so re-running the same symbol within an
hour returns 429 (skipped, harmless).

Requires the engines enabled on the target:
  SUPPLY_CHAIN_EXTRACTION_ENABLED=true  and  SUPPLY_CHAIN_THESIS_ENABLED=true
else the endpoints return 503.

Usage (from apps/api):
  python3 scripts/warm_bottleneck_lens.py [--base URL] [--symbols A,B,C]
      [--concurrency N] [--thesis-only] [--extract-only]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

import httpx

sys.path.insert(0, os.getcwd())  # allow `python3 scripts/...` from apps/api

try:
    from app.data.bottleneck_candidates import BOTTLENECK_CANDIDATES
except Exception:  # noqa: BLE001
    BOTTLENECK_CANDIDATES = []

DEFAULT_BASE = "https://thecounselor-production.up.railway.app"


async def _post(client: httpx.AsyncClient, url: str) -> tuple[int, dict]:
    try:
        r = await client.post(url)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return r.status_code, (body if isinstance(body, dict) else {})
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__}


async def _warm(client: httpx.AsyncClient, base: str, sym: str, *, extract: bool, thesis: bool) -> dict:
    out: dict = {"symbol": sym}
    if extract:
        code, body = await _post(client, f"{base}/api/supply-chain/{sym}/refresh")
        out["extract"] = f"{code} edges={body.get('edges')}" if code == 200 else f"{code} {body.get('detail', '')}".strip()
    if thesis:
        code, body = await _post(client, f"{base}/api/supply-chain/{sym}/thesis/refresh")
        out["thesis"] = (
            f"{code} fit={body.get('fit_score')}/24 {body.get('verdict', '')}"
            if code == 200 else f"{code} {body.get('detail', '')}".strip()
        )
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--symbols", default="", help="comma-separated override; default = the curated set")
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--thesis-only", action="store_true")
    ap.add_argument("--extract-only", action="store_true")
    args = ap.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or list(BOTTLENECK_CANDIDATES)
    if not symbols:
        print("no symbols to warm", flush=True)
        return
    do_extract = not args.thesis_only
    do_thesis = not args.extract_only

    print(
        f"warming {len(symbols)} symbols on {args.base} "
        f"(extract={do_extract} thesis={do_thesis} concurrency={args.concurrency})",
        flush=True,
    )
    sem = asyncio.Semaphore(max(1, args.concurrency))
    done = 0
    started = time.time()

    async with httpx.AsyncClient(timeout=300.0) as client:
        async def run(sym: str) -> None:
            nonlocal done
            async with sem:
                t0 = time.time()
                res = await _warm(client, args.base, sym, extract=do_extract, thesis=do_thesis)
                done += 1
                print(
                    f"[{done}/{len(symbols)}] {sym:6}  extract={res.get('extract', '-')}  "
                    f"thesis={res.get('thesis', '-')}  ({time.time() - t0:.0f}s)",
                    flush=True,
                )

        await asyncio.gather(*(run(s) for s in symbols))

    print(f"warm complete — {done}/{len(symbols)} in {time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
