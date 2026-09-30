let rows=[];let activeFilter="all";
const list=document.getElementById("list"),tpl=document.getElementById("rowTemplate"),search=document.getElementById("search"),count=document.getElementById("count"),empty=document.getElementById("empty"),updated=document.getElementById("updated");

const pct=v=>Number.isFinite(v)?(v>=0?"+":"")+v.toFixed(1)+"%":"—";
const money=v=>Number.isFinite(v)?"$"+v.toFixed(v>=100?2:3):"—";
function badge(text,type=""){return '<span class="badge '+type+'">'+text+'</span>'}

function render(){
  const q=search.value.trim().toLowerCase();
  const filtered=rows.filter(r=>{
    const text=(r.symbol+" "+r.name).toLowerCase();
    const nearDemand=r.demand_distance_pct!=null&&r.demand_distance_pct<=3;
    const fresh=r.demand_retests===0;
    const typeOk=activeFilter==="all"||r.type===activeFilter||(activeFilter==="demand"&&nearDemand)||(activeFilter==="fresh"&&fresh);
    return typeOk&&text.includes(q);
  });
  list.innerHTML="";
  filtered.forEach((r,i)=>{
    const n=tpl.content.cloneNode(true);
    const article=n.querySelector(".ticker-card");
    n.querySelector(".rank").textContent=i+1;
    n.querySelector(".symbol").textContent=r.symbol;
    n.querySelector(".name").textContent=r.name;
    const s=n.querySelector(".score");s.textContent=Math.round(r.score);s.classList.add(r.score>=80?"good":r.score>=60?"mid":"low");
    n.querySelector(".price").textContent=money(r.price);
    n.querySelector(".demand").textContent=r.demand_distance_pct==null?"—":pct(r.demand_distance_pct);
    n.querySelector(".supply").textContent=r.supply_distance_pct==null?"—":pct(r.supply_distance_pct);
    n.querySelector(".rsi").textContent=r.rsi==null?"—":r.rsi.toFixed(0);

    const b=[];
    if(r.demand_distance_pct!=null&&r.demand_distance_pct<=1)b.push(badge("At demand","positive"));
    else if(r.demand_distance_pct!=null&&r.demand_distance_pct<=3)b.push(badge("Near demand","positive"));
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
    why.innerHTML="<ul>"+reasons+"</ul>"+
      '<div class="zone-stats"><span>Retests: <b>'+(r.demand_retests??"—")+'</b></span>'+
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

async function load(){
  updated.textContent="Loading latest scan…";
  try{
    const res=await fetch("data/scan.json?ts="+Date.now(),{cache:"no-store"});
    if(!res.ok)throw new Error("No scan data");
    const data=await res.json();
    rows=(data.results||[]).sort((a,b)=>b.score-a.score);
    const d=new Date(data.generated_at);
    updated.textContent="Updated "+d.toLocaleString([], {month:"short",day:"numeric",hour:"numeric",minute:"2-digit"});
    render();
  }catch(e){
    updated.textContent="Waiting for market-data refresh";
    rows=[]; render();
  }
}
search.addEventListener("input",render);
document.getElementById("filters").addEventListener("click",e=>{
  if(!e.target.matches(".chip"))return;
  document.querySelectorAll(".chip").forEach(x=>x.classList.remove("active"));
  e.target.classList.add("active"); activeFilter=e.target.dataset.filter; render();
});
document.getElementById("refreshBtn").addEventListener("click",load);
if("serviceWorker" in navigator){navigator.serviceWorker.register("sw.js").catch(()=>{})}
load();