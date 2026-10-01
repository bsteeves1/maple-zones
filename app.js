let rows=[];let activeFilter="all";
const list=document.getElementById("list"),tpl=document.getElementById("rowTemplate"),search=document.getElementById("search"),count=document.getElementById("count"),empty=document.getElementById("empty"),updated=document.getElementById("updated"),sectionHeading=document.getElementById("sectionHeading");

const pct=v=>Number.isFinite(v)?(v>=0?"+":"")+v.toFixed(1)+"%":"—";
const money=v=>Number.isFinite(v)?"$"+v.toFixed(v>=100?2:3):"—";
const zoneText=z=>z&&Number.isFinite(z.low)&&Number.isFinite(z.high)?money(z.low)+"–"+money(z.high):"—";
function badge(text,type=""){return '<span class="badge '+type+'">'+text+'</span>'}
function swingView(r){
  const dd=r.demand_distance_pct, sd=r.supply_distance_pct, rsi=r.rsi;
  const trendBull=r.trend==="bullish";
  const weeklyBull=r.weekly_trend==="bullish";
  const fresh=(r.demand_retests??99)<=1;
  const strong=(r.departure_atr??0)>=1.8;
  const nearDemand=dd!=null&&dd<=1.5;
  const enoughRoom=sd==null||sd>=3.5;
  const rsiOk=rsi!=null&&rsi>=40&&rsi<=70;

  if(r.score>=82&&nearDemand&&fresh&&strong&&trendBull&&weeklyBull&&enoughRoom&&rsiOk){
    return {cls:"favorable",label:"Looks favorable now",detail:"Near demand, fresh/strong zone, bullish daily + weekly trend, and reasonable room before supply."};
  }
  if(sd!=null&&sd<=2){
    return {cls:"caution",label:"Watch — supply is close",detail:"The setup ranks well, but nearby supply limits the swing-trade room right now."};
  }
  if(r.score>=72&&dd!=null&&dd<=3&&fresh&&(trendBull||weeklyBull)){
    return {cls:"watch",label:"Watch for entry",detail:"Promising setup, but I’d want a cleaner reaction/confirmation from demand before treating it as a stronger swing entry."};
  }
  return {cls:"avoid",label:"Not attractive right now",detail:"The current combination of zone location, trend, freshness, RSI and room to supply is not strong enough for a high-confidence swing setup."};
}

function render(){
  const q=search.value.trim().toLowerCase();
  const filtered=rows.filter(r=>{
    const text=(r.symbol+" "+r.name).toLowerCase();
    const nearDemand=r.demand_distance_pct!=null&&r.demand_distance_pct<=3;
    const fresh=r.demand_retests===0;
    const bouncing=r.demand_bounce==="early"||r.demand_bounce==="confirmed";
    const typeOk=activeFilter==="all"||r.type===activeFilter||(activeFilter==="bounce"&&bouncing)||(activeFilter==="demand"&&nearDemand)||(activeFilter==="fresh"&&fresh);
    return typeOk&&text.includes(q);
  });
  if(activeFilter==="bounce") filtered.sort((a,b)=>(b.bounce_score||0)-(a.bounce_score||0)||b.score-a.score);
  else filtered.sort((a,b)=>b.score-a.score);
  sectionHeading.textContent=activeFilter==="bounce"?"Bullish reversals at demand":"Top setups";
  list.innerHTML="";
  filtered.forEach((r,i)=>{
    const n=tpl.content.cloneNode(true);
    n.querySelector(".rank").textContent=i+1;
    n.querySelector(".symbol").textContent=r.symbol;
    n.querySelector(".name").textContent=r.name;
    const s=n.querySelector(".score");s.textContent=Math.round(r.score);s.classList.add(r.score>=80?"good":r.score>=60?"mid":"low");
    n.querySelector(".price").textContent=money(r.price);
    n.querySelector(".demand").textContent=zoneText(r.demand_zone);
    n.querySelector(".supply").textContent=zoneText(r.supply_zone);
    n.querySelector(".rsi").textContent=r.rsi==null?"—":r.rsi.toFixed(0);

    const swing=n.querySelector(".swing-view");
    if(i===0){
      const sv=swingView(r);
      swing.classList.remove("hidden");
      swing.classList.add(sv.cls);
      swing.innerHTML='<span class="swing-kicker">SWING VIEW • RIGHT NOW</span><b>'+sv.label+'</b><small>'+sv.detail+'</small>';
    }

    const b=[];
    if(r.demand_bounce==="confirmed")b.push(badge("Confirmed bullish reversal","positive"));
    else if(r.demand_bounce==="early")b.push(badge("Early bullish reversal","positive"));
    if(r.demand_distance_pct!=null&&r.demand_distance_pct<=0.35)b.push(badge("At demand","positive"));
    else if(r.demand_distance_pct!=null&&r.demand_distance_pct<=3)b.push(badge("Approaching demand","positive"));
    if(r.demand_retests===0)b.push(badge("Fresh zone","positive"));
    else if(r.demand_retests===1)b.push(badge("1 retest"));
    if(r.departure_atr>=1.8)b.push(badge("Strong departure","positive"));
    if(r.trend==="bullish"&&r.weekly_trend==="bullish")b.push(badge("D+W bull trend","positive"));
    else if(r.trend==="bullish")b.push(badge("Daily bull","positive"));
    if(r.supply_distance_pct!=null&&r.supply_distance_pct<=3)b.push(badge("Near supply","warning"));
    b.push(badge(r.type.toUpperCase()));
    n.querySelector(".badges").innerHTML=b.join("");

    const why=n.querySelector(".why");
    const reasons=(r.reasons||[]).map(x=>"<li>"+x+"</li>").join("");
    const demandDist=r.demand_distance_pct==null?"—":pct(r.demand_distance_pct);
    const supplyDist=r.supply_distance_pct==null?"—":pct(r.supply_distance_pct);
    why.innerHTML="<ul>"+reasons+"</ul>"+
      '<div class="zone-stats"><span>Demand zone: <b>'+zoneText(r.demand_zone)+'</b></span>'+
      '<span>Distance to demand: <b>'+demandDist+'</b></span>'+
      '<span>Supply zone: <b>'+zoneText(r.supply_zone)+'</b></span>'+
      '<span>Distance to supply: <b>'+supplyDist+'</b></span>'+
      '<span>Bullish reversal: <b>'+(r.demand_bounce&&r.demand_bounce!=="none"?(r.demand_bounce==="confirmed"?"Confirmed":"Early")+" reversal • "+(r.bounce_pct==null?"—":pct(r.bounce_pct)):"—")+'</b></span>'+
      '<span>Retests: <b>'+(r.demand_retests??"—")+'</b></span>'+
      '<span>Departure: <b>'+(r.departure_atr==null?"—":r.departure_atr.toFixed(1)+" ATR")+'</b></span>'+
      '<span>Weekly: <b>'+((r.weekly_trend||"mixed").replace(/^./,c=>c.toUpperCase()))+'</b></span></div>';
    const btn=n.querySelector(".why-btn");
    btn.addEventListener("click",()=>{
      why.classList.toggle("hidden");
      btn.textContent=why.classList.contains("hidden")?"Why this score ▾":"Hide details ▴";
    });
    list.appendChild(n);
  });
  count.textContent=filtered.length+" shown";
  empty.classList.toggle("hidden",filtered.length!==0);
}

let lastGeneratedAt=null;
let lastLoadAt=0;

function formatStamp(iso){
  const d=new Date(iso);
  return d.toLocaleString([], {month:"short",day:"numeric",hour:"numeric",minute:"2-digit"});
}
function formatTime(d){
  return d.toLocaleTimeString([], {hour:"numeric",minute:"2-digit"});
}
async function fetchScan(){
  const bust=Date.now();
  const raw="https://raw.githubusercontent.com/bsteeves1/maple-zones/main/data/scan.json?ts="+bust;
  const local="data/scan.json?ts="+bust;
  try{
    const r=await fetch(raw,{cache:"no-store"});
    if(r.ok)return await r.json();
  }catch(e){}
  const r=await fetch(local,{cache:"no-store"});
  if(!r.ok)throw new Error("No scan data");
  return await r.json();
}

async function load(){
  lastLoadAt=Date.now();
  updated.textContent=lastGeneratedAt?"Checking for newer market data…":"Loading latest scan…";
  try{
    const data=await fetchScan();
    rows=(data.results||[]).sort((a,b)=>b.score-a.score);
    lastGeneratedAt=data.generated_at||lastGeneratedAt;
    const checked=new Date();
    updated.textContent="Market data "+formatStamp(lastGeneratedAt)+" • checked "+formatTime(checked);
    render();
  }catch(e){
    updated.textContent=lastGeneratedAt?"Market data "+formatStamp(lastGeneratedAt)+" • refresh check failed":"Waiting for market-data refresh";
    if(!lastGeneratedAt){rows=[];render();}
  }
}
search.addEventListener("input",render);
document.getElementById("filters").addEventListener("click",e=>{
  if(!e.target.matches(".chip"))return;
  document.querySelectorAll(".chip").forEach(x=>x.classList.remove("active"));
  e.target.classList.add("active"); activeFilter=e.target.dataset.filter; render();
});
document.getElementById("refreshBtn").addEventListener("click",load);
if("serviceWorker" in navigator){navigator.serviceWorker.register("sw.js",{updateViaCache:"none"}).then(reg=>reg.update()).catch(()=>{})}

const AUTO_REFRESH_MS=60*1000;
setInterval(()=>{if(document.visibilityState==="visible")load();},AUTO_REFRESH_MS);
document.addEventListener("visibilitychange",()=>{
  if(document.visibilityState==="visible"&&Date.now()-lastLoadAt>=AUTO_REFRESH_MS)load();
});
load();