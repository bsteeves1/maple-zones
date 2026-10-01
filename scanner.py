"""Daily zone candidates, not a certified course model or a live quote feed.

V3.4: explicit close-based invalidation with wick-breach warnings; separate
visit/day counts; causal local-pivot breaks; provisional current-session bars.
"""
import json
import math
import os
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = os.path.dirname(__file__)
RULES_VERSION = "3.4"
METHOD = "daily local-pivot zone candidates v3.4; close rule + breach warnings"


def json_safe(value):
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    return value


def rsi(close, period=14):
    d = close.diff()
    up = d.clip(lower=0).rolling(period).mean()
    down = (-d.clip(upper=0)).rolling(period).mean()
    result = 100 - 100 / (1 + up / down.replace(0, np.nan))
    result = result.mask((down == 0) & (up > 0), 100)
    return result.mask((down == 0) & (up == 0), 50)


def atr(df, period=14):
    pc = df["Close"].shift(1)
    tr = pd.concat([(df.High-df.Low).abs(), (df.High-pc).abs(),
                    (df.Low-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def trend_state(close, fast=20, slow=50):
    if len(close) < slow:
        return "mixed"
    ef = float(close.ewm(span=fast, adjust=False).mean().iloc[-1])
    es = float(close.ewm(span=slow, adjust=False).mean().iloc[-1])
    p = float(close.iloc[-1])
    return "bullish" if p > ef > es else "bearish" if p < ef < es else "mixed"


def weekly_trend(df):
    w = df.resample("W-FRI").agg({"Open":"first", "High":"max", "Low":"min",
                                  "Close":"last", "Volume":"sum"}).dropna()
    return trend_state(w.Close.astype(float), 10, 20)


def session_date(value):
    # Preserve the exchange's date; do not convert a date-only candle to UTC.
    return pd.Timestamp(value).date().isoformat()


def completed_index(df, now=None):
    """Conservative: today's daily candle is provisional until the next date.

    Yahoo daily bars do not provide an exchange-finalized flag. No time-of-day
    guess (holidays, early closes, delayed bars) is used as confirmation.
    """
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("America/New_York")).date()
    done = [i for i, t in enumerate(df.index) if pd.Timestamp(t).date() < today]
    return done[-1] if done else -1


def confirmed_pivots(df, last_complete, left=2, right=2):
    """Local pivots become knowable only after right-hand bars complete.

    Equal-high/low plateaus use the last equal extreme. These are local pivots,
    NOT a complete protected-HL/LH or discretionary market-structure model.
    """
    high, low = df.High.to_numpy(float), df.Low.to_numpy(float)
    out = {"high": [], "low": []}
    for i in range(left, last_complete-right+1):
        for kind, values in (("high", high), ("low", low)):
            before, after = values[i-left:i], values[i+1:i+right+1]
            ok = (values[i] >= before.max() and values[i] > after.max()) if kind == "high" else (
                  values[i] <= before.min() and values[i] < after.min())
            if ok:
                out[kind].append({"i": i, "known_i": i+right,
                                  "price": float(values[i]), "date": session_date(df.index[i])})
    return out


def zone_lifecycle(df, zone, kind, last_complete):
    """A retest is a separate daily-bar visit; touch_bars counts every day.

    Count touches only after departure. Check distal-boundary violations from
    the first post-origin bar, including the departure/confirmation window.
    A completed close beyond the boundary permanently invalidates the zone.
    Any high/low breach is retained as a warning even after price recovers.
    """
    if kind not in ("demand", "supply"):
        raise ValueError("Unknown zone kind")
    high, low, close = (df[c].to_numpy(float) for c in ("High", "Low", "Close"))
    visits = days = consecutive = longest = breaches = 0
    was_touching = False
    first_breach = last_breach = last_touch = None
    extreme = None
    valid = True
    for j in range(int(zone["i"])+1, len(df)):
        breach = low[j] < zone["low"] if kind == "demand" else high[j] > zone["high"]
        if breach:
            breaches += 1
            first_breach = first_breach or session_date(df.index[j])
            last_breach = session_date(df.index[j])
            value = low[j] if kind == "demand" else high[j]
            extreme = float(value if extreme is None else (
                min(extreme, value) if kind == "demand" else max(extreme, value)))
        closed_beyond = close[j] < zone["low"] if kind == "demand" else close[j] > zone["high"]
        if closed_beyond and j <= last_complete:
            valid = False
            break
        if j <= zone["departure_i"]:
            continue
        touching = high[j] >= zone["low"] and low[j] <= zone["high"]
        if touching:
            visits += int(not was_touching)
            days += 1
            consecutive += 1
            longest = max(longest, consecutive)
            last_touch = session_date(df.index[j])
        else:
            consecutive = 0
        was_touching = touching
    return {"valid": valid, "retests": visits, "touch_bars": days,
            "max_consecutive_touch_bars": longest, "last_touch_at": last_touch,
            "wick_breached": breaches > 0, "breach_bars": breaches,
            "first_breach_at": first_breach, "last_breach_at": last_breach,
            "breach_extreme": extreme, "invalidation_rule": "completed daily close",
            "status": "close_invalidated" if not valid else "boundary_breached" if breaches else "intact"}


def find_zones(df, last_complete=None, pivots=None):
    last_complete = completed_index(df) if last_complete is None else last_complete
    pivots = confirmed_pivots(df, last_complete) if pivots is None else pivots
    a = atr(df).to_numpy(float)
    op, hi, lo, cl = (df[c].to_numpy(float) for c in ("Open", "High", "Low", "Close"))
    zones = {"demand": [], "supply": []}
    origin_sets = {"demand": {p["i"] for p in pivots["low"]},
                   "supply": {p["i"] for p in pivots["high"]}}
    for i in range(15, last_complete-1):
        av = a[i-1]  # Event candles must not inflate their own width allowance.
        if not np.isfinite(av) or av <= 0 or hi[i]-lo[i] > 2*av:
            continue
        for kind in ("demand", "supply"):
            if i not in origin_sets[kind]:
                continue
            demand = kind == "demand"
            lower, upper = (lo[i], max(op[i], cl[i])) if demand else (min(op[i], cl[i]), hi[i])
            if not 0 < upper-lower <= 1.5*av:
                continue
            prior = [p for p in pivots["high" if demand else "low"] if p["known_i"] <= i]
            if not prior:
                continue
            target = prior[-1]
            old_closes = cl[target["known_i"]:i+1]
            if np.any(old_closes > target["price"] if demand else old_closes < target["price"]):
                continue  # Do not reuse a pivot already broken before this base.
            departure_i = break_i = None
            move = 0.0
            for j in range(i+1, min(i+3, last_complete)+1):
                outside = cl[j] > upper if demand else cl[j] < lower
                if outside and departure_i is None:
                    departure_i = j
                move = max(move, (cl[j]-upper if demand else lower-cl[j])/av)
                broke = cl[j] > target["price"]+0.05*av if demand else cl[j] < target["price"]-0.05*av
                if outside and broke and move >= 1.2:
                    break_i = j
                    break
            if break_i is None:
                continue
            z = {"low": float(lower), "high": float(upper), "i": i,
                 "formed_at": session_date(df.index[i]), "departure_i": departure_i,
                 "confirmed_i": max(i+2, break_i),
                 "confirmed_at": session_date(df.index[max(i+2, break_i)]),
                 "departure_atr": round(move, 2), "width_atr": round((upper-lower)/av, 2),
                 "structure_break": True, "structure_method": "completed close beyond confirmed local pivot",
                 "broken_pivot_price": target["price"], "broken_pivot_at": target["date"]}
            z.update(zone_lifecycle(df, z, kind, last_complete))
            if z["valid"]:
                zones[kind].append(z)
    return zones["demand"], zones["supply"]


def nearest_zone(price, zones, kind):
    possible = []
    for z in zones:
        if not z.get("valid", True):
            continue
        if (kind == "demand" and price < z["low"]) or (kind == "supply" and price > z["high"]):
            continue
        distance = max(0.0, price-z["high"] if kind == "demand" else z["low"]-price)
        possible.append((distance, -z["i"], z))
    if not possible:
        return None, None
    distance, _, z = min(possible, key=lambda item: item[:2])
    return z, float(distance/price*100)


def zones_overlap(dz, sz):
    # Keep opposing supply visible rather than delete a risk from the screen.
    return bool(dz and sz and min(dz["high"], sz["high"]) >= max(dz["low"], sz["low"]))


def demand_bounce_state(df, zone, last_complete=None, pivots=None, lookback=7):
    result = {"status": "none", "bars_since_touch": None, "bounce_pct": None,
              "bounce_score": 0.0, "swing_high": None, "swing_high_at": None,
              "swing_break_at": None, "detail": "No recent qualifying demand reaction"}
    if not zone or len(df) < 3:
        return result
    if zone.get("wick_breached") or not zone.get("valid", True):
        result["detail"] = "Demand boundary breached; excluded from clean bounce signals"
        return result
    last_complete = completed_index(df) if last_complete is None else last_complete
    pivots = confirmed_pivots(df, last_complete) if pivots is None else pivots
    hi, lo, cl, op = (df[c].to_numpy(float) for c in ("High", "Low", "Close", "Open"))
    visits = []
    touching = False
    for j in range(zone["departure_i"]+1, len(df)):
        hit = hi[j] >= zone["low"] and lo[j] <= zone["high"]
        if hit and not touching:
            visits.append([])
        if hit:
            visits[-1].append(j)
        touching = hit
    if not visits:
        return result
    visit = visits[-1]
    first_touch, last_touch = visit[0], visit[-1]
    since = len(df)-1-last_touch
    if since >= lookback:
        return result
    base = float(min(lo[j] for j in visit))
    bounce_pct = (cl[-1]-base)/base*100 if base > 0 else 0.0
    result.update(bars_since_touch=since, bounce_pct=round(float(bounce_pct), 2))
    if cl[-1] > zone["high"] and bounce_pct >= 0.25 and (cl[-1] > cl[-2] or cl[-1] > op[-1]):
        result.update(status="early", bounce_score=60.0,
                      detail="Early bounce only; no completed lower-high break")
    known = [p for p in pivots["high"] if p["known_i"] <= first_touch]
    if len(known) < 2 or known[-1]["price"] >= known[-2]["price"]:
        return result  # A bounce in an uptrend is not a reversal of a lower high.
    target = known[-1]
    result.update(swing_high=target["price"], swing_high_at=target["date"])
    if np.any(cl[target["known_i"]:first_touch+1] > target["price"]):
        return result
    av = float(atr(df).iloc[max(0, first_touch-1)])
    if not np.isfinite(av) or av <= 0:
        return result
    threshold = target["price"]+0.05*av
    for j in range(first_touch+1, last_complete+1):
        if cl[j] > max(threshold, zone["high"]) and cl[j-1] <= threshold:
            # Do not keep confirmation after a recross back under the pivot.
            if np.all(cl[j:] > target["price"]) and cl[-1] > zone["high"]:
                result.update(status="swing_break", bounce_score=85.0,
                              swing_break_at=session_date(df.index[j]),
                              detail="Completed prior-session close broke a known local lower high")
    return result


def score_row(df, now=None):
    last_complete = completed_index(df, now)
    close = df.Close.astype(float)
    price = float(close.iloc[-1])
    if not np.isfinite(price) or price <= 0:
        raise ValueError("Invalid latest price")
    rv = float(rsi(close).iloc[-1])
    dtrend, wtrend = trend_state(close), weekly_trend(df)
    pivots = confirmed_pivots(df, last_complete)
    demand, supply = find_zones(df, last_complete, pivots)
    dz, dd = nearest_zone(price, demand, "demand")
    sz, sd = nearest_zone(price, supply, "supply")
    overlap = zones_overlap(dz, sz)
    bounce = demand_bounce_state(df, dz, last_complete, pivots)
    warnings, reasons = [], []
    score = 35.0
    if dz:
        score += max(0, 28-dd*6)
        visits, days = dz["retests"], dz["touch_bars"]
        score += 12 if visits == 0 else 8 if visits == 1 else 3 if visits == 2 else -4
        score -= min(12, max(0, days-visits)*2)
        score += min(10, max(0, (dz["departure_atr"]-1.2)*8))
        reasons.append("Demand candidate passed a completed local-pivot close break")
        reasons.append(f"{visits} separate visits; {days} daily candles touched demand")
        if dd <= 1:
            reasons.append("Price at or within 1% above demand")
    else:
        warnings.append("No qualifying active demand candidate")
    for label, z in (("Demand", dz), ("Supply", sz)):
        if z and z["wick_breached"]:
            warnings.append(f"{label} boundary traded through on {z['first_breach_at']}; retained only under the close rule")
    if overlap:
        warnings.append("Demand and supply overlap; not a clean setup")
        bounce.update(status="none", bounce_score=0.0, detail="Opposing zones overlap")
    if sd is None:
        warnings.append("No qualifying supply candidate; upside room is unknown")
    elif sd <= 1:
        score -= 18
        warnings.append("At or very close to opposing supply")
    elif sd <= 3:
        score -= 10
        warnings.append("Limited room before opposing supply")
    elif sd >= 7:
        score += 6
        reasons.append("At least 7% to the displayed supply candidate")
    score += 10 if dtrend == "bullish" else -10 if dtrend == "bearish" else 0
    score += 10 if wtrend == "bullish" else -8 if wtrend == "bearish" else 0
    if np.isfinite(rv):
        score += 7 if 45 <= rv <= 65 else -7 if rv > 75 else 2 if rv < 35 else 0
    if not dz:
        score = min(score, 45)
    if dz and dz["wick_breached"]:
        score = min(score, 55)
    if overlap:
        score = min(score, 50)
    if sd is not None and sd <= 1:
        score = min(score, 55)
    if sd is None:
        score = min(score, 74)
    return json_safe({
        "rules_version": RULES_VERSION, "price": round(price, 4),
        "last_candle_date": session_date(df.index[-1]),
        "validated_through": session_date(df.index[last_complete]) if last_complete >= 0 else None,
        "bar_is_provisional": last_complete < len(df)-1,
        "score": round(max(0, min(100, score)), 1), "rsi": round(rv, 1),
        "trend": dtrend, "weekly_trend": wtrend, "demand_zone": dz, "supply_zone": sz,
        "demand_distance_pct": None if dd is None else round(dd, 2),
        "supply_distance_pct": None if sd is None else round(sd, 2),
        "demand_retests": None if dz is None else dz["retests"],
        "demand_age_bars": None if dz is None else len(df)-1-dz["i"],
        "departure_atr": None if dz is None else dz["departure_atr"],
        "overlap_conflict": overlap, "demand_bounce": bounce["status"],
        "bounce_bars_since_touch": bounce["bars_since_touch"], "bounce_pct": bounce["bounce_pct"],
        "bounce_score": bounce["bounce_score"], "bounce_detail": bounce["detail"],
        "bounce_swing_high": bounce["swing_high"], "bounce_swing_high_at": bounce["swing_high_at"],
        "bounce_break_at": bounce["swing_break_at"], "warnings": warnings, "reasons": reasons})


def extract_symbol_frame(batch, sym):
    if batch is None or batch.empty:
        return None
    try:
        if isinstance(batch.columns, pd.MultiIndex):
            if sym in batch.columns.get_level_values(0):
                df = batch[sym].copy()
            elif sym in batch.columns.get_level_values(1):
                df = batch.xs(sym, axis=1, level=1).copy()
            else:
                return None
        else:
            df = batch.copy()
        need = ["Open", "High", "Low", "Close", "Volume"]
        df = df[need].replace([np.inf, -np.inf], np.nan).dropna(subset=need[:4])
        df = df.loc[~df.index.duplicated(keep="last")].sort_index()
        valid = (df.Low > 0) & (df.High >= df[["Open", "Close", "Low"]].max(axis=1)) & (
            df.Low <= df[["Open", "Close"]].min(axis=1))
        df = df.loc[valid]
        return df if len(df) >= 120 else None
    except (KeyError, ValueError, TypeError):
        return None


def main():
    import yfinance as yf  # Keep rule tests network-independent.
    with open(os.path.join(ROOT, "watchlist.json"), encoding="utf-8") as f:
        watch = json.load(f)
    items = {x["symbol"]: x for x in watch}
    symbols = list(items)
    results = []
    for start in range(0, len(symbols), 50):
        chunk = symbols[start:start+50]
        print(f"Batch {start+1}-{start+len(chunk)} of {len(symbols)}", flush=True)
        try:
            batch = yf.download(chunk, period="18mo", interval="1d", auto_adjust=False,
                                progress=False, threads=True, group_by="ticker", timeout=15)
        except Exception as exc:
            print("BATCH ERROR", str(exc)[:160], flush=True)
            batch = None
        for sym in chunk:
            try:
                df = extract_symbol_frame(batch, sym)
                if df is None:
                    print("SKIP", sym, "no usable history", flush=True)
                    continue
                row = {**items[sym], **score_row(df)}
                results.append(row)
                print(sym, row["score"], row["demand_bounce"], flush=True)
            except Exception as exc:
                print("SKIP", sym, str(exc)[:120], flush=True)
        time.sleep(0.1)
    if not results:
        raise RuntimeError("No symbols scored; refusing to overwrite good scan data")
    results.sort(key=lambda r: r["score"], reverse=True)
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "method": METHOD,
           "rules_version": RULES_VERSION, "universe_size": len(watch),
           "symbols_scored": len(results), "results": results}
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    path = os.path.join(ROOT, "data", "scan.json")
    with open(path+".tmp", "w", encoding="utf-8") as f:
        json.dump(json_safe(out), f, indent=2, allow_nan=False)
    os.replace(path+".tmp", path)
    print("Wrote", len(results), "of", len(watch), "symbols", flush=True)


if __name__ == "__main__":
    main()
