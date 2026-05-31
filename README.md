# Wyckoff Scanner — Jump the Creek & Break the Ice

Scans the major US equity universes for **Wyckoff method** trade setups and produces
a sortable, filterable HTML dashboard. Optionally emails the highest-conviction
setups on a daily schedule.

- **S&P 500**, **Nasdaq 100**, and **S&P 600 SmallCap** (~1,200 stocks)
- **Bullish — Jump the Creek**: accumulation range → breakout above resistance ("the creek") on expanding volume
- **Bearish — Break the Ice**: distribution range → breakdown below support ("the ice") on expanding volume
- Each stock is scored 0–100 for both bullish and bearish setups

## What it detects

| Signal | Wyckoff Phase | Meaning |
|--------|---------------|---------|
| **Jump the Creek** | Accumulation E | Breaks above consolidation resistance on volume — markup beginning |
| **Spring** | Accumulation C | Brief dip below support that recovers — final shakeout |
| **Break the Ice** | Distribution E | Breaks below consolidation support on volume — markdown beginning |
| **Upthrust** | Distribution C | Brief spike above resistance that fails — bull trap |
| **VCP** | Supplementary | Volatility Contraction Pattern — energy coiling |
| **Vol Dry-Up** | Accumulation | Volume shrinks in the range — supply absorbed |
| **Bear Vol** | Distribution | Down-day volume exceeds up-day volume |

### Scoring (0–100)

Consolidation zone (15) + primary breakout/breakdown (35) + spring/upthrust (15)
+ volume signature (10) + relative strength vs SPY (15) + RSI position (10)
+ VCP bonus (~9).

## Setup

```bash
pip install -r requirements.txt
python scanner.py
```

The scan takes ~10–15 minutes and auto-opens `wyckoff_scanner.html`.

### Flags

| Flag | Effect |
|------|--------|
| *(none)* | Run scan, build report, open in browser |
| `--no-open` | Run scan and build report without opening the browser |
| `--email` | Run scan and email setups scoring ≥ `min_score` (implies `--no-open`) |

## Daily email alerts

1. Copy the config template and fill it in:
   ```bash
   copy email_config.example.json email_config.json
   ```
2. Create a **Gmail App Password** (Google Account → Security → 2-Step Verification
   → App passwords) and paste it into `email_config.json` as `app_password`.
   Set `sender`, `recipient`, and `min_score` (default `80`).
3. Test it:
   ```bash
   python scanner.py --email
   ```
4. Schedule it for 6 PM daily (Windows):
   ```powershell
   powershell -ExecutionPolicy Bypass -File setup_schedule.ps1
   ```

`email_config.json` is gitignored so your app password is never committed. You can
instead supply credentials via the `WYCKOFF_SMTP_SENDER`, `WYCKOFF_SMTP_PASSWORD`,
and `WYCKOFF_SMTP_RECIPIENT` environment variables.

## Data sources

Ticker lists come from Wikipedia (S&P 500 / Nasdaq 100 / S&P 600). Price data is
from Yahoo Finance via `yfinance`. The iShares Russell 2000 holdings CSV is now
bot-blocked, so **S&P 600 SmallCap** is used as the small-cap universe.

## Disclaimer

This is an **end-of-day screening tool**, not investment advice. Signals are
candidates for further analysis — always confirm on a chart before trading.
