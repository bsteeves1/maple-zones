import json, math, os
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
    tr=pd.concat([(df["High"]-df["Low"]).abs(),(df["High"]-pc).abs(),(df["Low"]-pc).abs()],axis=1).max(axis=1)
    return tr.rolling(period).mean()

def find_zones(df):
    a=atr(df)
    demand=[]; supply=[]
    for i in range(3,len(df)-4):
        lo=float(df["Low"].iloc[i]); hi=float(df["High"].iloc[i]); op=float(df["Open"].iloc[i]); cl=float(df["Close"].iloc[i])
        av=float(a.iloc[i]) if pd.notna(a.iloc[i]) else 0
        if av<=0: continue
        is_low=lo==float(df["Low"].iloc[i-2:i+3].min())
        is_high=hi==float(df["High"].iloc[i-2:i+3].max())
        up_move=float(df["High"].iloc[i+1:i+4].max())-cl
        dn_move=cl-float(df["Low"].iloc[i+1:i+4].min())
        if is_low and up_move>=1.2*av:
            demand.append({"low":lo,"high":max(op,cl),"i":i})
        if is_high and dn_move>=1.2*av:
            supply.append({"low":min(op,cl),"high":hi,"i":i})
    return demand,supply

def nearest_valid(price,zones,kind):
    valid=[]
    for z in zones[-30:]:
        if kind=="demand" and z["low"]<=price:
            valid.append(z)
        elif kind=="supply" and z["high"]>=price:
            valid.append(z)
    if not valid:return None,None
    if kind=="demand":
        z=min(valid,key=lambda z:abs(price-z["high"]))
        dist=(price-z["high"])/price*100
    else:
        z=min(valid,key=lambda z:abs(z["low"]-price))
        dist=(z["low"]-price)/price*100
    return z,max(0,float(dist))

def score_row(df):
    close=df["Close"].astype(float)
    price=float(close.iloc[-1])
    ema20=float(close.ewm(span=20,adjust=False).mean().iloc[-1])
    ema50=float(close.ewm(span=50,adjust=False).mean().iloc[-1])
    rv=float(rsi(close).iloc[-1])
    demand,supply=find_zones(df)
    dz,dd=nearest_valid(price,demand,"demand")
    sz,sd=nearest_valid(price,supply,"supply")
    trend="bullish" if price>ema20>ema50 else "bearish" if price<ema20<ema50 else "mixed"

    score=45.0
    if dd is not None: score += max(0,25-dd*5)
    if sd is not None: score -= max(0,15-sd*4)
    if trend=="bullish": score+=18
    elif trend=="bearish": score-=12
    if 45<=rv<=65: score+=10
    elif rv>75: score-=6
    elif rv<35: score+=3
    score=max(0,min(100,score))
    return {
      "price":price,"score":round(score,1),"rsi":round(rv,1),"trend":trend,
      "demand_distance_pct":None if dd is None else round(dd,2),
      "supply_distance_pct":None if sd is None else round(sd,2),
      "demand_zone":dz,"supply_zone":sz
    }

def main():
    results=[]
    for item in WATCH:
        sym=item["symbol"]
        try:
            df=yf.download(sym,period="9mo",interval="1d",auto_adjust=False,progress=False,threads=False)
            if isinstance(df.columns,pd.MultiIndex): df.columns=df.columns.get_level_values(0)
            df=df.dropna()
            if len(df)<80: raise ValueError("not enough history")
            row={**item,**score_row(df)}
            results.append(row)
            print(sym,row["score"])
        except Exception as e:
            print("SKIP",sym,str(e)[:120])
    results.sort(key=lambda x:x["score"],reverse=True)
    out={"generated_at":datetime.now(timezone.utc).isoformat(),"method":"daily heuristic v1","results":results}
    os.makedirs(os.path.join(ROOT,"data"),exist_ok=True)
    with open(os.path.join(ROOT,"data","scan.json"),"w",encoding="utf-8") as f: json.dump(out,f,indent=2)
    print("wrote",len(results),"symbols")

if __name__=="__main__": main()