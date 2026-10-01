/* Maple UI V3.7: entry readiness is not the V3.4 watchlist-quality score. */
(async function(){
  'use strict';
  // An old installed HTML shell can briefly load the new app.js first.
  if(!globalThis.MapleReadiness){
    try{await new Promise((resolve,reject)=>{
      const s=document.createElement('script');s.src='readiness.js?v=3.6';
      s.onload=resolve;s.onerror=reject;document.head.appendChild(s);
    });}catch(e){
      document.getElementById('updated').textContent='Ranking module could not load — reopen Maple to retry.';
      return; // Never fall back to ranking entry readiness by the old score.
    }
  }
  const R=globalThis.MapleReadiness;
  let rows=[],activeFilter='all',lastGeneratedAt=null,lastLoadAt=0,loading=false,lastHealthKey='';
  const list=document.getElementById('list'),tpl=document.getElementById('rowTemplate'),
    search=document.getElementById('search'),count=document.getElementById('count'),
    empty=document.getElementById('empty'),updated=document.getElementById('updated'),
    sectionHeading=document.getElementById('sectionHeading'),refreshBtn=document.getElementById('refreshBtn');
  // Keep mixed-cache upgrades safe without requiring a reinstall.
  if(!document.getElementById('rankingMode')){
    const label=document.createElement('label');label.className='ranking-control';
    label.innerHTML='Rank by <select id="rankingMode"><option value="entry">Entry readiness (default)</option><option value="quality">Watchlist quality (not entry timing)</option></select>';
    document.querySelector('.controls').appendChild(label);
  }
  if(!document.getElementById('rankingSummary')){
    const p=document.createElement('p');p.id='rankingSummary';p.className='ranking-summary';
    document.querySelector('.section-title').after(p);
  }
  const rankingMode=document.getElementById('rankingMode'),rankingSummary=document.getElementById('rankingSummary');
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pct=v=>Number.isFinite(v)?v.toFixed(2)+'%':'unknown';
  const money=v=>Number.isFinite(v)?'$'+v.toFixed(v>=100?2:3):'—';
  const zoneText=z=>z&&Number.isFinite(z.low)&&Number.isFinite(z.high)?money(z.low)+'–'+money(z.high):'—';
  function dateText(iso){
    if(!/^\d{4}-\d{2}-\d{2}$/.test(iso||''))return 'unknown';
    const d=new Date(iso+'T12:00:00');
    return Number.isNaN(d.getTime())?'unknown':d.toLocaleDateString([], {year:'numeric',month:'short',day:'numeric'});
  }
  function retestText(z){
    if(!z)return 'No qualifying candidate';
    if(!Number.isInteger(z.touch_bars))return 'Legacy counts — awaiting zone recheck';
    const n=z.retests,days=z.touch_bars;
    return (n===0&&!z.wick_breached?'Untested • ':'')+n+' separate '+(n===1?'visit':'visits')+
      ' • '+days+' daily '+(days===1?'candle':'candles')+' touched';
  }
  const zoneMeta=z=>z?'Formed '+dateText(z.formed_at)+' • '+retestText(z)+(z.wick_breached?' • BOUNDARY BREACHED':''):'No qualifying candidate';
  const isCurrent=r=>r.rules_version===R.POLICY.zoneRulesVersion;
  const cleanDemand=r=>isCurrent(r)&&r.demand_zone?.valid&&!r.demand_zone.wick_breached&&!r.overlap_conflict;
  function bounceLabel(r){
    if(!isCurrent(r))return 'Legacy signal — needs rescan';
    if(r.demand_bounce==='swing_break')return 'Bullish reversal confirmed';
    if(r.demand_bounce==='early')return r.bar_is_provisional?'Early bounce • provisional':'Early bounce • unconfirmed';
    return 'No clean bounce signal';
  }
  const badge=(text,type='')=>'<span class="badge '+type+'">'+esc(text)+'</span>';
  function setText(root,selector,value){const el=root.querySelector(selector);if(el)el.textContent=value;}
  function healthKey(){return R.scanHealth(lastGeneratedAt).state+'|'+R.sessionDate();}
  function render(){
    const q=search.value.trim().toLowerCase(),mode=rankingMode.value;
    const ranked=R.rank(rows,{generatedAt:lastGeneratedAt,now:Date.now()},mode);
    const filtered=ranked.filter(({row:r,readiness:e})=>{
      const text=(r.symbol+' '+r.name).toLowerCase();
      const near=e.distancePct!==null&&e.distancePct<=R.POLICY.maxDemandDistancePct;
      const fresh=cleanDemand(r)&&r.demand_zone.touch_bars===0;
      return text.includes(q)&&(activeFilter==='all'||r.type===activeFilter||
        (activeFilter==='bounce'&&e.bounceCandidate)||(activeFilter==='demand'&&near)||(activeFilter==='fresh'&&fresh));
    });
    const candidates=filtered.filter(x=>x.readiness.nearCandidate).length;
    sectionHeading.textContent=mode==='quality'?'Watchlist quality — not entry timing':
      activeFilter==='bounce'?'Near-demand bounces — for review':'Entry-readiness ranking';
    rankingSummary.textContent=mode==='quality'?
      'Sorted by general watchlist quality. A high number does not mean a good entry now; each card keeps its separate entry-readiness status.':
      candidates?candidates+' near-demand watch '+(candidates===1?'candidate':'candidates')+
        '. Sorted by reaction evidence, then distance to demand, then quality. Waiting, confirmation, or review is not a buy signal.':
        'No qualifying near-demand setups in this view. Any remaining results are watchlist/reference only — not entry-ready.';
    const fragment=document.createDocumentFragment();let lastGroup=null,entryOrdinal=0;
    filtered.forEach(({row:r,readiness:e},i)=>{
      const group=e.nearCandidate?'NEAR-DEMAND WATCH CANDIDATES':'WATCHLIST & CAUTIONS — NOT ENTRY-READY';
      if(mode==='entry'&&group!==lastGroup){
        const h=document.createElement('h4');h.className='rank-group';h.textContent=group;
        fragment.appendChild(h);lastGroup=group;
      }
      const n=tpl.content.cloneNode(true),card=n.querySelector('.ticker-card');
      card.dataset.symbol=r.symbol;card.dataset.readiness=e.state;
      const rankEl=n.querySelector('.rank');
      let shownRank='—',watchOrdinal=null;
      if(mode==='quality')shownRank=String(i+1);
      else if(e.nearCandidate){watchOrdinal=++entryOrdinal;shownRank='#'+watchOrdinal;}
      rankEl.textContent=shownRank;
      if(watchOrdinal){
        rankEl.setAttribute('aria-label','Watch candidate #'+watchOrdinal);
        const rankContext=document.createElement('div');rankContext.className='rank-context';
        rankContext.textContent='Watch candidate #'+watchOrdinal;
        n.querySelector('.ticker-main').prepend(rankContext);
      }
      setText(n,'.symbol',r.symbol);setText(n,'.name',r.name);
      const quality=n.querySelector('.quality-score')||n.querySelector('.score');
      if(quality){
        quality.className='quality-score';quality.textContent=e.qualityScore===null?'—':Math.round(e.qualityScore)+'/100';
        quality.title='Watchlist quality only — not entry readiness or a win probability';
        if(!quality.parentElement.classList.contains('quality-summary')){
          const wrap=document.createElement('div');wrap.className='quality-summary';
          const label=document.createElement('span');label.textContent='Watchlist quality';
          quality.before(wrap);wrap.append(label,quality);
        }
      }
      setText(n,'.price',money(r.price));setText(n,'.rsi',Number.isFinite(r.rsi)?r.rsi.toFixed(0):'—');
      setText(n,'.demand',zoneText(r.demand_zone));setText(n,'.supply',zoneText(r.supply_zone));
      setText(n,'.demand-meta',zoneMeta(r.demand_zone));setText(n,'.supply-meta',zoneMeta(r.supply_zone));
      const supplyLabel=n.querySelector('.supply')?.parentElement?.querySelector('span');
      if(supplyLabel)supplyLabel.textContent=r.breached_supply_reference?'Next intact supply':'Supply candidate';
      const entry=n.querySelector('.swing-view');entry.className='swing-view '+e.tone;
      entry.innerHTML='<span class="swing-kicker">ENTRY READINESS</span><b>'+esc(e.label)+'</b><small>'+esc(e.detail)+'</small>';
      // Put the status before the price/zone blocks on every card, not only #1.
      n.querySelector('.metrics').before(entry);
      if(e.nearCandidate){
        const confirmation=document.createElement('div');
        const trigger=Number.isFinite(e.confirmationTrigger)?e.confirmationTrigger:null;
        if(e.state==='break_review'){
          confirmation.className='confirmation-meta confirmed';
          confirmation.textContent=trigger?
            'Bullish reversal confirmed: a completed daily close broke the '+money(trigger)+' local swing trigger on '+dateText(r.bounce_break_at)+'.':
            'Bullish reversal confirmed by a completed prior-session local swing break on '+dateText(r.bounce_break_at)+'.';
        }else{
          confirmation.className='confirmation-meta pending';
          confirmation.textContent=trigger?
            'Bullish confirmation needed: completed daily close above the '+money(trigger)+' local swing trigger.':
            'Bullish confirmation needed: waiting for a valid local lower-high trigger.';
          if(r.bar_is_provisional)confirmation.textContent+=' Today\'s provisional candle does not count as completed confirmation.';
        }
        entry.after(confirmation);
      }
      const distance=document.createElement('p');distance.className='distance-meta';
      distance.textContent=(e.distancePct===null?'Demand distance: unknown':e.distancePct===0?
        'Price at / inside the displayed demand range':'Pullback to demand: '+pct(e.distancePct))+
        ' • Room to supply: '+pct(e.supplyRoomPct);
      const metrics=n.querySelector('.metrics');
      metrics.after(distance);
      if(r.breached_supply_reference){
        const ref=document.createElement('div');ref.className='breached-reference';
        ref.innerHTML='<span>BREACHED SUPPLY REFERENCE</span><b>'+esc(zoneText(r.breached_supply_reference))+
          '</b><small>'+esc(zoneMeta(r.breached_supply_reference))+'</small><p>'+
          (r.supply_zone?'Kept for historical resistance context. Room-to-supply uses the next intact supply above it.':
            'Kept for historical resistance context. No higher intact supply candidate is currently available.')+'</p>';
        metrics.after(ref);
      }
      const meta=document.createElement('p');meta.className='candle-meta';
      meta.textContent=isCurrent(r)?'Price candle: '+dateText(r.last_candle_date)+
        (r.bar_is_provisional?' • provisional':'')+'. Completed-candle checks through '+dateText(r.validated_through)+'.':
        'Older scan — awaiting zone validation.';
      distance.after(meta);
      const warnings=Array.isArray(r.warnings)?r.warnings:[];
      if(warnings.length){
        const panel=document.createElement('div');panel.className='zone-warnings';
        panel.innerHTML='<strong>Zone cautions</strong><ul>'+warnings.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>';
        meta.after(panel);
      }
      const b=[];
      if(e.bounceCandidate)b.push(badge(bounceLabel(r),e.state==='break_review'?'positive':''));
      if(r.demand_zone?.wick_breached)b.push(badge('Demand boundary breached','warning'));
      if(r.supply_zone?.wick_breached)b.push(badge('Supply boundary breached','warning'));
      if(r.breached_supply_reference)b.push(badge('Prior supply breached','warning'));
      if(r.overlap_conflict)b.push(badge('Overlapping zones','warning'));
      if(cleanDemand(r)&&r.demand_zone.touch_bars===0)b.push(badge('Untested demand'));
      if(r.trend==='bullish'&&r.weekly_trend==='bullish')b.push(badge('D+W bull trend'));
      b.push(badge((r.type||'asset').toUpperCase()));
      n.querySelector('.badges').innerHTML=b.join('');
      const why=n.querySelector('.why');
      const details=['Entry readiness: '+e.label,e.detail,
        'Watchlist quality: '+(e.qualityScore===null?'unknown':e.qualityScore+'/100')+' — not entry timing',
        'Demand: '+zoneText(r.demand_zone)+' • '+zoneMeta(r.demand_zone),
        (r.breached_supply_reference?'Next intact supply: ':'Supply: ')+zoneText(r.supply_zone)+' • '+zoneMeta(r.supply_zone),
        r.breached_supply_reference?'Breached supply reference: '+zoneText(r.breached_supply_reference)+' • '+zoneMeta(r.breached_supply_reference):'',
        'Pullback to demand: '+pct(e.distancePct),'Room to supply: '+pct(e.supplyRoomPct),
        'Zone-engine reaction: '+bounceLabel(r),r.bounce_detail||'',
        'Local lower high: '+money(r.bounce_swing_high)+' • '+dateText(r.bounce_swing_high_at),
        'Bullish confirmation trigger: '+money(e.confirmationTrigger),
        'Completed break date: '+dateText(r.bounce_break_at)];
      for(const [label,z] of [['Demand',r.demand_zone],['Supply',r.supply_zone],['Breached supply reference',r.breached_supply_reference]]){
        if(!z)continue;
        details.push(label+' first eligible: '+dateText(z.confirmed_at));
        details.push(label+' longest continuous visit: '+(z.max_consecutive_touch_bars??'unknown')+' daily candles');
        if(z.wick_breached)details.push(label+' first breach: '+dateText(z.first_breach_at)+' • extreme '+money(z.breach_extreme));
      }
      why.innerHTML='<strong>Watchlist-quality inputs</strong><ul>'+(r.reasons||[]).map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>'+
        '<div class="zone-stats">'+details.filter(Boolean).map(x=>'<span>'+esc(x)+'</span>').join('')+'</div>';
      const btn=n.querySelector('.why-btn');btn.textContent='Why this ranking ▾';
      btn.addEventListener('click',()=>{
        why.classList.toggle('hidden');btn.textContent=why.classList.contains('hidden')?'Why this ranking ▾':'Hide details ▴';
      });
      fragment.appendChild(n);
    });
    list.replaceChildren(fragment);count.textContent=filtered.length+' shown';
    empty.textContent=activeFilter==='bounce'?'No clean, near-demand bounce candidates in this scan.':'No matching tickers.';
    empty.classList.toggle('hidden',filtered.length!==0);lastHealthKey=healthKey();
  }
  function formatStamp(iso){
    const d=new Date(iso);return Number.isNaN(d.getTime())?'unknown':d.toLocaleString([], {month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
  }
  async function fetchScan(){
    const bust=Date.now();
    const urls=['https://raw.githubusercontent.com/bsteeves1/maple-zones/main/data/scan.json?ts='+bust,'data/scan.json?ts='+bust];
    for(const url of urls){
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
      try{
        const response=await fetch(url,{cache:'no-store',signal:controller.signal});
        if(!response.ok)throw new Error('HTTP '+response.status);
        const data=await response.json();
        if(!Array.isArray(data.results)||!Number.isFinite(Date.parse(data.generated_at)))throw new Error('Invalid scan schema');
        if(lastGeneratedAt&&Date.parse(data.generated_at)<Date.parse(lastGeneratedAt))continue;
        if(!data.results.every(r=>typeof r.symbol==='string'&&Number.isFinite(r.price)&&Number.isFinite(r.score)))throw new Error('Invalid scan rows');
        return data;
      }catch(e){console.warn('Scan source unavailable',e.message);}finally{clearTimeout(timer);}
    }
    throw new Error('No usable scan source');
  }
  async function load({quiet=false}={}){
    if(loading)return;loading=true;lastLoadAt=Date.now();refreshBtn.disabled=true;
    if(!quiet)updated.textContent=lastGeneratedAt?'Checking for a newer scan…':'Loading scan…';
    try{
      const data=await fetchScan(),changed=data.generated_at!==lastGeneratedAt;
      rows=data.results;lastGeneratedAt=data.generated_at;
      const h=R.scanHealth(lastGeneratedAt),age=h.ageMinutes===null?'unknown':Math.floor(h.ageMinutes);
      updated.textContent='Scan completed '+formatStamp(lastGeneratedAt)+' • '+age+' min old • checked '+new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit'})+
        (rows.some(r=>!isCurrent(r))?' • awaiting zone recheck':'')+(h.state!=='recent'?' • entry ranking paused — needs newer scan':'');
      if(changed||healthKey()!==lastHealthKey||!list.children.length)render();
    }catch(e){
      updated.textContent=lastGeneratedAt?'Refresh failed — retaining scan from '+formatStamp(lastGeneratedAt):'Scan could not load — tap ↻ to retry';
      // An aging scan must lose entry readiness even while the network is down.
      if(rows.length&&healthKey()!==lastHealthKey)render();
    }finally{loading=false;refreshBtn.disabled=false;}
  }
  search.addEventListener('input',render);rankingMode.addEventListener('change',render);
  document.getElementById('filters').addEventListener('click',e=>{
    if(!e.target.matches('.chip'))return;
    document.querySelectorAll('.chip').forEach(x=>x.classList.remove('active'));
    e.target.classList.add('active');activeFilter=e.target.dataset.filter;render();
  });
  refreshBtn.addEventListener('click',()=>load());
  if('serviceWorker' in navigator){
    const controlled=Boolean(navigator.serviceWorker.controller);let reloading=false;
    navigator.serviceWorker.addEventListener('controllerchange',()=>{if(controlled&&!reloading){reloading=true;location.reload();}});
    navigator.serviceWorker.register('sw.js',{updateViaCache:'none'}).then(reg=>reg.update()).catch(()=>{});
  }
  const AUTO_REFRESH_MS=15000;
  setInterval(()=>{if(document.visibilityState==='visible')load({quiet:true});},AUTO_REFRESH_MS);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&Date.now()-lastLoadAt>=AUTO_REFRESH_MS)load({quiet:true});});
  load();
})();
