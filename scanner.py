import json, os, time, math
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import yfinance as yf

ROOT=os.path.dirname(__file__)
with open(os.path.join(ROOT,"watchlist.json"),encoding="utf-8") as f:
    WATCH=json.load(f)

def json_safe(v):
    """Convert NumPy/non-finite values into strict JSON-safe values for browsers."""
    if isinstance(v, dict):
        return {k: json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [json_safe(x) for x in v]
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (np.floating, float)):
        x=float(v)
        return x if math.isfinite(x) else None
    return v

def rsi(close,period=14):
    d=close.diff()
    up=d.clip(lower=0).rolling(period).mean()
    dn=(-d.clip(upper=0)).rolling(period).mean()
    rs=up/dn.replace(0,np.nan)
    return 100-(100/(1+rs))

def atr(df,period=14):
    pc=df["Close"].shift(1)
    tr=pd.concat([
        (df["High"]-df["Low"]).abs(),
        (df["High"]-pc).abs(),
        (df["Low"]-pc).abs()
    ],axis=1).max(axis=1)
    return tr.rolling(period).mean()

def trend_state(close, fast=20, slow=50):
    if len(close)<slow: return "mixed"
    ef=float(close.ewm(span=fast,adjust=False).mean().iloc[-1])
    es=float(close.ewm(span=slow,adjust=False).mean().iloc[-1])
    p=float(close.iloc[-1])
    return "bullish" if p>ef>es else "bearish" if p<ef<es else "mixed"

def weekly_trend(df):
    w=df.resample("W-FRI").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna()
    return trend_state(w["Close"].astype(float),10,20)

def zone_retests_and_validity(df, zone, kind):
    start=zone["i"]+4
    retests=0
    was_outside=True
    valid=True
    for j in range(start,len(df)):
        lo=float(df["Low"].iloc[j]); hi=float(df["High"].iloc[j]); cl=float(df["Close"].iloc[j])
        overlaps = hi>=zone["low"] and lo<=zone["high"]
        if kind=="demand" and cl<zone["low"]:
            valid=False; break
        if kind=="supply" and cl>zone["high"]:
            valid=False; break
        if overlaps and was_outside:
            retests+=1
            was_outside=False
        elif not overlaps:
            was_outside=True
    return retests, valid

def find_zones(df):
    """
    Stricter daily supply/demand zones.

    A candidate must:
      1) form at a local extreme,
      2) leave with meaningful displacement,
      3) be reasonably sized relative to ATR, and
      4) break a prior swing extreme after departure.

    This avoids treating oversized event candles or ordinary reactions as zones.
    """
    a=atr(df)
    demand=[]; supply=[]
    for i in range(6,len(df)-4):
        lo=float(df["Low"].iloc[i]); hi=float(df["High"].iloc[i])
        op=float(df["Open"].iloc[i]); cl=float(df["Close"].iloc[i])
        av=float(a.iloc[i]) if pd.notna(a.iloc[i]) else 0
        if av<=0: continue

        local_low=float(df["Low"].iloc[i-2:i+3].min())
        local_high=float(df["High"].iloc[i-2:i+3].max())
        prior_high=float(df["High"].iloc[i-5:i].max())
        prior_low=float(df["Low"].iloc[i-5:i].min())
        future_high=float(df["High"].iloc[i+1:i+4].max())
        future_low=float(df["Low"].iloc[i+1:i+4].min())
        up_move=future_high-cl
        dn_move=cl-future_low

        demand_high=max(op,cl)
        supply_low=min(op,cl)
        demand_width=max(0.0,demand_high-lo)
        supply_width=max(0.0,hi-supply_low)
        formed_at=pd.Timestamp(df.index[i]).date().isoformat()

        demand_break = future_high > prior_high + 0.05*av
        supply_break = future_low < prior_low - 0.05*av
        demand_size_ok = demand_width <= 1.50*av
        supply_size_ok = supply_width <= 1.50*av

        if lo<=local_low and up_move>=1.2*av and demand_break and demand_size_ok:
            z={
                "low":lo,"high":demand_high,"i":i,
                "departure_atr":round(up_move/av,2),
                "width_atr":round(demand_width/av,2),
                "structure_break":True,
                "formed_at":formed_at
            }
            z["retests"],z["valid"]=zone_retests_and_validity(df,z,"demand")
            if z["valid"]: demand.append(z)

        if hi>=local_high and dn_move>=1.2*av and supply_break and supply_size_ok:
            z={
                "low":supply_low,"high":hi,"i":i,
                "departure_atr":round(dn_move/av,2),
                "width_atr":round(supply_width/av,2),
                "structure_break":True,
                "formed_at":formed_at
            }
            z["retests"],z["valid"]=zone_retests_and_validity(df,z,"supply")
            if z["valid"]: supply.append(z)
    return demand,supply

def zone_age(df,z):
    if not z:return None
    return max(0,len(df)-1-int(z["i"]))

def nearest_zone(price,zones,kind):
    valid=[]
    for z in zones[-40:]:
        if kind=="demand" and price>=z["low"]:
            valid.append(z)
        elif kind=="supply" and price<=z["high"]:
            valid.append(z)
    if not valid:return None,None
    if kind=="demand":
        z=min(valid,key=lambda z:abs(price-z["high"]))
        dist=0.0 if z["low"]<=price<=z["high"] else (price-z["high"])/price*100
    else:
        z=min(valid,key=lambda z:abs(z["low"]-price))
        dist=0.0 if z["low"]<=price<=z["high"] else (z["low"]-price)/price*100
    return z,max(0,float(dist))

def freshness_points(z):
    if not z:return 0
    r=int(z.get("retests",0))
    if r==0:return 12
    if r==1:return 8
    if r==2:return 3
    return -4

def zone_quality(z, age_bars=0):
    if not z:return -999
    return (
        float(z.get("departure_atr",0))*10
        - int(z.get("retests",0))*5
        - max(0,age_bars)*0.03
        - max(0,float(z.get("width_atr",0))-0.8)*2
    )

def resolve_opposing_overlap(df, dz, dd, sz, sd):
    """Do not present materially overlapping demand and supply as simultaneous clean zones."""
    if not dz or not sz:
        return dz,dd,sz,sd
    overlap=max(0.0,min(float(dz["high"]),float(sz["high"]))-max(float(dz["low"]),float(sz["low"])))
    dw=max(1e-9,float(dz["high"])-float(dz["low"]))
    sw=max(1e-9,float(sz["high"])-float(sz["low"]))
    overlap_fraction=overlap/min(dw,sw)
    if overlap_fraction < 0.25:
        return dz,dd,sz,sd

    dq=zone_quality(dz,zone_age(df,dz))
    sq=zone_quality(sz,zone_age(df,sz))
    if dq>=sq:
        return dz,dd,None,None
    return None,None,sz,sd

def demand_bounce_state(df, zone, lookback=7):
    """Detect a bullish reversal after price trades into a valid demand zone."""
    if not zone or len(df)<3:
        return {"status":"none","bars_since_touch":None,"bounce_pct":None,"bounce_score":0.0}

    start=max(int(zone["i"])+4, len(df)-lookback)
    touch_i=None
    touch_low=None
    for j in range(start,len(df)):
        lo=float(df["Low"].iloc[j]); hi=float(df["High"].iloc[j])
        if hi>=zone["low"] and lo<=zone["high"]:
            touch_i=j
            touch_low=lo if touch_low is None else min(touch_low,lo)

    if touch_i is None:
        return {"status":"none","bars_since_touch":None,"bounce_pct":None,"bounce_score":0.0}

    bars_since=(len(df)-1)-touch_i
    price=float(df["Close"].iloc[-1])
    prev=float(df["Close"].iloc[-2])
    op=float(df["Open"].iloc[-1])
    base=max(float(zone["low"]), min(float(zone["high"]), touch_low if touch_low is not None else float(zone["high"])))
    bounce_pct=((price-base)/base*100) if base>0 else 0.0
    above_zone=price>float(zone["high"])
    rising=price>prev
    bullish_candle=price>op

    status="none"
    if bars_since<=5 and above_zone and bounce_pct>=0.75 and rising and bullish_candle:
        status="confirmed"
    elif bars_since<=3 and price>=float(zone["low"]) and bounce_pct>=0.25 and (rising or bullish_candle):
        status="early"

    score=0.0
    if status!="none":
        score=60.0
        score+=max(0,15-bars_since*3)
        score+=min(15,max(0,bounce_pct*4))
        if rising: score+=5
        if bullish_candle: score+=5
        if status=="confirmed": score+=10
    return {
        "status":status,
        "bars_since_touch":int(bars_since),
        "bounce_pct":round(float(bounce_pct),2),
        "bounce_score":round(min(100,score),1)
    }

def score_row(df):
    close=df["Close"].astype(float)
    price=float(close.iloc[-1])
    rv=float(rsi(close).iloc[-1])
    dtrend=trend_state(close)
    wtrend=weekly_trend(df)
    demand,supply=find_zones(df)
    dz,dd=nearest_zone(price,demand,"demand")
    sz,sd=nearest_zone(price,supply,"supply")
    dz,dd,sz,sd=resolve_opposing_overlap(df,dz,dd,sz,sd)
    bounce=demand_bounce_state(df,dz)

    score=35.0
    reasons=[]

    if dd is not None:
        score+=max(0,28-dd*6)
        if dd<=1: reasons.append("Price is sitting at/very near demand")
        elif dd<=3: reasons.append("Price is within 3% of demand")
    else:
        reasons.append("No valid nearby demand zone found")

    if dz:
        score+=freshness_points(dz)
        score+=min(10,max(0,(float(dz.get("departure_atr",1.2))-1.2)*8))
        if dz.get("retests",0)==0: reasons.append("Demand zone is fresh (untested)")
        elif dz.get("retests",0)==1: reasons.append("Demand has only one retest")
        if dz.get("departure_atr",0)>=1.8: reasons.append("Strong departure from demand")

    if sd is not None:
        if sd<=1:
            score-=18; reasons.append("Very close to opposing supply")
        elif sd<=3:
            score-=10; reasons.append("Limited room before supply")
        elif sd>=7:
            score+=6; reasons.append("Good room before opposing supply")

    if dtrend=="bullish":
        score+=10; reasons.append("Daily trend is bullish")
    elif dtrend=="bearish":
        score-=10; reasons.append("Daily trend is bearish")

    if wtrend=="bullish":
        score+=10; reasons.append("Weekly trend agrees bullish")
    elif wtrend=="bearish":
        score-=8; reasons.append("Weekly trend is bearish")

    if 45<=rv<=65:
        score+=7; reasons.append("RSI is constructive, not stretched")
    elif rv>75:
        score-=7; reasons.append("RSI is stretched")
    elif rv<35:
        score+=2

    score=max(0,min(100,score))
    return {
      "price":round(price,4),"score":round(score,1),"rsi":round(rv,1),
      "trend":dtrend,"weekly_trend":wtrend,
      "demand_distance_pct":None if dd is None else round(dd,2),
      "supply_distance_pct":None if sd is None else round(sd,2),
      "demand_zone":dz,"supply_zone":sz,
      "demand_retests":None if not dz else int(dz.get("retests",0)),
      "demand_age_bars":zone_age(df,dz),
      "departure_atr":None if not dz else round(float(dz.get("departure_atr",0)),2),
      "demand_bounce":bounce["status"],
      "bounce_bars_since_touch":bounce["bars_since_touch"],
      "bounce_pct":bounce["bounce_pct"],
      "bounce_score":bounce["bounce_score"],
      "reasons":reasons[:5]
    }

def extract_symbol_frame(batch, sym):
    if batch is None or batch.empty:
        return None
    try:
        if isinstance(batch.columns,pd.MultiIndex):
            lvl0=set(batch.columns.get_level_values(0))
            lvl1=set(batch.columns.get_level_values(1))
            if sym in lvl0:
                df=batch[sym].copy()
            elif sym in lvl1:
                df=batch.xs(sym,axis=1,level=1).copy()
            else:
                return None
        else:
            df=batch.copy()
        need=["Open","High","Low","Close","Volume"]
        if not all(c in df.columns for c in need):
            return None
        df=df[need].dropna(subset=["Open","High","Low","Close"])
        return df if len(df)>=120 else None
    except Exception:
        return None

def main():
    results=[]
    symbols=[x["symbol"] for x in WATCH]
    items={x["symbol"]:x for x in WATCH}
    chunk_size=50
    downloaded=0

    for start in range(0,len(symbols),chunk_size):
        chunk=symbols[start:start+chunk_size]
        print(f"batch {start+1}-{min(start+len(chunk),len(symbols))} of {len(symbols)}")
        try:
            batch=yf.download(
                chunk,period="18mo",interval="1d",auto_adjust=False,
                progress=False,threads=True,group_by="ticker"
            )
        except Exception as e:
            print("BATCH ERROR",str(e)[:160])
            batch=None

        for sym in chunk:
            try:
                df=extract_symbol_frame(batch,sym)
                if df is None:
                    print("SKIP",sym,"no usable history")
                    continue
                row={**items[sym],**score_row(df)}
                results.append(row)
                downloaded+=1
                print(sym,row["score"])
            except Exception as e:
                print("SKIP",sym,str(e)[:120])

        time.sleep(0.1)

    results.sort(key=lambda x:x["score"],reverse=True)
    out={
      "generated_at":datetime.now(timezone.utc).isoformat(),
      "method":"daily supply-demand heuristic v3.3 dated structure-validated zones",
      "universe_size":len(WATCH),
      "symbols_scored":downloaded,
      "results":results
    }
    os.makedirs(os.path.join(ROOT,"data"),exist_ok=True)
    with open(os.path.join(ROOT,"data","scan.json"),"w",encoding="utf-8") as f:
        json.dump(json_safe(out),f,indent=2,allow_nan=False)
    print("wrote",len(results),"of",len(WATCH),"symbols")

if __name__=="__main__":
    main()
