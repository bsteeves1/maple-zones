const CACHE="maple-zones-v9";
const ASSETS=["./","index.html","style.css","app.js","manifest.json","icon.svg"];
self.addEventListener("install",e=>{
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)));
});
self.addEventListener("activate",e=>{
  e.waitUntil(Promise.all([
    self.clients.claim(),
    caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))))
  ]));
});
self.addEventListener("fetch",e=>{
  if(e.request.method!=="GET")return;
  if(e.request.url.includes("/data/")||e.request.url.includes("raw.githubusercontent.com"))return;
  e.respondWith(
    fetch(e.request,{cache:"no-store"})
      .then(r=>{const copy=r.clone();caches.open(CACHE).then(c=>c.put(e.request,copy));return r;})
      .catch(()=>caches.match(e.request))
  );
});