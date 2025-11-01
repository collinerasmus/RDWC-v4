(() => {
  const q  = (s) => document.querySelector(s);
  const el = (h) => { const d=document.createElement('div'); d.innerHTML=h.trim(); return d.firstChild; };

  async function getJSON(url){
    const r = await fetch(url, {cache:'no-store'});
    if (!r.ok) throw new Error('HTTP '+r.status+' for '+url);
    return r.json();
  }
  async function postJSON(url, body){
    const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    if (!r.ok) throw new Error('HTTP '+r.status+' for '+url);
    return r.json().catch(()=> ({}));
  }

  // --- Compatibility helpers -------------------------------------------------
  async function getRelayMap() {
    // Prefer plural, then singular. Fall back to reading keys from status.
    try { return await getJSON('/relays/map'); } catch(_){}
    try { return await getJSON('/relay/map'); } catch(_){}
    // No map endpoints; derive names from /relay/status keys
    const st = await getRelayState();
    const map = {};
    Object.keys(st).forEach(k => map[k] = k.replace(/_/g,' '));
    return map;
  }

  async function getRelayState() {
    // Try plural state
    try { return await getJSON('/relays/state'); } catch(_){}
    // Try singular state (if you have it)
    try { return await getJSON('/relay/state'); } catch(_){}
    // Fallback: /relay/status (your current server)
    // Expected shape: { lights:{state:true}, main_pump:{state:false}, ... }
    const status = await getJSON('/relay/status');
    const flat = {};
    Object.entries(status).forEach(([k,v]) => flat[k] = !!(v && v.state));
    return flat;
  }

  async function setRelay(key, desiredOn) {
    // Try modern POST with {name,on}
    try { return await postJSON('/relay/set', { name:key, on: !!desiredOn }); } catch(_){}
    // Try POST with {relay,state}
    try { return await postJSON('/relay/set', { relay:key, state: !!desiredOn }); } catch(_){}
    // Try GET with ?name=&on=
    try { return await getJSON(`/relay/set?name=${encodeURIComponent(key)}&on=${desiredOn?1:0}`); } catch(_){}
    // Try GET with ?relay=&state=
    return await getJSON(`/relay/set?relay=${encodeURIComponent(key)}&state=${desiredOn?1:0}`);
  }

  // --- UI --------------------------------------------------------------------
  function btnTemplate(key, name, on){
    const cls = on ? 'bg-green-600 hover:bg-green-700' : 'bg-red-600 hover:bg-red-700';
    const label = (on ? 'ON ' : 'OFF ') + name;
    return el(`<button data-relay="${key}" class="relay-btn ${cls} text-white rounded-xl py-2 px-3 w-full">${label}</button>`);
  }

  async function paint() {
    const grid = q('#relays-grid');
    if (!grid) return;
    grid.innerHTML = '<div class="text-gray-400 text-sm">Loading relays…</div>';

    const [map, state] = await Promise.all([getRelayMap(), getRelayState()]);
    grid.innerHTML = '';
    Object.keys(map).forEach(key => {
      const name = map[key] || key;
      const on = !!state[key];
      grid.appendChild(btnTemplate(key, name, on));
    });
    wire();
    const note = q('#relays-note');
    if (note) note.textContent = 'Click to toggle. State refreshes every 5s.';
  }

  function wire(){
    const grid = q('#relays-grid');
    if (!grid) return;
    grid.querySelectorAll('.relay-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const key = btn.getAttribute('data-relay');
        const wasOn = btn.textContent.startsWith('ON ');
        try{
          // Optimistic flip
          flipButton(btn, !wasOn);
          await setRelay(key, !wasOn);
          // Confirm with fresh state
          const st = await getRelayState();
          flipButton(btn, !!st[key]);
        }catch(e){
          console.error('toggle failed', e);
          // Revert optimistic change on error
          flipButton(btn, wasOn);
        }
      });
    });
  }

  function flipButton(btn, on){
    btn.textContent = (on ? 'ON ' : 'OFF ') + btn.textContent.replace(/^ON |^OFF /,'').trim();
    btn.classList.remove('bg-green-600','hover:bg-green-700','bg-red-600','hover:bg-red-700');
    if (on) {
      btn.classList.add('bg-green-600','hover:bg-green-700');
    } else {
      btn.classList.add('bg-red-600','hover:bg-red-700');
    }
  }

  async function periodicRefresh(){
    try{
      const st = await getRelayState();
      document.querySelectorAll('#relays-grid .relay-btn').forEach(btn => {
        const key = btn.getAttribute('data-relay');
        if (key in st) flipButton(btn, !!st[key]);
      });
    }catch(e){ console.debug('refresh skipped', e); }
  }

  document.addEventListener('DOMContentLoaded', () => {
    paint().catch(err => {
      const grid = q('#relays-grid');
      if (grid) grid.innerHTML = `<div class="text-red-400 text-sm">Relays failed to load: ${String(err)}</div>`;
      console.error(err);
    });
    setInterval(periodicRefresh, 5000);
  });
})();
