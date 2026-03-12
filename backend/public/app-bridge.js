(() => {
  const API = `${location.origin}/api`;
  let lastVideoSnapshot = null;
  let bootstrapped = false;

  function setLS(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  async function bootstrapState() {
    try {
      const res = await fetch(`${API}/bootstrap`);
      if (!res.ok) return;
      const data = await res.json();
      setLS('sv_users', data.users || []);
      setLS('sv_videos', data.videos || []);
      setLS('sv_code', (data.settings && data.settings.entryCode) || '1234');
      bootstrapped = true;
      if (typeof buildGenrePills === 'function') buildGenrePills();
      if (typeof renderGrid === 'function') renderGrid();
      if (typeof renderAdmin === 'function') renderAdmin();
    } catch (e) {
      console.warn('Bootstrap failed:', e);
    }
  }

  async function syncVideosIfChanged() {
    try {
      const snapshot = localStorage.getItem('sv_videos') || '[]';
      if (!bootstrapped || snapshot === lastVideoSnapshot) return;
      lastVideoSnapshot = snapshot;
      await fetch(`${API}/videos/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ videos: JSON.parse(snapshot) })
      });
    } catch (e) {
      console.warn('Video sync failed:', e);
    }
  }

  window.doLogin = async function doLoginPatched() {
    const email = document.getElementById('liEmail').value.trim().toLowerCase();
    const pass = document.getElementById('liPass').value;
    const err = document.getElementById('liErr');
    err.textContent = '';
    if (!email || !pass) {
      err.textContent = 'Fill in all fields';
      return;
    }
    try {
      const res = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password: pass })
      });
      const data = await res.json();
      if (!res.ok) {
        err.textContent = data.error || 'Login failed';
        return;
      }
      localStorage.setItem('sv_users', JSON.stringify(data.state.users || []));
      localStorage.setItem('sv_videos', JSON.stringify(data.state.videos || []));
      localStorage.setItem('sv_code', JSON.stringify((data.state.settings && data.state.settings.entryCode) || '1234'));
      saveSess({ id: data.user.id });
      launchApp(data.user);
    } catch (e) {
      err.textContent = 'Could not reach backend';
    }
  };

  window.doSignup = async function doSignupPatched() {
    const firstName = document.getElementById('suFirst').value.trim();
    const lastName = document.getElementById('suLast').value.trim();
    const email = document.getElementById('suEmail').value.trim().toLowerCase();
    const password = document.getElementById('suPass').value;
    const err = document.getElementById('suErr');
    err.textContent = '';
    if (!firstName || !email || !password) {
      err.textContent = 'Fill in required fields';
      return;
    }
    try {
      const res = await fetch(`${API}/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ firstName, lastName, email, password })
      });
      const data = await res.json();
      if (!res.ok) {
        err.textContent = data.error || 'Signup failed';
        return;
      }
      const note = data.devCode ? `${data.message}` : 'Check your email for the verification code.';
      const code = window.prompt(`${note}\n\nEnter the 6-digit code:` , data.devCode || '');
      if (!code) return;
      const verify = await fetch(`${API}/auth/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, code })
      });
      const verified = await verify.json();
      if (!verify.ok) {
        err.textContent = verified.error || 'Verification failed';
        return;
      }
      localStorage.setItem('sv_users', JSON.stringify(verified.state.users || []));
      document.getElementById('pendingCard').classList.remove('hidden');
      ['suFirst','suLast','suEmail','suPass'].forEach(id => document.getElementById(id).value = '');
      if (typeof toast === 'function') toast('Email verified. Waiting for admin approval.','g');
    } catch (e) {
      err.textContent = 'Could not reach backend';
    }
  };

  window.setStatus = async function setStatusPatched(id, status) {
    try {
      const res = await fetch(`${API}/admin/user-status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, status })
      });
      const data = await res.json();
      if (!res.ok) {
        if (typeof toast === 'function') toast(data.error || 'Status update failed', 'e');
        return;
      }
      localStorage.setItem('sv_users', JSON.stringify(data.state.users || []));
      renderAdmin();
      if (typeof toast === 'function') toast('User ' + (status === 'approved' ? 'approved ✓' : 'rejected'), status === 'approved' ? 's' : 'e');
    } catch (e) {
      if (typeof toast === 'function') toast('Backend unavailable', 'e');
    }
  };

  window.saveSettings = async function saveSettingsPatched() {
    const entryCode = document.getElementById('setCode').value.trim();
    const adminPassword = document.getElementById('setPass').value;
    try {
      const res = await fetch(`${API}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entryCode, adminPassword })
      });
      const data = await res.json();
      if (!res.ok) {
        if (typeof toast === 'function') toast(data.error || 'Save failed', 'e');
        return;
      }
      localStorage.setItem('sv_users', JSON.stringify(data.state.users || []));
      localStorage.setItem('sv_code', JSON.stringify((data.state.settings && data.state.settings.entryCode) || '1234'));
      document.getElementById('setCode').value = '';
      document.getElementById('setPass').value = '';
      if (typeof toast === 'function') toast('Settings updated', 's');
    } catch (e) {
      if (typeof toast === 'function') toast('Backend unavailable', 'e');
    }
  };

  function createFinderCard() {
    if (document.getElementById('providerFinderCard')) return;
    const grid = document.querySelector('#adminPage .admin-grid');
    if (!grid) return;
    const card = document.createElement('div');
    card.className = 'admin-card full';
    card.id = 'providerFinderCard';
    card.innerHTML = `
      <div class="card-ttl">Anime Finder</div>
      <div style="display:grid;grid-template-columns:220px 1fr auto;gap:10px;align-items:end;margin-bottom:14px">
        <div><label>Provider</label><select id="providerSel"><option value="hianime">HiAnime</option><option value="aniwatch">Aniwatch</option></select></div>
        <div><label>Search anime</label><input id="providerSearchInput" placeholder="Type an anime name"></div>
        <button class="btn btn-gold" id="providerSearchBtn">Search</button>
      </div>
      <div id="providerSearchStatus" style="font-size:12px;color:var(--muted);margin-bottom:10px"></div>
      <div id="providerResults" class="vid-list" style="max-height:260px"></div>
      <div id="providerEpisodes" class="vid-list" style="max-height:320px;margin-top:14px"></div>
    `;
    grid.prepend(card);

    const status = card.querySelector('#providerSearchStatus');
    const resultsEl = card.querySelector('#providerResults');
    const episodesEl = card.querySelector('#providerEpisodes');
    const searchBtn = card.querySelector('#providerSearchBtn');
    const input = card.querySelector('#providerSearchInput');
    const providerSel = card.querySelector('#providerSel');

    async function searchProvider() {
      const q = input.value.trim();
      if (!q) return;
      status.textContent = 'Searching...';
      resultsEl.innerHTML = '';
      episodesEl.innerHTML = '';
      try {
        const res = await fetch(`${API}/provider-search?q=${encodeURIComponent(q)}&provider=${encodeURIComponent(providerSel.value)}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Search failed');
        const items = data.results || [];
        status.textContent = `${items.length} result(s)`;
        if (!items.length) {
          resultsEl.innerHTML = '<div style="color:var(--muted);padding:12px">No results</div>';
          return;
        }
        resultsEl.innerHTML = items.map((item, idx) => `
          <div class="vid-item">
            <div class="vid-item-thumb" style="background-image:url('${item.cover || ''}');background-size:cover;background-position:center"></div>
            <div class="vid-item-info">
              <div class="vid-item-name">${item.title || 'Untitled'}</div>
              <div class="vid-item-meta">${item.url || ''}</div>
            </div>
            <div class="vid-item-acts"><button class="tact approve" data-idx="${idx}">Episodes</button></div>
          </div>
        `).join('');
        [...resultsEl.querySelectorAll('button[data-idx]')].forEach(btn => {
          btn.onclick = async () => {
            const item = items[Number(btn.dataset.idx)];
            status.textContent = 'Loading episodes...';
            episodesEl.innerHTML = '';
            const res2 = await fetch(`${API}/provider-episodes?provider=${encodeURIComponent(providerSel.value)}&url=${encodeURIComponent(item.url)}`);
            const data2 = await res2.json();
            if (!res2.ok) throw new Error(data2.error || 'Episode load failed');
            const eps = data2.episodes || [];
            status.textContent = `${eps.length} episode(s) found`;
            episodesEl.innerHTML = eps.map((ep, epIdx) => `
              <div class="vid-item">
                <div class="vid-item-thumb">▶</div>
                <div class="vid-item-info">
                  <div class="vid-item-name">${ep.title || `Episode ${ep.number || epIdx+1}`}</div>
                  <div class="vid-item-meta">${ep.url || ''}</div>
                </div>
                <div class="vid-item-acts"><button class="tact approve" data-epidx="${epIdx}">Import</button></div>
              </div>
            `).join('');
            [...episodesEl.querySelectorAll('button[data-epidx]')].forEach(epBtn => {
              epBtn.onclick = async () => {
                const ep = eps[Number(epBtn.dataset.epidx)];
                status.textContent = 'Extracting stream... this can take a while';
                epBtn.disabled = true;
                try {
                  const ext = await fetch(`${API}/extract`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: ep.url })
                  });
                  const extData = await ext.json();
                  if (!ext.ok) throw new Error(extData.error || 'Extraction failed');
                  if (!extData.best || !extData.best.url) throw new Error('No playable stream found');
                  switchSrc('stream');
                  document.getElementById('streamUrl').value = extData.best.url;
                  document.getElementById('sTitle').value = item.title || q;
                  document.getElementById('sEp').value = ep.title || `Ep ${ep.number || epIdx+1}`;
                  document.getElementById('sMeta').value = `${providerSel.value} import`;
                  addStreamUrl();
                  status.textContent = 'Imported successfully';
                } catch (err) {
                  status.textContent = err.message;
                  if (typeof toast === 'function') toast(err.message, 'e');
                } finally {
                  epBtn.disabled = false;
                }
              };
            });
          };
        });
      } catch (err) {
        status.textContent = err.message;
        if (typeof toast === 'function') toast(err.message, 'e');
      }
    }

    searchBtn.onclick = searchProvider;
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') searchProvider(); });
  }

  const originalShowPage = window.showPage;
  window.showPage = function showPagePatched(page) {
    const result = originalShowPage(page);
    if (page === 'admin') setTimeout(createFinderCard, 0);
    return result;
  };

  bootstrapState().then(() => {
    const sess = JSON.parse(localStorage.getItem('sv_sess') || 'null');
    if (sess && typeof launchApp === 'function' && document.getElementById('appScreen') && document.getElementById('appScreen').classList.contains('hidden')) {
      fetch(`${API}/auth/session/${encodeURIComponent(sess.id)}`)
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (data && data.user && data.user.status === 'approved') launchApp(data.user); })
        .catch(() => {});
    }
  });
  setInterval(syncVideosIfChanged, 1500);
})();
