# China A-share universe fetcher

This package gives you a reproducible way to pull:

1. CSI 300 constituents — index code `000300`
2. CSI 500 constituents — index code `000905`
3. CSI 1000 constituents — index code `000852`
4. All Shanghai + Shenzhen A-shares, excluding Beijing Stock Exchange
5. A combined universe with membership flags for CSI 300 / 500 / 1000

## Why a script instead of a static file?

The CSI 300, CSI 500 and CSI 1000 are periodically rebalanced. Shanghai/Shenzhen A-share listings also change due to IPOs, delistings, ST status changes, suspensions, and exchange updates. For a product like Livermore, it is safer to use a refreshable source-of-truth script rather than manually maintain static tickers.

## How to run

```bash
pip install -U akshare pandas openpyxl
python fetch_china_a_share_universes.py
```

The script will create a folder named `china_a_share_universes/` with:

- `csi300_constituents.csv`
- `csi500_constituents.csv`
- `csi1000_constituents.csv`
- `all_shanghai_shenzhen_a_shares.csv`
- `combined_a_share_universe.csv`
- `livermore_a_share_universe.xlsx`

## Recommended use in Livermore

Use `combined_a_share_universe.csv` as the canonical research universe table. Store the raw index files as source snapshots so you can compare future rebalances over time.

Suggested database fields:

- `ticker`
- `exchange`
- `yahoo_ticker`
- `name_cn`
- `industry_cn`
- `in_csi_300`
- `in_csi_500`
- `in_csi_1000`
- `as_of_date`

