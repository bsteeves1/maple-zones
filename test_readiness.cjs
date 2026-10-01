'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const R=require('./readiness.js');
const context={now:Date.parse('2026-10-01T19:55:00Z'),generatedAt:'2026-10-01T19:54:00Z'};
function row(patch={}){
  return {symbol:'NEAR.TO',name:'Synthetic fixture',type:'stock',rules_version:'3.4',
    price:100,score:65,last_candle_date:'2026-10-01',validated_through:'2026-09-30',
    bar_is_provisional:true,demand_zone:{low:97,high:99,valid:true,wick_breached:false,
      touch_bars:2,retests:1,formed_at:'2026-09-10'},
    supply_zone:{low:110,high:112,valid:true,wick_breached:false,touch_bars:0,retests:0},
    demand_bounce:'none',bounce_bars_since_touch:null,overlap_conflict:false,...patch};
}
function dcbo(){return row({symbol:'DCBO.TO',price:33.6,score:90,
  demand_zone:{low:28.13,high:28.71,valid:true,wick_breached:false,touch_bars:0,retests:0,
    formed_at:'2026-08-06'},
  supply_zone:{low:39.35,high:40.08,valid:true,wick_breached:false,touch_bars:0,retests:0,
    formed_at:'2025-10-27'}});}
const c=r=>R.classify(r,context);
const early=()=>row({demand_bounce:'early',bounce_bars_since_touch:1,bounce_confirmation_trigger:101.2});
const swing=()=>row({demand_bounce:'swing_break',bounce_bars_since_touch:2,
  bounce_swing_high:99.5,bounce_swing_high_at:'2026-09-24',bounce_confirmation_trigger:99.75,
  bounce_break_at:'2026-09-30'});

test('DCBO screenshot: high quality remains watchlist-only at 14.55% from demand',()=>{
  const x=c(dcbo());assert.equal(x.state,'far_demand');assert.equal(x.qualityScore,90);
  assert.ok(Math.abs(x.distancePct-14.5535714286)<1e-9);
  assert.equal(x.nearCandidate,false);assert.equal(x.bounceCandidate,false);
  assert.match(x.detail,/14\.55% pullback/);
});
test('Default ranking promotes a clean near setup over the higher-quality distant DCBO',()=>{
  assert.equal(R.rank([dcbo(),row({score:40})],context)[0].row.symbol,'NEAR.TO');
});
test('Separate quality mode deliberately ranks quality, without changing readiness labels',()=>{
  const x=R.rank([row(),dcbo()],context,'quality');
  assert.equal(x[0].row.symbol,'DCBO.TO');assert.equal(x[0].readiness.state,'far_demand');
});
test('A stale bounce flag never overrides the distance gate',()=>{
  const d={...dcbo(),demand_bounce:'swing_break',bounce_bars_since_touch:1};
  assert.equal(c(d).bounceCandidate,false);assert.equal(c(d).state,'far_demand');
});
test('No-demand high-quality symbol is not an entry candidate',()=>{
  assert.equal(c(row({score:100,demand_zone:null})).nearCandidate,false);
});
test('Breached demand cannot outrank a clean near setup',()=>{
  const bad=row({symbol:'BAD',score:100,demand_zone:{...row().demand_zone,wick_breached:true}});
  const good=row({symbol:'GOOD',score:20});
  assert.equal(c(bad).state,'breached_demand');assert.equal(R.rank([bad,good],context)[0].row.symbol,'GOOD');
});
test('Breached supply blocks an apparent completed swing break',()=>{
  assert.equal(c({...swing(),supply_zone:{...row().supply_zone,wick_breached:true}}).state,'breached_supply');
});
test('Geometric overlap is caught even with an incorrectly false overlap flag',()=>{
  const z={...row().supply_zone,low:98.5,high:102};
  assert.equal(c(row({supply_zone:z})).state,'overlap');
});
test('Reported overlap conflict cannot be ignored by the ranking',()=>{
  assert.equal(c(row({overlap_conflict:true})).nearCandidate,false);
});
test('Missing supply means unknown room, never an entry candidate',()=>{
  const x=c({...swing(),supply_zone:null});assert.equal(x.state,'unknown_supply');assert.equal(x.nearCandidate,false);
});
test('Price in supply is not a clean entry',()=>{
  assert.equal(c(row({supply_zone:{...row().supply_zone,low:99.9,high:101}})).state,'limited_room');
});
test('Supply precisely 2% away is blocked',()=>{
  assert.equal(c(row({supply_zone:{...row().supply_zone,low:102,high:103}})).state,'limited_room');
});
test('Supply more than 2% away passes the supply-room screen',()=>{
  assert.equal(c(row({supply_zone:{...row().supply_zone,low:102.001,high:103}})).state,'near_demand');
});
test('Distance exactly 3% is eligible for waiting, not bounce confirmation',()=>{
  const x=c(row({demand_zone:{...row().demand_zone,low:96,high:97}}));
  assert.equal(x.state,'near_demand');assert.equal(x.bounceCandidate,false);
});
test('Unrounded distance slightly above 3% is excluded, even if backend rounds it to 3',()=>{
  const x=c(row({demand_distance_pct:3,demand_zone:{...row().demand_zone,low:96,high:96.999}}));
  assert.equal(x.state,'far_demand');
});
test('At the lower demand boundary is inside, not below',()=>{
  assert.equal(c(row({price:97})).state,'near_demand');
});
test('Below the lower demand boundary is excluded',()=>{
  assert.equal(c(row({price:96.99})).state,'below_demand');
});
test('Provisional early bounce is explicitly unconfirmed',()=>{
  const x=c(early());assert.equal(x.state,'early_bounce');assert.match(x.detail,/provisional/);
  assert.equal(x.confirmationTrigger,101.2);
});
test('Completed local break uses an explicit bullish reversal confirmed review label',()=>{
  assert.equal(c(swing()).label,'Bullish reversal confirmed — review');
});
test('Untested demand cannot carry an early bounce',()=>{
  const r=early();r.demand_zone.touch_bars=0;assert.equal(c(r).state,'near_demand');
});
test('Old touch outside six-bar window is not a bounce candidate',()=>{
  assert.equal(c({...early(),bounce_bars_since_touch:7}).bounceCandidate,false);
});
test('Inside demand with a stray bounce flag still awaits a reaction',()=>{
  assert.equal(c({...early(),price:98}).state,'near_demand');
});
test('Completed local break with dated prior-session evidence reaches review stage',()=>{
  const x=c(swing());assert.equal(x.state,'break_review');assert.equal(x.bounceCandidate,true);
});
test('A stronger label cannot be created from a bare flag without evidence',()=>{
  assert.equal(c(row({demand_bounce:'swing_break',bounce_bars_since_touch:1})).state,'near_demand');
});
test('Current-day provisional break date cannot be treated as completed',()=>{
  assert.equal(c({...swing(),bounce_break_at:'2026-10-01'}).state,'near_demand');
});
test('Invalid validation chronology is not confirmation',()=>{
  assert.equal(c({...swing(),validated_through:'2026-10-02'}).state,'near_demand');
});
test('Unknown pivot date is not confirmation',()=>{
  assert.equal(c({...swing(),bounce_swing_high_at:null}).state,'near_demand');
});
test('Price recrossed below local high is not a completed-break candidate',()=>{
  assert.equal(c({...swing(),bounce_swing_high:101}).state,'near_demand');
});
test('Ranking stage order is break review, early, waiting, far, blocked',()=>{
  const inputs=[dcbo(),row({symbol:'WAIT'}),{...early(),symbol:'EARLY'},
    {...swing(),symbol:'BREAK'},row({symbol:'BLOCKED',demand_zone:null})];
  assert.deepEqual(R.rank(inputs,context).map(x=>x.row.symbol),['BREAK','EARLY','WAIT','DCBO.TO','BLOCKED']);
});
test('Within one stage, distance beats general quality',()=>{
  const closer=row({symbol:'CLOSE',score:20,demand_zone:{...row().demand_zone,high:99.5}});
  const farther=row({symbol:'FAR',score:100});
  assert.equal(R.rank([farther,closer],context)[0].row.symbol,'CLOSE');
});
test('Quality breaks ties only after readiness stage and distance',()=>{
  assert.equal(R.rank([row({symbol:'LOW',score:20}),row({symbol:'HIGH',score:90})],context)[0].row.symbol,'HIGH');
});
test('Zero quality is preserved, not coerced to missing',()=>{
  assert.equal(c(row({score:0})).qualityScore,0);
});
test('Rank does not mutate source rows or their order',()=>{
  const input=[dcbo(),row()];const before=JSON.stringify(input);R.rank(input,context);
  assert.equal(JSON.stringify(input),before);
});
test('All unqualified rows produce zero near-demand candidates, not a forced number one',()=>{
  assert.equal(R.rank([dcbo(),row({demand_zone:null})],context).filter(x=>x.readiness.nearCandidate).length,0);
});
test('A 20-minute-old scan is accepted at the documented boundary',()=>{
  assert.equal(R.classify(row(),{...context,generatedAt:'2026-10-01T19:35:00Z'}).state,'near_demand');
});
test('A scan just over 20 minutes old pauses entry-readiness ranking',()=>{
  assert.equal(R.classify(swing(),{...context,generatedAt:'2026-10-01T19:34:59Z'}).state,'stale');
});
test('Missing scan timestamp fails safely',()=>{
  assert.equal(R.classify(swing(),{now:context.now}).nearCandidate,false);
});
test('Future scan timestamp outside clock tolerance fails safely',()=>{
  assert.equal(R.classify(swing(),{...context,generatedAt:'2026-10-01T20:55:00Z'}).state,'stale');
});
test('Older price candle remains watchlist, even when scan is new',()=>{
  assert.equal(c(row({last_candle_date:'2026-09-30'})).state,'prior_session');
});
test('Future price date is not usable current-session data',()=>{
  assert.equal(c(row({last_candle_date:'2026-10-02'})).state,'invalid_date');
});
test('Invalid dates do not roll over and count as usable prices',()=>{
  assert.equal(c(row({last_candle_date:'2026-02-30'})).state,'invalid_date');
});
test('Exchange session date is not shifted by device timezone or UTC midnight',()=>{
  assert.equal(R.sessionDate(Date.parse('2026-10-02T02:00:00Z')),'2026-10-01');
});
test('Legacy rules never inherit current entry readiness',()=>{
  assert.equal(c(row({rules_version:'3.3'})).state,'legacy');
});
test('Invalid demand geometry and NaN prices fail safely',()=>{
  for(const p of [NaN,Infinity,0,-1,null])assert.equal(c(row({price:p})).nearCandidate,false);
  for(const z of [{low:0,high:99},{low:100,high:99},{low:99,high:99}])
    assert.equal(c(row({demand_zone:{...row().demand_zone,...z}})).nearCandidate,false);
});
test('Unknown boundary validity cannot be silently treated as clean',()=>{
  const dz={...row().demand_zone};delete dz.wick_breached;
  assert.equal(c(row({demand_zone:dz})).state,'invalid_demand');
});
test('Contradictory price beyond displayed supply asks for review',()=>{
  assert.equal(c(row({supply_zone:{...row().supply_zone,low:99.2,high:99.5}})).state,'passed_supply');
});
test('Thousands of deterministic randomized cases preserve all readiness gates',()=>{
  let seed=5;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
  for(let i=0;i<2500;i++){
    const p=30+random()*100,distance=random()*25;
    const r=early();r.price=p;r.score=random()*100;r.demand_zone.high=p*(1-distance/100);
    r.demand_zone.low=r.demand_zone.high-1;r.supply_zone.low=p*(1+random()*.2);
    r.supply_zone.high=r.supply_zone.low+1;r.demand_zone.wick_breached=random()<.1;
    const x=c(r);assert.ok(Number.isFinite(x.tier));
    if(x.nearCandidate){assert.ok(x.distancePct<=3);assert.ok(x.supplyRoomPct>2);assert.equal(r.demand_zone.wick_breached,false);}
    if(x.distancePct>3)assert.equal(x.nearCandidate,false);
  }
});
