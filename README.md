# 🍁 Maple Zones

A free, phone-friendly Canadian stock/ETF/CDR scanner.

## What it does

- Uses free Yahoo Finance market data through `yfinance`
- Scans a starter list of Canadian ETFs, TSX stocks and Canadian-listed CDRs
- Estimates recent daily demand and supply zones
- Scores each ticker using zone distance, EMA trend alignment and RSI
- Refreshes automatically on weekdays using GitHub Actions
- Runs as a static Progressive Web App, so it can be added to a phone home screen

## Important

The scanner is a heuristic research tool, not a recommendation engine and not a replacement for the course-based trading algorithm. Market data may be delayed, missing or adjusted by the upstream provider.

## First setup

1. Run **Actions → Refresh market scan → Run workflow** once.
2. In **Settings → Pages**, choose **GitHub Actions** as the source.
3. Run **Actions → Deploy Maple Zones → Run workflow**.
4. Open the Pages URL on your phone and use **Add to Home screen**.

The repository must be on a GitHub plan/configuration that supports Pages for its visibility. If Pages is unavailable while this repo is private, making the repository public is the simplest no-cost path.

## Custom watchlist

Edit `watchlist.json`. Yahoo Finance symbols are used, e.g. `VFV.TO` and `WMT.NE`.
