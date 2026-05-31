#!/usr/bin/env python3
"""
Wyckoff Scanner — Jump the Creek (Bullish) & Break the Ice (Bearish)
Scans S&P 500, Nasdaq 100, Russell 2000

Wyckoff Phases Detected:
  BULLISH — Accumulation → Spring → Jump the Creek (breakout above creek/resistance)
  BEARISH — Distribution → Upthrust → Break the Ice (breakdown below support)

Supplementary signals:
  VCP (Volatility Contraction Pattern), RS vs SPY, Volume Effort/Result
"""

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import time
import webbrowser
import warnings
import sys
from datetime import datetime
from io import StringIO

warnings.filterwarnings("ignore")

# Windows consoles default to cp1252, which can't encode the Unicode box-drawing
# and ellipsis characters used in progress output. Force UTF-8 so prints don't crash.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ─── Ticker Universe ──────────────────────────────────────────────────────────

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# Fallback S&P 500 list (used only if Wikipedia is unreachable). Not exhaustive
# but covers the most-liquid names so the scanner always has something to work on.
SP500_FALLBACK = (
    "AAPL MSFT NVDA AMZN META GOOGL GOOG BRK-B LLY AVGO TSLA JPM V XOM UNH MA "
    "JNJ PG HD COST ABBV MRK CVX ADBE WMT CRM KO PEP BAC NFLX AMD TMO MCD CSCO "
    "ACN ABT LIN ORCL DHR WFC TXN PM DIS INTC VZ INTU AMGN IBM CAT NOW QCOM GE "
    "NKE UNP SPGI HON LOW AMAT BKNG GS UBER MS BA RTX AXP BLK PLD SYK SBUX GILD "
    "MDT ELV TJX VRTX LRCX ADP DE C MMC ISRG REGN PGR CB ZTS BSX SCHW MO BMY SO "
    "FI CI DUK PANW MU SNPS CME APH KLAC NOC ICE EQIX WM ITW SHW CL AON MCK CDNS "
    "USB GD MMM EOG FCX TGT EMR PYPL CSX MAR PXD ORLY MNST ADSK PSX APD ROP NXPI "
    "ABNB MPC AJG NSC FDX HCA SLB TT WELL AZO TDG PH ECL CTAS PCAR MSI CARR EW "
    "CMG HLT OXY ANET F GM AIG MET TFC SPG AFL DXCM ROST SRE TRV NEM PSA O HUM "
    "AEP KMB DOW BK ALL GIS D KMI CPRT IDXX KHC EXC FTNT YUM A DD VLO LHX FAST "
    "BIIB CTVA OTIS GWW VRSK CMI ON IQV PRU GEHC NUE EA KR HSY CCI ED DLR XEL "
    "WMB STZ DG VICI RSG GLW PWR HES ACGL EFX KDP MLM CHTR WEC PCG IT FANG AVB "
    "ZBH ANSS WBD MTD KEYS HPQ DFS TROW FITB STT MPWR EBAY APTV WST RMD WTW DAL"
).split()

NASDAQ100_FALLBACK = (
    "AAPL MSFT NVDA AMZN META GOOGL GOOG AVGO TSLA COST NFLX AMD PEP ADBE CSCO "
    "TMUS INTC INTU QCOM AMAT TXN BKNG HON AMGN ISRG VRTX SBUX GILD ADP MDLZ "
    "REGN LRCX PANW MU ADI SNPS KLAC CDNS MELI ABNB PYPL MAR ORLY CSX MNST CTAS "
    "ASML NXPI WDAY FTNT PCAR ROP ODFL CPRT DXCM ADSK PAYX MRVL KDP AEP CHTR "
    "IDXX FAST EA EXC CCEP VRSK BKR KHC GEHC CTSH BIIB CDW ON XEL ANSS DLTR "
    "TTD GFS WBD ZS DDOG TEAM MDB ROST CRWD MRNA SIRI LULU FANG"
).split()


def _read_wiki_tables(url):
    """Fetch a Wikipedia page with browser headers, then parse its HTML tables."""
    r = requests.get(url, timeout=20, headers=BROWSER_HEADERS)
    r.raise_for_status()
    return pd.read_html(StringIO(r.text))


def get_sp500_tickers():
    try:
        tables = _read_wiki_tables(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        )
        return tables[0]["Symbol"].str.replace(".", "-", regex=False).tolist()
    except Exception as e:
        print(f"  [warn] SP500 fetch failed ({e}); using fallback list")
        return SP500_FALLBACK


def get_nasdaq100_tickers():
    try:
        tables = _read_wiki_tables("https://en.wikipedia.org/wiki/Nasdaq-100")
        for t in tables:
            for col in ["Ticker", "Symbol"]:
                if col in t.columns:
                    return t[col].dropna().str.replace(".", "-", regex=False).tolist()
    except Exception as e:
        print(f"  [warn] Nasdaq100 fetch failed ({e}); using fallback list")
    return NASDAQ100_FALLBACK


def _ishares_russell2000():
    """Top 500 Russell 2000 components from iShares IWM holdings CSV.

    The iShares file has a variable number of preamble lines, so we locate the
    real header row dynamically. iShares sometimes returns an HTML captcha page
    instead of the CSV — we detect that and let the caller fall back.
    """
    url = (
        "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/"
        "1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
    )
    r = requests.get(url, timeout=20, headers=BROWSER_HEADERS)
    r.raise_for_status()
    if r.text.lstrip().lower().startswith("<!doctype") or "<html" in r.text[:200].lower():
        raise ValueError("iShares returned HTML (bot-blocked), not CSV")
    lines = r.text.splitlines()
    header_idx = next(
        (i for i, ln in enumerate(lines) if ln.lstrip().startswith('"Ticker"')
         or ln.lstrip().startswith("Ticker,")),
        None,
    )
    if header_idx is None:
        raise ValueError("could not locate header row")
    df = pd.read_csv(StringIO("\n".join(lines[header_idx:])))
    tickers = df["Ticker"].dropna().astype(str).str.strip().tolist()
    clean = [t for t in tickers if t and t not in ("-", "") and "." not in t]
    return clean[:500]


def _sp600_smallcap():
    """S&P 600 SmallCap constituents from Wikipedia — reliable small-cap proxy."""
    tables = _read_wiki_tables(
        "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"
    )
    for t in tables:
        for col in ["Symbol", "Ticker symbol", "Ticker"]:
            if col in t.columns:
                return t[col].dropna().str.replace(".", "-", regex=False).tolist()
    raise ValueError("no symbol column found in S&P 600 tables")


def get_smallcap_tickers():
    """Small-cap universe: iShares Russell 2000 if reachable, else S&P 600.

    Returns (tickers, label) so the report shows which source was actually used.
    """
    try:
        return _ishares_russell2000(), "Russell 2000"
    except Exception as e:
        print(f"  [warn] Russell 2000 (iShares) failed ({e})")
    try:
        tk = _sp600_smallcap()
        print("  [info] using S&P 600 SmallCap as small-cap proxy")
        return tk, "S&P 600"
    except Exception as e:
        print(f"  [warn] S&P 600 fallback failed ({e}); skipping small-caps")
        return [], "Small Cap"

# ─── Technical Helpers ────────────────────────────────────────────────────────

def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))

BREAKOUT_WINDOW = 6  # recent bars treated as the potential breakout/breakdown zone

def detect_consolidation(close, high, low, lookback=50, min_days=18,
                         exclude_recent=BREAKOUT_WINDOW):
    """
    Returns (is_consolidating, range_high, range_low, range_pct).

    The trading range (the "creek" / "ice" levels) is measured over `lookback`
    bars ending `exclude_recent` bars ago — i.e. it EXCLUDES the most recent
    breakout window. This is essential: if the range included the latest bars,
    today's price could never exceed its own range high, so a breakout could
    never be detected.
    """
    needed = lookback + exclude_recent
    if len(close) < needed:
        return False, None, None, 0
    end = -exclude_recent if exclude_recent else None
    c = close.iloc[-needed:end]
    h = high.iloc[-needed:end]
    l = low.iloc[-needed:end]
    rng_high = h.max()
    rng_low  = l.min()
    rng_pct  = (rng_high - rng_low) / rng_low * 100
    if rng_pct >= 25:
        return False, rng_high, rng_low, rng_pct
    mid  = (rng_high + rng_low) / 2
    band_hi = mid + (rng_high - mid) * 0.85
    band_lo = mid - (mid - rng_low) * 0.85
    days_in = ((c >= band_lo) & (c <= band_hi)).sum()
    return days_in >= min_days, rng_high, rng_low, rng_pct

def detect_spring(close, low, rng_low, lookback=25):
    """Brief dip below range support that closes back above it — Wyckoff Spring."""
    if rng_low is None or len(close) < lookback:
        return False, 0
    rc = close.iloc[-lookback:]
    rl = low.iloc[-lookback:]
    mask = (rl < rng_low * 0.985) & (rc > rng_low)
    if not mask.any():
        return False, 0
    idx  = mask[::-1].idxmax()
    days = len(close) - close.index.get_loc(idx) - 1
    return True, days

def detect_upthrust(close, high, rng_high, lookback=25):
    """Brief spike above range resistance that closes back below — Wyckoff Upthrust."""
    if rng_high is None or len(close) < lookback:
        return False, 0
    rc = close.iloc[-lookback:]
    rh = high.iloc[-lookback:]
    mask = (rh > rng_high * 1.015) & (rc < rng_high)
    if not mask.any():
        return False, 0
    idx  = mask[::-1].idxmax()
    days = len(close) - close.index.get_loc(idx) - 1
    return True, days

def detect_jump_creek(close, volume, rng_high, lookback=6):
    """
    Jump the Creek: recent close above range resistance on above-avg volume.
    Returns (triggered, vol_ratio, pct_above_creek).
    """
    if rng_high is None or len(close) < lookback + 30:
        return False, 0, 0
    rc  = close.iloc[-lookback:]
    rv  = volume.iloc[-lookback:]
    avg = volume.iloc[-60:-lookback].mean()
    if avg == 0:
        return False, 0, 0
    above = rc > rng_high * 1.003
    surge = rv > avg * 1.25
    hit   = above & surge
    if not hit.any():
        return False, 0, 0
    vr  = rv[hit].mean() / avg
    pct = (rc[hit].iloc[-1] - rng_high) / rng_high * 100
    return True, round(vr, 2), round(pct, 2)

def detect_break_ice(close, volume, rng_low, lookback=6):
    """
    Break the Ice: recent close below range support on above-avg volume.
    Returns (triggered, vol_ratio, pct_below_ice).
    """
    if rng_low is None or len(close) < lookback + 30:
        return False, 0, 0
    rc  = close.iloc[-lookback:]
    rv  = volume.iloc[-lookback:]
    avg = volume.iloc[-60:-lookback].mean()
    if avg == 0:
        return False, 0, 0
    below = rc < rng_low * 0.997
    surge = rv > avg * 1.25
    hit   = below & surge
    if not hit.any():
        return False, 0, 0
    vr  = rv[hit].mean() / avg
    pct = (rng_low - rc[hit].iloc[-1]) / rng_low * 100
    return True, round(vr, 2), round(pct, 2)

def volume_dry_up_pct(volume, lookback=50, recent=10):
    """How much lower is recent volume vs the prior baseline? (higher = more dry-up)"""
    if len(volume) < lookback:
        return 0
    baseline = volume.iloc[-lookback:-recent].mean()
    current  = volume.iloc[-recent:].mean()
    return max((baseline - current) / baseline * 100, 0)

def vcp_score(close, lookback=60):
    """
    Volatility Contraction Pattern: three segments of contracting price range.
    Returns a 0–30 contribution to the bull score.
    """
    if len(close) < lookback:
        return 0
    seg = lookback // 3
    def rng(s): return (s.max() - s.min()) / s.mean() if s.mean() > 0 else 0
    r1 = rng(close.iloc[-lookback     : -2*seg])
    r2 = rng(close.iloc[-2*seg        : -seg  ])
    r3 = rng(close.iloc[-seg          :       ])
    if r1 > r2 > r3 > 0:
        return min((r1 / r3) * 15, 30)
    return 0

def relative_strength(stock_close, spy_close, period=50):
    """Stock return minus SPY return over `period` days."""
    if len(stock_close) < period or len(spy_close) < period:
        return 0
    sr = stock_close.iloc[-1] / stock_close.iloc[-period] - 1
    mr = spy_close.iloc[-1]   / spy_close.iloc[-period]   - 1
    return round((sr - mr) * 100, 2)

def bearish_volume_dominance(close, volume, days=20):
    """True if average volume on down days > 1.2x average volume on up days."""
    if len(close) < days:
        return False
    ret  = close.pct_change().iloc[-days:]
    vol  = volume.iloc[-days:]
    dv   = vol[ret < 0].mean()
    uv   = vol[ret > 0].mean()
    return dv > uv * 1.2 if uv > 0 else False

# ─── Wyckoff Scoring ──────────────────────────────────────────────────────────

def score_bullish(close, high, low, volume, spy_close):
    """
    Wyckoff Accumulation + Jump the Creek score (0–100).
    Requires a consolidation zone as precondition.
    """
    score = 0
    d = {}

    consol, rh, rl, rp = detect_consolidation(close, high, low)
    if not consol:
        return 0, {}
    score += 15
    d["range_high"] = round(rh, 2)
    d["range_low"]  = round(rl, 2)
    d["range_pct"]  = round(rp, 1)

    jtc, vr, bp = detect_jump_creek(close, volume, rh)
    d["jump_creek"] = jtc
    if jtc:
        score += 35
        d["vol_ratio"]     = vr
        d["breakout_pct"]  = bp

    spring, sdays = detect_spring(close, low, rl)
    d["spring"] = spring
    if spring:
        score += 15
        d["spring_days_ago"] = sdays

    vdu = volume_dry_up_pct(volume)
    d["vol_dry_pct"] = round(vdu, 1)
    score += 10 if vdu > 20 else (5 if vdu > 10 else 0)

    rs = relative_strength(close, spy_close)
    d["rs_vs_spy"] = rs
    score += 15 if rs > 5 else (7 if rs > 0 else 0)

    vc = vcp_score(close)
    d["vcp_score"] = round(vc, 1)
    score += vc * 0.3

    r = rsi(close).iloc[-1]
    d["rsi"] = round(r, 1)
    score += 10 if 50 < r < 70 else (5 if r >= 70 else 0)

    return min(round(score), 100), d

def score_bearish(close, high, low, volume, spy_close):
    """
    Wyckoff Distribution + Break the Ice score (0–100).
    Requires consolidation at a relatively elevated price level.
    """
    score = 0
    d = {}

    consol, rh, rl, rp = detect_consolidation(close, high, low)
    if not consol:
        return 0, {}

    # Distribution happens at high prices — stock should be in upper half of 1-year range
    hi_1y = high.rolling(200).max().iloc[-1]
    lo_1y = low.rolling(200).min().iloc[-1]
    if hi_1y == lo_1y:
        return 0, {}
    position = (close.iloc[-1] - lo_1y) / (hi_1y - lo_1y)
    if position < 0.45:
        return 0, {}

    score += 15
    d["range_high"] = round(rh, 2)
    d["range_low"]  = round(rl, 2)
    d["range_pct"]  = round(rp, 1)

    bti, vr, bp = detect_break_ice(close, volume, rl)
    d["break_ice"] = bti
    if bti:
        score += 35
        d["vol_ratio"]    = vr
        d["breakdown_pct"] = bp

    ut, udays = detect_upthrust(close, high, rh)
    d["upthrust"] = ut
    if ut:
        score += 15
        d["upthrust_days_ago"] = udays

    rs = relative_strength(close, spy_close)
    d["rs_vs_spy"] = rs
    score += 15 if rs < -5 else (7 if rs < 0 else 0)

    bvd = bearish_volume_dominance(close, volume)
    d["bearish_volume"] = bvd
    if bvd:
        score += 10

    r = rsi(close).iloc[-1]
    d["rsi"] = round(r, 1)
    score += 10 if 30 < r < 50 else (5 if r <= 30 else 0)

    return min(round(score), 100), d

# ─── Scanner ─────────────────────────────────────────────────────────────────

def scan(tickers, spy_close, label, batch=50):
    results = []
    total   = len(tickers)
    for i in range(0, total, batch):
        chunk = tickers[i : i + batch]
        pct   = int((i / total) * 100)
        print(f"  [{label}] {pct:3d}% — {i}/{total}", end="\r")
        try:
            raw = yf.download(
                chunk, period="9mo", interval="1d",
                group_by="ticker", progress=False, threads=True, timeout=30,
            )
        except Exception:
            continue

        for tk in chunk:
            try:
                df = raw[tk].dropna() if len(chunk) > 1 else raw.dropna()
                if len(df) < 80:
                    continue
                c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]

                spy = spy_close.reindex(c.index, method="ffill").dropna()
                c2  = c.reindex(spy.index).dropna()
                if len(c2) < 60:
                    continue
                h2 = h.reindex(c2.index)
                l2 = l.reindex(c2.index)
                v2 = v.reindex(c2.index)

                bs, bd = score_bullish(c2, h2, l2, v2, spy)
                brs, brd = score_bearish(c2, h2, l2, v2, spy)

                top = max(bs, brs)
                if top < 30:
                    continue

                results.append({
                    "ticker":       tk,
                    "index":        label,
                    "price":        round(float(c.iloc[-1]), 2),
                    "bull_score":   bs,
                    "bear_score":   brs,
                    "signal":       "BULLISH" if bs >= brs else "BEARISH",
                    "bull_details": bd,
                    "bear_details": brd,
                })
            except Exception:
                continue
        time.sleep(0.3)

    print(f"  [{label}] 100% — {total}/{total}  ")
    return results

# ─── HTML Report ─────────────────────────────────────────────────────────────

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wyckoff Scanner</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#0d0d14;color:#dde}
header{background:#12121f;padding:18px 28px;border-bottom:1px solid #222238}
header h1{font-size:1.5rem;color:#00e5b0;letter-spacing:-.02em}
header p{color:#666;font-size:.8rem;margin-top:4px}
.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;padding:12px 28px;background:#0f0f1a;border-bottom:1px solid #1e1e30}
.toolbar select,.toolbar input{background:#181828;border:1px solid #2e2e4a;color:#dde;padding:6px 10px;border-radius:5px;font-size:.82rem}
.toolbar label{font-size:.82rem;color:#888}
#cnt{font-size:.8rem;color:#555;margin-left:4px}
.kpis{display:flex;gap:14px;padding:14px 28px;background:#0f0f1a;flex-wrap:wrap;border-bottom:1px solid #1e1e30}
.kpi{background:#12121f;border:1px solid #1e1e30;border-radius:8px;padding:10px 18px;text-align:center;min-width:110px}
.kpi .n{font-size:1.7rem;font-weight:700}
.kpi .l{font-size:.7rem;color:#666;margin-top:2px}
.bull{color:#00e5b0}.bear{color:#ff6565}.neu{color:#ffc048}
.wrap{overflow-x:auto;height:calc(100vh - 210px)}
table{width:100%;border-collapse:collapse}
th{background:#12121f;color:#666;font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;padding:9px 13px;text-align:left;position:sticky;top:0;cursor:pointer;user-select:none;white-space:nowrap}
th:hover{color:#dde}
td{padding:9px 13px;border-bottom:1px solid #171724;font-size:.84rem;vertical-align:middle}
tr:hover td{background:#14142a}
.tk{font-weight:700;color:#fff;font-size:.92rem}
.bar-wrap{display:flex;align-items:center;gap:6px}
.bar{height:5px;border-radius:3px;transition:width .2s}
.sn{font-weight:700;min-width:26px;font-size:.85rem}
.badge{display:inline-block;padding:2px 7px;border-radius:4px;font-size:.7rem;font-weight:700}
.bb{background:rgba(0,229,176,.12);color:#00e5b0;border:1px solid rgba(0,229,176,.25)}
.rb{background:rgba(255,101,101,.12);color:#ff6565;border:1px solid rgba(255,101,101,.25)}
.ib{background:rgba(120,120,200,.12);color:#99a;border:1px solid rgba(120,120,200,.2);font-size:.66rem}
.pill{display:inline-block;padding:1px 6px;border-radius:3px;font-size:.68rem;margin:1px}
.pg{background:rgba(0,229,176,.08);color:#00e5b0}
.pr{background:rgba(255,101,101,.08);color:#ff6565}
.py{background:rgba(255,192,72,.08);color:#ffc048}
.pgr{background:rgba(150,150,180,.08);color:#777}
.det{color:#484860;font-size:.73rem}
</style>
</head>
<body>
<header>
  <h1>Wyckoff Scanner — Jump the Creek &amp; Break the Ice</h1>
  <p>S&amp;P 500 · Nasdaq 100 · Russell 2000 &nbsp;|&nbsp; Generated: __DATE__</p>
</header>
<div class="toolbar">
  <label>Signal
    <select id="fSig" onchange="go()">
      <option value="ALL">All</option>
      <option value="BULLISH">Bullish (Jump Creek)</option>
      <option value="BEARISH">Bearish (Break Ice)</option>
    </select>
  </label>
  <label>Min Score
    <input id="fScore" type="number" value="35" min="0" max="100" onchange="go()" style="width:56px">
  </label>
  <label>Index
    <select id="fIdx" onchange="go()">
      <option value="ALL">All Indices</option>
      <option value="S&P 500">S&amp;P 500</option>
      <option value="Nasdaq 100">Nasdaq 100</option>
      <option value="Russell 2000">Russell 2000</option>
    </select>
  </label>
  <label>Ticker <input id="fTk" type="text" placeholder="AAPL…" onkeyup="go()" style="width:80px"></label>
  <span id="cnt"></span>
</div>
<div class="kpis">
  <div class="kpi"><div class="n bull" id="kBull">—</div><div class="l">Bullish Setups</div></div>
  <div class="kpi"><div class="n bear" id="kBear">—</div><div class="l">Bearish Setups</div></div>
  <div class="kpi"><div class="n neu"  id="kTotal">—</div><div class="l">Total Matches</div></div>
  <div class="kpi"><div class="n" style="color:#7ec8e3" id="kJTC">—</div><div class="l">Jump Creek Active</div></div>
  <div class="kpi"><div class="n" style="color:#ffaa6b" id="kBTI">—</div><div class="l">Break Ice Active</div></div>
  <div class="kpi"><div class="n" style="color:#b0a0ff" id="kSpring">—</div><div class="l">Springs Detected</div></div>
  <div class="kpi"><div class="n" style="color:#ffcc80" id="kUT">—</div><div class="l">Upthrusts</div></div>
</div>
<div class="wrap">
<table>
  <thead><tr>
    <th onclick="sort(0)">Ticker ↕</th>
    <th onclick="sort(1)">Index ↕</th>
    <th onclick="sort(2)">Price ↕</th>
    <th onclick="sort(3)">Signal ↕</th>
    <th onclick="sort(4)">Bull Score ↕</th>
    <th onclick="sort(5)">Bear Score ↕</th>
    <th>Key Signals</th>
    <th onclick="sort(7)">RSI ↕</th>
    <th onclick="sort(8)">RS vs SPY ↕</th>
    <th>Range / Breakout</th>
  </tr></thead>
  <tbody id="tb"></tbody>
</table>
</div>
<script>
const D=__DATA__;
let sc=4,sd=-1;
function sort(c){sc===c?sd*=-1:(sc=c,sd=-1);go();}
function go(){
  const sig=document.getElementById('fSig').value;
  const ms=+document.getElementById('fScore').value||0;
  const idx=document.getElementById('fIdx').value;
  const tk=document.getElementById('fTk').value.toUpperCase();
  let rows=D.filter(r=>{
    const s=r.signal==='BULLISH'?r.bull_score:r.bear_score;
    return(sig==='ALL'||r.signal===sig)&&s>=ms&&(idx==='ALL'||r.index===idx)&&r.ticker.includes(tk);
  });
  rows.sort((a,b)=>{
    const map=(r,i)=>[r.ticker,r.index,r.price,r.signal,r.bull_score,r.bear_score,0,
      (r.signal==='BULLISH'?r.bull_details:r.bear_details).rsi||0,
      (r.signal==='BULLISH'?r.bull_details:r.bear_details).rs_vs_spy||0][i];
    const av=map(a,sc),bv=map(b,sc);
    return typeof av==='string'?av.localeCompare(bv)*sd:(av-bv)*sd;
  });
  document.getElementById('cnt').textContent=rows.length+' results';
  document.getElementById('kBull').textContent=rows.filter(r=>r.signal==='BULLISH').length;
  document.getElementById('kBear').textContent=rows.filter(r=>r.signal==='BEARISH').length;
  document.getElementById('kTotal').textContent=rows.length;
  document.getElementById('kJTC').textContent=rows.filter(r=>r.bull_details.jump_creek).length;
  document.getElementById('kBTI').textContent=rows.filter(r=>r.bear_details.break_ice).length;
  document.getElementById('kSpring').textContent=rows.filter(r=>r.bull_details.spring).length;
  document.getElementById('kUT').textContent=rows.filter(r=>r.bear_details.upthrust).length;
  document.getElementById('tb').innerHTML=rows.map(row).join('');
}
function row(r){
  const isBull=r.signal==='BULLISH';
  const d=isBull?r.bull_details:r.bear_details;
  const pills=[];
  if(r.bull_details.jump_creek) pills.push('<span class="pill pg">Jump Creek</span>');
  if(r.bear_details.break_ice)  pills.push('<span class="pill pr">Break Ice</span>');
  if(r.bull_details.spring)     pills.push('<span class="pill pg">Spring</span>');
  if(r.bear_details.upthrust)   pills.push('<span class="pill pr">Upthrust</span>');
  if(r.bull_details.vcp_score>0)pills.push('<span class="pill py">VCP</span>');
  if(r.bull_details.vol_dry_pct>15) pills.push('<span class="pill pgr">Vol Dry-Up</span>');
  if(r.bear_details.bearish_volume) pills.push('<span class="pill pr">Bear Vol</span>');

  const rsi=d.rsi??'—';
  const rs=d.rs_vs_spy??null;
  const rsStr=rs!==null?(rs>0?'+':'')+rs+'%':'—';
  const rsC=rs!==null?(rs>0?'bull':'bear'):'';

  const det=[];
  if(d.range_high) det.push(`$${d.range_low}–$${d.range_high} (${d.range_pct}%)`);
  if(d.vol_ratio)  det.push(`Vol ${d.vol_ratio}x`);
  if(d.breakout_pct!==undefined) det.push(`+${d.breakout_pct}% above creek`);
  if(d.breakdown_pct!==undefined)det.push(`-${d.breakdown_pct}% thru ice`);

  return`<tr>
    <td><span class="tk">${r.ticker}</span></td>
    <td><span class="badge ib">${r.index}</span></td>
    <td>$${r.price}</td>
    <td><span class="badge ${isBull?'bb':'rb'}">${r.signal}</span></td>
    <td><div class="bar-wrap"><div class="bar" style="width:${r.bull_score}px;background:#00e5b0"></div><span class="sn bull">${r.bull_score}</span></div></td>
    <td><div class="bar-wrap"><div class="bar" style="width:${r.bear_score}px;background:#ff6565"></div><span class="sn bear">${r.bear_score}</span></div></td>
    <td>${pills.join('')||'<span style="color:#333">—</span>'}</td>
    <td style="color:${rsi>50?'#00e5b0':'#ff6565'}">${rsi}</td>
    <td class="${rsC}">${rsStr}</td>
    <td class="det">${det.join(' · ')}</td>
  </tr>`;
}
go();
</script>
</body>
</html>"""


def _json_default(o):
    """Convert numpy scalar types (bool_, int64, float64) to native Python."""
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    return str(o)


def build_report(results, path="wyckoff_scanner.html"):
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = (
        TEMPLATE
        .replace("__DATE__", generated)
        .replace("__DATA__", json.dumps(results, default=_json_default))
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


# ─── Email Alerts ─────────────────────────────────────────────────────────────

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

EMAIL_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "email_config.json")


def load_email_config():
    """Load SMTP settings from email_config.json next to this script.

    Environment variables (WYCKOFF_SMTP_*) override file values so the app
    password never has to live on disk if you prefer to set it in the
    scheduled-task environment instead.
    """
    cfg = {}
    if os.path.exists(EMAIL_CONFIG_PATH):
        with open(EMAIL_CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    cfg.setdefault("smtp_host", "smtp.gmail.com")
    cfg.setdefault("smtp_port", 587)
    cfg.setdefault("min_score", 80)
    # Env overrides
    cfg["sender"]       = os.environ.get("WYCKOFF_SMTP_SENDER",    cfg.get("sender", ""))
    cfg["app_password"] = os.environ.get("WYCKOFF_SMTP_PASSWORD",  cfg.get("app_password", ""))
    cfg["recipient"]    = os.environ.get("WYCKOFF_SMTP_RECIPIENT", cfg.get("recipient", cfg.get("sender", "")))
    return cfg


def _alert_table(rows, kind):
    """Build one HTML table (bullish or bearish) for the email body."""
    if not rows:
        return f"<p style='color:#888'>No {kind.lower()} setups scored above the threshold today.</p>"
    accent = "#0a8f6c" if kind == "BULLISH" else "#c43d3d"
    head = "Above Creek" if kind == "BULLISH" else "Thru Ice"
    score_key = "bull_score" if kind == "BULLISH" else "bear_score"
    body = []
    for r in rows:
        d = r["bull_details"] if kind == "BULLISH" else r["bear_details"]
        move = d.get("breakout_pct") if kind == "BULLISH" else d.get("breakdown_pct")
        move_str = (f"+{move}%" if kind == "BULLISH" else f"-{move}%") if move is not None else "—"
        body.append(
            f"<tr>"
            f"<td style='padding:6px 10px;font-weight:700'>{r['ticker']}</td>"
            f"<td style='padding:6px 10px;color:#666'>{r['index']}</td>"
            f"<td style='padding:6px 10px'>${r['price']}</td>"
            f"<td style='padding:6px 10px;font-weight:700;color:{accent}'>{r[score_key]}</td>"
            f"<td style='padding:6px 10px'>{d.get('vol_ratio','—')}x</td>"
            f"<td style='padding:6px 10px'>{move_str}</td>"
            f"<td style='padding:6px 10px'>{d.get('rs_vs_spy','—')}%</td>"
            f"</tr>"
        )
    return (
        f"<h3 style='color:{accent};margin:18px 0 6px'>{kind} — "
        f"{'Jump the Creek' if kind=='BULLISH' else 'Break the Ice'} ({len(rows)})</h3>"
        f"<table style='border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px;width:100%'>"
        f"<tr style='background:#f0f0f0;text-align:left'>"
        f"<th style='padding:6px 10px'>Ticker</th><th style='padding:6px 10px'>Index</th>"
        f"<th style='padding:6px 10px'>Price</th><th style='padding:6px 10px'>Score</th>"
        f"<th style='padding:6px 10px'>Vol</th><th style='padding:6px 10px'>{head}</th>"
        f"<th style='padding:6px 10px'>RS vs SPY</th></tr>"
        + "".join(body) + "</table>"
    )


def send_email_report(results, cfg):
    """Email bullish/bearish setups scoring >= cfg['min_score']. Returns True on success."""
    min_score = cfg["min_score"]
    bull = [r for r in results
            if r["signal"] == "BULLISH" and r["bull_score"] >= min_score]
    bear = [r for r in results
            if r["signal"] == "BEARISH" and r["bear_score"] >= min_score]
    bull.sort(key=lambda x: x["bull_score"], reverse=True)
    bear.sort(key=lambda x: x["bear_score"], reverse=True)

    if not cfg.get("sender") or not cfg.get("app_password") or not cfg.get("recipient"):
        print("  [email] skipped — email_config.json is missing sender/app_password/recipient")
        return False

    date = datetime.now().strftime("%A, %B %d, %Y")
    html = (
        f"<div style='font-family:Arial,sans-serif;max-width:760px'>"
        f"<h2 style='color:#0a0a0a'>Wyckoff Daily Alerts — {date}</h2>"
        f"<p style='color:#666'>Setups scoring <b>{min_score}+</b> across S&amp;P 500, "
        f"Nasdaq 100, and S&amp;P 600 SmallCap.</p>"
        + _alert_table(bull, "BULLISH")
        + _alert_table(bear, "BEARISH")
        + "<p style='color:#999;font-size:11px;margin-top:24px'>End-of-day screen — "
        "not investment advice. Always confirm on a chart.</p></div>"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = (f"Wyckoff Alerts {datetime.now():%Y-%m-%d} — "
                      f"{len(bull)} bullish / {len(bear)} bearish (score {min_score}+)")
    msg["From"] = cfg["sender"]
    msg["To"] = cfg["recipient"]
    msg.attach(MIMEText("HTML email — view in an HTML-capable client.", "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(cfg["smtp_host"], int(cfg["smtp_port"]), timeout=30) as s:
            s.starttls()
            s.login(cfg["sender"], cfg["app_password"])
            s.sendmail(cfg["sender"], [cfg["recipient"]], msg.as_string())
        print(f"  [email] sent to {cfg['recipient']} — {len(bull)} bullish, {len(bear)} bearish")
        return True
    except Exception as e:
        print(f"  [email] FAILED: {e}")
        return False


# ─── Main ─────────────────────────────────────────────────────────────────────

def run_scan():
    """Run the full scan across all indices; returns deduplicated, sorted results."""
    print("\nFetching ticker lists…")
    sp500   = get_sp500_tickers()
    nasdaq  = get_nasdaq100_tickers()
    smallcap, smallcap_label = get_smallcap_tickers()
    print(f"  S&P 500:      {len(sp500)} tickers")
    print(f"  Nasdaq 100:   {len(nasdaq)} tickers")
    print(f"  {smallcap_label}: {len(smallcap)} tickers")

    print("\nDownloading SPY benchmark…")
    spy = yf.download("SPY", period="9mo", interval="1d", progress=False)
    spy_close = spy["Close"]
    # Newer yfinance returns multi-index columns; squeeze to a 1-D Series.
    if hasattr(spy_close, "columns"):
        spy_close = spy_close.iloc[:, 0]

    all_results = []
    print("\nScanning S&P 500…")
    all_results += scan(sp500, spy_close, "S&P 500")
    print("Scanning Nasdaq 100…")
    all_results += scan(nasdaq, spy_close, "Nasdaq 100")
    if smallcap:
        print(f"Scanning {smallcap_label}…")
        all_results += scan(smallcap, spy_close, smallcap_label)

    # Deduplicate: keep highest combined score per ticker
    seen = {}
    for r in all_results:
        key = r["ticker"]
        top = max(r["bull_score"], r["bear_score"])
        if key not in seen or top > max(seen[key]["bull_score"], seen[key]["bear_score"]):
            seen[key] = r
    return sorted(seen.values(),
                  key=lambda x: max(x["bull_score"], x["bear_score"]), reverse=True)


def main():
    email_mode = "--email" in sys.argv
    no_open    = "--no-open" in sys.argv or email_mode

    print("=" * 58)
    print("  WYCKOFF SCANNER  —  Jump the Creek & Break the Ice")
    print("=" * 58)

    results = run_scan()

    # Build the report FIRST, so a stray console-encoding error in the summary
    # prints below can never discard the scan results.
    out = "wyckoff_scanner.html"
    build_report(results, out)
    abs_path = os.path.abspath(out)

    bull = sum(1 for r in results if r["signal"] == "BULLISH")
    bear = sum(1 for r in results if r["signal"] == "BEARISH")
    jtc  = sum(1 for r in results if r["bull_details"].get("jump_creek"))
    bti  = sum(1 for r in results if r["bear_details"].get("break_ice"))

    print("\n" + "-" * 40)
    print(f"  Total setups : {len(results)}")
    print(f"  Bullish      : {bull}  (Jump Creek active: {jtc})")
    print(f"  Bearish      : {bear}  (Break Ice active:  {bti})")
    print("-" * 40)
    print(f"\nReport -> {abs_path}")

    if email_mode:
        cfg = load_email_config()
        send_email_report(results, cfg)

    if not no_open:
        webbrowser.open(f"file:///{abs_path.replace(chr(92), '/')}")


if __name__ == "__main__":
    main()
