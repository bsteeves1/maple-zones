import json, os
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import yfinance as yf

ROOT=os.path.dirname(__file__)
with open(os.path.join(ROOT,"watchlist.json"),encoding="utf-8") as f:
    WATCH=json.load(f)

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
    a=atr(df)
    demand=[]; supply=[]
    for i in range(3,len(df)-4):
        lo=float(df["Low"].iloc[i]); hi=float(df["High"].iloc[i])
        op=float(df["Open"].iloc[i]); cl=float(df["Close"].iloc[i])
        av=float(a.iloc[i]) if pd.notna(a.iloc[i]) else 0
        if av<=0: continue

        local_low=float(df["Low"].iloc[i-2:i+3].min())
        local_high=float(df["High"].iloc[i-2:i+3].max())
        up_move=float(df["High"].iloc[i+1:i+4].max())-cl
        dn_move=cl-float(df["Low"].iloc[i+1:i+4].min())

        if lo<=local_low and up_move>=1.2*av:
            z={"low":lo,"high":max(op,cl),"i":i,"departure_atr":round(up_move/av,2)}
            z["retests"],z["valid"]=zone_retests_and_validity(df,z,"demand")
            if z["valid"]: demand.append(z)
        if hi>=local_high and dn_move>=1.2*av:
            z={"low":min(op,cl),"high":hi,"i":i,"departure_atr":round(dn_move/av,2)}
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

def score_row(df):
    close=df["Close"].astype(float)
    price=float(close.iloc[-1])
    rv=float(rsi(close).iloc[-1])
    dtrend=trend_state(close)
    wtrend=weekly_trend(df)
    demand,supply=find_zones(df)
    dz,dd=nearest_zone(price,demand,"demand")
    sz,sd=nearest_zone(price,supply,"supply")

    score=35.0
    reasons=[]

    if dd is not None:
        near=max(0,28-dd*6)
        score+=near
        if dd<=1: reasons.append("Price is sitting at/very near demand")
        elif dd<=3: reasons.append("Price is within 3% of demand")
    else:
        reasons.append("No valid nearby demand zone found")

    if dz:
        fp=freshness_points(dz); score+=fp
        dep=min(10,max(0,(float(dz.get("departure_atr",1.2))-1.2)*8))
        score+=dep
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
      "price":round(price,4),
      "score":round(score,1),
      "rsi":round(rv,1),
      "trend":dtrend,
      "weekly_trend":wtrend,
      "demand_distance_pct":None if dd is None else round(dd,2),
      "supply_distance_pct":None if sd is None else round(sd,2),
      "demand_zone":dz,
      "supply_zone":sz,
      "demand_retests":None if not dz else int(dz.get("retests",0)),
      "demand_age_bars":zone_age(df,dz),
      "departure_atr":None if not dz else round(float(dz.get("departure_atr",0)),2),
      "reasons":reasons[:5]
    }

def main():
    results=[]
    for item in WATCH:
        sym=item["symbol"]
        try:
            df=yf.download(sym,period="18mo",interval="1d",auto_adjust=False,progress=False,threads=False)
            if isinstance(df.columns,pd.MultiIndex): df.columns=df.columns.get_level_values(0)
            df=df.dropna()
            if len(df)<120: raise ValueError("not enough history")
            row={**item,**score_row(df)}
            results.append(row)
            print(sym,row["score"])
        except Exception as e:
            print("SKIP",sym,str(e)[:120])
    results.sort(key=lambda x:x["score"],reverse=True)
    out={
      "generated_at":datetime.now(timezone.utc).isoformat(),
      "method":"daily supply-demand heuristic v2",
      "results":results
    }
    os.makedirs(os.path.join(ROOT,"data"),exist_ok=True)
    with open(os.path.join(ROOT,"data","scan.json"),"w",encoding="utf-8") as f:
        json.dump(out,f,indent=2)
    print("wrote",len(results),"symbols")

if __name__=="__main__":
    main()
