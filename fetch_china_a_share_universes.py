"""
Fetch China A-share ticker universes for Livermore-style research workflows.

Outputs:
  - csi300_constituents.csv
  - csi500_constituents.csv
  - csi1000_constituents.csv
  - all_shanghai_shenzhen_a_shares.csv
  - combined_a_share_universe.csv
  - livermore_a_share_universe.xlsx

Install:
  pip install -U akshare pandas openpyxl

Run:
  python fetch_china_a_share_universes.py

Notes:
  - CSI constituents are fetched from China Securities Index via AKShare.
  - Full Shanghai/Shenzhen A-share universe is fetched from Eastmoney spot lists via AKShare.
  - Excludes Beijing Stock Exchange by design.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Dict

import pandas as pd

import time

try:
    import akshare as ak
except ImportError as exc:
    raise SystemExit("Please install dependencies first: pip install -U akshare pandas openpyxl") from exc


def _fetch_with_retry(fn, name: str, max_retries: int = 3):
    """Call fn() with retries on connection errors. Eastmoney rate-limits
    aggressively; retry with back-off instead of crashing."""
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            if attempt < max_retries - 1:
                wait = 2.0 * (attempt + 1)
                print(f"  {name}: {type(exc).__name__} — retrying in {wait:.0f}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
            else:
                raise

OUTPUT_DIR = Path("china_a_share_universes")
OUTPUT_DIR.mkdir(exist_ok=True)
AS_OF_DATE = dt.date.today().isoformat()

INDEXES: Dict[str, str] = {
    "CSI 300": "000300",
    "CSI 500": "000905",
    "CSI 1000": "000852",
}


def normalize_exchange_from_code(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith(("6", "9")):
        return "Shanghai Stock Exchange"
    if code.startswith(("0", "2", "3")):
        return "Shenzhen Stock Exchange"
    if code.startswith(("4", "8")):
        return "Beijing Stock Exchange"
    return "Unknown"


def yahoo_suffix(exchange: str) -> str:
    if "Shanghai" in exchange:
        return ".SS"
    if "Shenzhen" in exchange:
        return ".SZ"
    return ""


def normalize_index_constituents(df: pd.DataFrame, index_name: str, index_code: str) -> pd.DataFrame:
    # AKShare currently returns Chinese column names from CSI.
    rename_map = {
        "日期": "date",
        "指数代码": "index_code",
        "指数名称": "index_name_cn",
        "指数英文名称": "index_name_en",
        "成分券代码": "ticker",
        "成分券名称": "name_cn",
        "成分券英文名称": "name_en",
        "交易所": "exchange_cn",
        "交易所英文名称": "exchange",
        "权重": "weight_pct",
    }
    out = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}).copy()
    if "ticker" not in out.columns:
        raise ValueError(f"Ticker column not found for {index_name}. Columns returned: {list(df.columns)}")
    out["ticker"] = out["ticker"].astype(str).str.extract(r"(\d{6})", expand=False).str.zfill(6)
    out["index_name"] = index_name
    out["index_code"] = index_code
    if "exchange" not in out.columns:
        out["exchange"] = out["ticker"].map(normalize_exchange_from_code)
    out["yahoo_ticker"] = out.apply(lambda r: r["ticker"] + yahoo_suffix(str(r.get("exchange", ""))), axis=1)
    out["as_of_date"] = AS_OF_DATE
    cols = [
        "as_of_date", "index_name", "index_code", "ticker", "yahoo_ticker",
        "name_cn", "name_en", "exchange", "exchange_cn", "weight_pct",
    ]
    return out[[c for c in cols if c in out.columns]].sort_values("ticker").reset_index(drop=True)


def fetch_index(index_name: str, index_code: str) -> pd.DataFrame:
    # Prefer weights if available; otherwise use constituents only.
    try:
        raw = ak.index_stock_cons_weight_csindex(symbol=index_code)
    except Exception:
        raw = ak.index_stock_cons_csindex(symbol=index_code)
    return normalize_index_constituents(raw, index_name, index_code)


def normalize_spot_df(df: pd.DataFrame, exchange: str) -> pd.DataFrame:
    rename_map = {
        "代码": "ticker",
        "名称": "name_cn",
        "最新价": "last_price",
        "涨跌幅": "pct_change",
        "成交量": "volume",
        "成交额": "turnover",
        "总市值": "market_cap",
        "流通市值": "free_float_market_cap",
        "行业": "industry_cn",
    }
    out = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}).copy()
    if "ticker" not in out.columns:
        raise ValueError(f"Ticker column not found for {exchange}. Columns returned: {list(df.columns)}")
    out["ticker"] = out["ticker"].astype(str).str.extract(r"(\d{6})", expand=False).str.zfill(6)
    out["exchange"] = exchange
    out["yahoo_ticker"] = out["ticker"] + yahoo_suffix(exchange)
    out["as_of_date"] = AS_OF_DATE
    cols = [
        "as_of_date", "ticker", "yahoo_ticker", "name_cn", "exchange",
        "industry_cn", "last_price", "pct_change", "volume", "turnover",
        "market_cap", "free_float_market_cap",
    ]
    return out[[c for c in cols if c in out.columns]].sort_values("ticker").reset_index(drop=True)


def fetch_all_sh_sz_a_shares() -> pd.DataFrame:
    sh = normalize_spot_df(
        _fetch_with_retry(lambda: ak.stock_sh_a_spot_em(), "Shanghai A-shares"),
        "Shanghai Stock Exchange",
    )
    # Small delay between exchanges — Eastmoney rate-limits aggressively
    time.sleep(3)
    sz = normalize_spot_df(
        _fetch_with_retry(lambda: ak.stock_sz_a_spot_em(), "Shenzhen A-shares"),
        "Shenzhen Stock Exchange",
    )
    all_a = pd.concat([sh, sz], ignore_index=True).drop_duplicates(subset=["ticker", "exchange"])
    return all_a.sort_values(["exchange", "ticker"]).reset_index(drop=True)


def main() -> None:
    index_frames = {}
    for index_name, index_code in INDEXES.items():
        print(f"Fetching {index_name} ({index_code})...")
        df = fetch_index(index_name, index_code)
        index_frames[index_name] = df
        out_path = OUTPUT_DIR / f"{index_name.lower().replace(' ', '')}_constituents.csv"
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"  saved {len(df):,} rows -> {out_path}")

    print("Fetching all Shanghai + Shenzhen A-shares... (may fail from some networks)")
    try:
        all_a = fetch_all_sh_sz_a_shares()
        all_path = OUTPUT_DIR / "all_shanghai_shenzhen_a_shares.csv"
        all_a.to_csv(all_path, index=False, encoding="utf-8-sig")
        print(f"  saved {len(all_a):,} rows -> {all_path}")
    except Exception as exc:
        print(f"  Skipped — Eastmoney connection failed: {type(exc).__name__}")
        print(f"  CSI 300/500/1000 data was saved successfully. Re-run later for full A-share list.")
        all_a = None

    # Combined universe with index membership flags
    if all_a is not None:
        combined = all_a.copy()
        for index_name, df in index_frames.items():
            flag_col = "in_" + index_name.lower().replace(" ", "_")
            members = set(df["ticker"].astype(str))
            combined[flag_col] = combined["ticker"].isin(members)

        combined_path = OUTPUT_DIR / "combined_a_share_universe.csv"
        combined.to_csv(combined_path, index=False, encoding="utf-8-sig")
        print(f"  saved {len(combined):,} rows -> {combined_path}")

        xlsx_path = OUTPUT_DIR / "livermore_a_share_universe.xlsx"
        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
            pd.DataFrame({
                "field": ["as_of_date", "source", "note"],
                "value": [AS_OF_DATE, "AKShare: CSI / Eastmoney endpoints",
                          "CSI 300/500/1000 plus all Shanghai + Shenzhen A-shares; "
                          "excludes Beijing Stock Exchange"],
            }).to_excel(writer, sheet_name="README", index=False)
            for index_name, df in index_frames.items():
                sheet = index_name.replace(" ", "_")
                df.to_excel(writer, sheet_name=sheet, index=False)
            all_a.to_excel(writer, sheet_name="All_SH_SZ_A_Shares", index=False)
            combined.to_excel(writer, sheet_name="Combined_Universe", index=False)
        print(f"  saved workbook -> {xlsx_path}")
    else:
        print("  Skipping combined/excel — run again when full A-share data is available")


if __name__ == "__main__":
    main()
