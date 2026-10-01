const CACHE="maple-zones-v12";
const ASSETS=["./","index.html","style.css","readiness.js?v=3.6","app.js?v=3.6","manifest.json","icon.svg"];
self.addEventListener("install",e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).then(()=>self.skipWaiting()));
});
self.addEventListener("activate",e=>{
  e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith("maple-zones-")&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
self.addEventListener("fetch",e=>{
  if(e.request.method!=="GET")return;
  const url=new URL(e.request.url);
  if(url.origin!==self.location.origin||url.pathname.includes("/data/"))return;
  e.respondWith(fetch(e.request,{cache:"no-store"}).then(r=>{
    if(r.ok){const copy=r.clone();e.waitUntil(caches.open(CACHE).then(c=>c.put(e.request,copy)));}
    return r;
  }).catch(()=>caches.match(e.request).then(r=>r||Response.error())));
});
