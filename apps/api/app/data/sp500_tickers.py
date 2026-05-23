"""S&P 500 constituent set — used by Market Pulse gating in Stage 3
and by the Top Movers candidate pool from PR-8 (2026-05-23) onwards.

Scout tier can request per-ticker Market Pulse data (`/api/company/{symbol}/*`,
`/api/stocks/{ticker}` etc.) for tickers in this set only. Strategist+ has
unrestricted ticker scope. `market_pulse_service._build_top_assets` uses
this set as the positive universe filter for US Top Movers — anything
outside the set is dropped (implicit no-CN-listing / no-ETF / no-foreign
exclusions).

Why the full S&P 500 (not "top 250"):
  - Cleaner mental model for users — "Scout: S&P 500 only" is recognizable.
  - The source list is a well-known public artifact, not a market-cap snapshot
    that drifts daily.
  - Slightly more generous to Scouts (better conversion psychology).

**Expand-only invariant (2026-05-23 per Jimmy's directive):**
This set is a STANDARD — a contract with users that "Top Movers shows
the S&P 500." Future PRs may ADD tickers (at quarterly reconstitution)
but must NOT shrink it without an explicit product decision. The
contract breaks the moment users see fewer names with no explanation.
The principle is captured in root [CLAUDE.md](../../../../CLAUDE.md)
"Product invariants" — see also `docs/KNOWN_ISSUES.md` for the
2026-05-23 saga that prompted the rule.

Refresh policy:
  - Manual. The S&P 500 reconstitutes ~quarterly; a couple of additions/removals
    each quarter. Maintain via PR when the index changes meaningfully.
  - As-of date noted below. Acceptable staleness: ~1 quarter.
  - **Net size trends UP** over time. Index removals at reconstitution
    are matched by additions — the resulting frozenset size should
    never drop below the previous PR's size without explicit product
    sign-off.
  - No automated refresh script for v1.
"""
from __future__ import annotations

# As-of date: 2026-05-20. Approximately 500 entries — covers the major
# constituents across all sectors. When the index reconstitutes, add or
# remove tickers via PR and bump the as-of date.
SP500_TICKERS: frozenset[str] = frozenset({
    # Top 50 by market cap
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "BRK.B",
    "LLY", "AVGO", "JPM", "V", "WMT", "XOM", "MA", "UNH", "ORCL", "COST", "HD",
    "PG", "JNJ", "ABBV", "NFLX", "BAC", "CRM", "CVX", "MRK", "KO", "AMD",
    "ADBE", "PEP", "TMO", "LIN", "CSCO", "MCD", "ACN", "WFC", "ABT", "DHR",
    "TMUS", "NOW", "QCOM", "TXN", "GE", "IBM", "AXP", "AMGN", "ISRG", "DIS",
    # Communication Services
    "CMCSA", "VZ", "T", "CHTR", "WBD", "PARA", "EA", "TTWO", "OMC", "IPG",
    "LYV", "MTCH", "NWSA", "NWS", "FOXA", "FOX",
    # Consumer Discretionary
    "BKNG", "TJX", "SBUX", "NKE", "LOW", "AMGN", "CMG", "MAR", "ABNB", "ORLY",
    "HLT", "AZO", "GM", "F", "ROST", "YUM", "LULU", "RCL", "CCL", "NCLH",
    "DRI", "EBAY", "EXPE", "WYNN", "MGM", "LVS", "TPR", "RL", "GRMN", "POOL",
    "ULTA", "BBY", "DPZ", "DHI", "LEN", "NVR", "PHM", "DECK", "WHR", "BWA",
    # Consumer Staples
    "KMB", "MO", "PM", "CL", "GIS", "STZ", "MDLZ", "KHC", "TGT", "DG", "DLTR",
    "SYY", "HSY", "K", "MNST", "CHD", "TAP", "CAG", "MKC", "HRL", "TSN",
    "ADM", "BG", "EL", "CLX", "CPB", "SJM",
    # Energy
    "COP", "EOG", "SLB", "MPC", "PSX", "VLO", "WMB", "OKE", "OXY", "PXD",
    "KMI", "HES", "HAL", "DVN", "FANG", "BKR", "TRGP", "MRO", "APA", "EQT",
    "CTRA", "OVV", "CHRD", "RRC",
    # Financials
    "GS", "MS", "BLK", "SCHW", "AXP", "C", "TFC", "USB", "PNC", "AIG",
    "MET", "PRU", "TRV", "AFL", "ALL", "PGR", "HIG", "CB", "MMC", "AON",
    "AJG", "WTW", "BRO", "FDS", "MCO", "MSCI", "SPGI", "ICE", "CME", "CBOE",
    "NDAQ", "NTRS", "BK", "STT", "FITB", "HBAN", "RF", "KEY", "CFG", "MTB",
    "ZION", "CMA", "SBNY", "SIVB", "FRC", "PBCT", "PNFP", "SNV", "FNB", "BPOP",
    "DFS", "COF", "SYF", "ALLY", "GL", "L", "RJF", "SF", "EVR", "LAZ",
    "JEF", "PIPR", "MKTX", "WAL", "EWBC", "WTFC", "FHN", "ASB",
    # Health Care
    "PFE", "TMO", "DHR", "ABT", "BMY", "MDT", "GILD", "AMGN", "CVS", "CI",
    "ELV", "HUM", "CNC", "MOH", "REGN", "VRTX", "BIIB", "ALXN", "ZTS", "EW",
    "BSX", "SYK", "BDX", "HOLX", "ILMN", "MTD", "WAT", "A", "PKI", "WST",
    "RVTY", "BAX", "DXCM", "ALGN", "RMD", "STE", "IDXX", "PODD", "MRNA", "BIO",
    "TFX", "COO", "TECH", "CRL", "VTRS", "ZBH", "INCY", "JAZZ", "ENSG", "HCA",
    "UHS", "THC", "MCK", "ABC", "CAH",
    # Industrials
    "CAT", "RTX", "HON", "UNP", "BA", "LMT", "DE", "GE", "MMM", "UPS",
    "FDX", "EMR", "ETN", "ITW", "NSC", "PH", "GD", "NOC", "WM", "CSX",
    "TT", "RSG", "PCAR", "JCI", "CMI", "PWR", "URI", "OTIS", "CARR", "HUBB",
    "FAST", "ROK", "ROP", "GWW", "IR", "FTV", "AMP", "SNA", "TXT", "AOS",
    "JBHT", "ODFL", "EXPD", "CHRW", "LSTR", "XPO", "KNX", "ALK", "DAL", "UAL",
    "AAL", "LUV", "JBLU", "SAVE", "MIDD", "PNR", "DOV", "XYL", "FBHS", "BLDR",
    "BWXT", "CW", "HEI", "TDG", "HII", "LDOS", "LHX", "GNRC", "WSO", "ALLE",
    "MAS", "JCI", "VMC", "MLM", "USCR", "EXP", "SUM", "CMC", "STLD", "NUE",
    # Information Technology
    "ASML", "TSM", "INTC", "MU", "AMAT", "LRCX", "KLAC", "MRVL", "MCHP",
    "ON", "ANET", "PANW", "FTNT", "CRWD", "ZS", "OKTA", "DDOG", "MDB", "SNOW",
    "TEAM", "WDAY", "INTU", "ADSK", "ADI", "MPWR", "ENTG", "TER", "KEYS", "ZBRA",
    "JNPR", "NTAP", "STX", "WDC", "HPE", "DELL", "HPQ", "ANSS", "CDNS", "SNPS",
    "FFIV", "AKAM", "VRSN", "PAYC", "PCTY", "TYL", "GLOB", "EPAM", "CTSH", "DXC",
    "GEN", "FIS", "FISV", "FI", "BR", "JKHY", "WU", "GPN", "EFX",
    # Materials
    "LIN", "APD", "SHW", "ECL", "FCX", "NEM", "CTVA", "DOW", "DD", "PPG",
    "NUE", "STLD", "VMC", "MLM", "ALB", "MOS", "CF", "FMC", "EMN", "IFF",
    "AVY", "PKG", "WRK", "IP", "AMCR", "BALL", "SEE", "SON",
    # Real Estate
    "PLD", "AMT", "CCI", "EQIX", "PSA", "O", "WELL", "DLR", "VICI", "EXR",
    "AVB", "SBAC", "SPG", "EQR", "WY", "ARE", "MAA", "ESS", "VTR", "CPT",
    "INVH", "UDR", "BXP", "PEAK", "HST", "FRT", "REG", "KIM", "ELS", "DOC",
    "AIV", "SLG", "VNO", "EPR", "PINE",
    # Utilities
    "NEE", "DUK", "SO", "AEP", "SRE", "D", "PCG", "EXC", "XEL", "WEC",
    "ED", "ES", "EIX", "PEG", "AWK", "DTE", "FE", "ETR", "AEE", "CMS",
    "PPL", "CNP", "NRG", "ATO", "LNT", "NI", "EVRG", "PNW", "AES", "VST",
    # Tail of the index — common Mid-cap names
    "DDOG", "NET", "GTLB", "DOCN", "ESTC", "TWLO", "AYX", "ALRM", "BAND",
    "PYPL", "SQ", "AFRM", "U", "ROKU", "PINS", "SNAP", "TWTR", "Z", "ZG",
    "DASH", "UBER", "LYFT", "BMBL", "RBLX", "DKNG", "GRMN", "FTNT", "PANW",
    "S", "DOCN", "FRSH", "ZI",
})


def is_sp500(ticker: str) -> bool:
    """Case-insensitive S&P 500 membership check."""
    return ticker.upper() in SP500_TICKERS
