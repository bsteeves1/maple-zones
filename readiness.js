/* Maple UI V3.5. Deterministic entry-readiness classification, not a forecast.
 * The V3.4 zone engine and its quality score are unchanged.
 * 3% proximity / 2% supply room / 20-minute scan age are explicit screening
 * defaults, NOT backtested probabilities or trading-performance claims.
 * This same module drives filtering, sorting, labels and the card explanation.
 */
(function(root, factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.MapleReadiness=api;
})(typeof globalThis!=='undefined'?globalThis:this, function(){
  'use strict';
  const POLICY=Object.freeze({maxDemandDistancePct:3,minSupplyRoomPct:2,
    maxScanAgeMinutes:20,maxTouchAgeBars:6,zoneRulesVersion:'3.4'});
  const finite=v=>typeof v==='number'&&Number.isFinite(v);
  const validDate=s=>{
    if(typeof s!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(s))return false;
    const d=new Date(s+'T12:00:00Z');
    return Number.isFinite(d.getTime())&&d.toISOString().slice(0,10)===s;
  };
  function sessionDate(now=Date.now()){
    const d=new Date(now);
    if(!Number.isFinite(d.getTime()))return null;
    const parts=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',
      year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(d);
    const get=k=>parts.find(p=>p.type===k).value;
    return get('year')+'-'+get('month')+'-'+get('day');
  }
  function scanHealth(generatedAt,now=Date.now()){
    const stamp=typeof generatedAt==='string'?Date.parse(generatedAt):NaN;
    if(!finite(stamp)||!finite(now)||stamp-now>120000)return {state:'unknown',ageMinutes:null};
    const age=Math.max(0,(now-stamp)/60000);
    return {state:age>POLICY.maxScanAgeMinutes?'aging':'recent',ageMinutes:age};
  }
  const zoneGeometry=z=>Boolean(z&&finite(z.low)&&finite(z.high)&&z.low>0&&z.high>z.low);
  const quality=r=>finite(r?.score)?Math.max(0,Math.min(100,r.score)):null;
  function classify(row,context={}){
    const r=row||{}, now=context.now??Date.now();
    const dz=r.demand_zone,sz=r.supply_zone,p=r.price;
    // Compute from unrounded prices, not the backend's rounded percentage.
    const dd=finite(p)&&p>0&&zoneGeometry(dz)?Math.max(0,(p-dz.high)/p*100):null;
    const sd=finite(p)&&p>0&&zoneGeometry(sz)?Math.max(0,(sz.low-p)/p*100):null;
    const base={qualityScore:quality(r),distancePct:dd,supplyRoomPct:sd,
      tier:0,nearCandidate:false,bounceCandidate:false};
    const result=(state,label,detail,tone='caution',tier=0)=>({...base,state,label,detail,tone,tier,
      nearCandidate:tier>=3,bounceCandidate:tier>=4});
    if(r.rules_version!==POLICY.zoneRulesVersion)return result('legacy','Awaiting zone recheck',
      'Older zone rules. A legacy quality score is not entry readiness.','muted');
    if(!finite(p)||p<=0)return result('invalid_price','Price unavailable',
      'A usable price is required to measure distance to demand.');
    const health=scanHealth(context.generatedAt,now);
    if(health.state!=='recent')return result('stale',health.state==='aging'?'Needs fresh scan':'Scan time unavailable',
      'Entry ranking is paused until a scan no more than 20 minutes old is available. Existing candidates remain for reference.','muted');
    const today=sessionDate(now);
    if(!validDate(r.last_candle_date)||!today||r.last_candle_date>today)return result('invalid_date','Price date unavailable',
      'The price-candle date cannot be verified for this session.','muted');
    if(r.last_candle_date!==today)return result('prior_session','Prior-session data — watchlist only',
      'The price candle is not dated today in New York. This can be normal outside market hours; it is not a current-session entry check.','muted');
    if(!dz)return result('missing_demand','No qualifying demand',
      'No active demand candidate was found. Other quality points cannot create an entry setup.');
    if(!zoneGeometry(dz)||dz.valid!==true||typeof dz.wick_breached!=='boolean')return result('invalid_demand','Demand needs review',
      'Demand geometry or validity is missing or invalid.');
    if(p<dz.low)return result('below_demand','Price below demand',
      'The available price is below the demand boundary. Excluded from near-demand entry candidates.');
    if(dz.wick_breached)return result('breached_demand','Demand boundary breached',
      'The close rule retained this zone, but price traded through it. It is not a clean demand-bounce entry.');
    const overlap=zoneGeometry(sz)&&Math.min(dz.high,sz.high)>=Math.max(dz.low,sz.low);
    if(r.overlap_conflict||overlap)return result('overlap','Conflicting zones — caution',
      'Demand and supply overlap. Both remain visible; this is not a clean entry setup.');
    if(sz&&(!zoneGeometry(sz)||sz.valid!==true||typeof sz.wick_breached!=='boolean'))return result('invalid_supply','Supply needs review',
      'Opposing supply is invalid or incomplete; it cannot establish clear upside room.');
    if(sz?.wick_breached)return result('breached_supply','Supply boundary breached',
      'The opposing supply boundary has been traded through. Manual review is required before treating the room as clear.');
    if(sz&&p>sz.high)return result('passed_supply','Price beyond supplied zone',
      'The available price is above the displayed supply zone. A fresh zone selection is needed.');
    if(sd!==null&&sd<=POLICY.minSupplyRoomPct)return result('limited_room','Supply too close — caution',
      'Only '+sd.toFixed(2)+'% to opposing supply. This screen requires more than 2%; a high quality score cannot override that check.');
    if(dd>POLICY.maxDemandDistancePct)return result('far_demand','Watchlist only — away from demand',
      'A '+dd.toFixed(2)+'% pullback is needed to reach demand. The near-demand limit is 3%; trend and quality points cannot override it.'+
      (sz?'':' Opposing supply is also unknown.'),'muted',1);
    if(!sz)return result('unknown_supply','Watchlist only — supply unknown',
      'Price is near demand, but no qualifying opposing supply is available. Missing supply does not mean unlimited room.','muted',2);
    const touched=Number.isInteger(dz.touch_bars)&&dz.touch_bars>0&&
      Number.isInteger(r.bounce_bars_since_touch)&&r.bounce_bars_since_touch>=0&&
      r.bounce_bars_since_touch<=POLICY.maxTouchAgeBars;
    const above=p>dz.high;
    const breakEvidence=touched&&above&&r.demand_bounce==='swing_break'&&
      finite(r.bounce_swing_high)&&r.bounce_swing_high>0&&p>r.bounce_swing_high&&
      validDate(r.bounce_break_at)&&validDate(r.validated_through)&&
      r.bounce_break_at<=r.validated_through&&r.validated_through<today&&
      validDate(r.bounce_swing_high_at)&&r.bounce_swing_high_at<r.bounce_break_at;
    if(breakEvidence)return result('break_review','Local break — review',
      'Within 3% of intact demand, with room to supply and a completed local lower-high break after a recent visit. Review the chart; this is not a buy instruction or a success probability.','review',5);
    if(touched&&above&&r.demand_bounce==='early')return result('early_bounce','Early bounce — unconfirmed',
      'Within 3% of intact demand with room to supply and a recent upward reaction. There is no completed local swing-break confirmation.'+
      (r.bar_is_provisional?' Today\'s price candle is provisional.':''),'watch',4);
    return result('near_demand','Near demand — waiting',
      'Within 3% of intact demand with room to supply, but no qualifying recent bounce or completed local swing break. Wait for evidence rather than relying on watchlist quality.','watch',3);
  }
  const cmpString=(a,b)=>a<b?-1:a>b?1:0;
  function compare(a,b,mode='entry'){
    const qa=a.readiness.qualityScore??-1,qb=b.readiness.qualityScore??-1;
    if(mode==='quality'&&qa!==qb)return qb-qa;
    const tier=b.readiness.tier-a.readiness.tier;
    if(tier)return tier;
    const da=a.readiness.distancePct??Infinity,db=b.readiness.distancePct??Infinity;
    if(da!==db)return da<db?-1:1;
    if(qa!==qb)return qb-qa;
    return cmpString(String(a.row.symbol||''),String(b.row.symbol||''));
  }
  function rank(rows,context={},mode='entry'){
    return rows.map(row=>({row,readiness:classify(row,context)})).sort((a,b)=>compare(a,b,mode));
  }
  return Object.freeze({POLICY,classify,rank,compare,scanHealth,sessionDate});
});
