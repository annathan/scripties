// DEFAULT_BACKEND must match background.js and content.js exactly.
const DEFAULT_BACKEND = 'https://api.safetybuddy.app';

async function getBackend() {
  return new Promise(resolve => chrome.storage.local.get(['backendUrl'], ({ backendUrl }) => {
    resolve(backendUrl || DEFAULT_BACKEND);
  }));
}

async function getApiKey() {
  return new Promise(resolve => chrome.storage.local.get(['apiKey'], ({ apiKey }) => resolve(apiKey || null)));
}

async function api(path, method = 'GET', body = null) {
  const [backend, key] = await Promise.all([getBackend(), getApiKey()]);
  const headers = { 'Content-Type': 'application/json' };
  if (key) headers['Authorization'] = `Bearer ${key}`;
  const res = await fetch(`${backend}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Request failed');
  return data;
}

function setMsg(elId, text, type = 'ok') {
  const el = document.getElementById(elId);
  el.textContent = text;
  el.className = `msg ${type}`;
}

// ---------------------------------------------------------------------------
// Auth section
// ---------------------------------------------------------------------------

document.getElementById('showRegister').addEventListener('click', () => {
  document.getElementById('loginSection').style.display = 'none';
  document.getElementById('registerSection').style.display = '';
});

document.getElementById('showLogin').addEventListener('click', () => {
  document.getElementById('loginSection').style.display = '';
  document.getElementById('registerSection').style.display = 'none';
});

document.getElementById('loginBtn').addEventListener('click', async () => {
  const email = document.getElementById('authEmail').value.trim();
  const password = document.getElementById('authPassword').value;
  if (!email || !password) return setMsg('authMsg', 'Please fill in both fields.', 'err');
  try {
    const data = await api('/auth/login', 'POST', { email, password });
    await chrome.storage.local.set({ apiKey: data.api_key });
    await showAccountView(data);
  } catch (e) {
    setMsg('authMsg', e.message, 'err');
  }
});

document.getElementById('registerBtn').addEventListener('click', async () => {
  const name = document.getElementById('regName').value.trim();
  const email = document.getElementById('regEmail').value.trim();
  const password = document.getElementById('regPassword').value;
  if (!email || !password) return setMsg('regMsg', 'Email and password are required.', 'err');
  if (password.length < 8) return setMsg('regMsg', 'Password must be at least 8 characters.', 'err');
  try {
    const data = await api('/auth/register', 'POST', { name, email, password });
    await chrome.storage.local.set({ apiKey: data.api_key });
    await showAccountView(data);
  } catch (e) {
    setMsg('regMsg', e.message, 'err');
  }
});

// ---------------------------------------------------------------------------
// Account view
// ---------------------------------------------------------------------------

async function cacheUserDetailsForWarningPage(name) {
  // warning.js reads guardianName from chrome.storage.local. Keep it current
  // so the warning page shows the right name without a server round-trip.
  const guardians = await api('/guardians').catch(() => []);
  const firstGuardianName = guardians[0]?.name || '';
  await chrome.storage.local.set({
    userName: name || '',
    guardianName: firstGuardianName,
  });
}

async function showAccountView(userData) {
  document.getElementById('authView').style.display = 'none';
  document.getElementById('accountView').style.display = '';

  const isPro = userData.plan === 'pro';
  const badge = document.getElementById('planBadge');
  badge.textContent = isPro ? 'Pro ✓' : 'Free';
  badge.className = 'plan-badge' + (isPro ? ' pro' : '');

  document.getElementById('hiLine').textContent = userData.name
    ? `Hi, ${userData.name}!`
    : `Hi! (${userData.email})`;

  document.getElementById('emailFeature').textContent = isPro ? '✓ On' : '— Free plan';
  document.getElementById('emailFeature').className = isPro ? 'feature-on' : 'feature-off';
  document.getElementById('smsFeature').textContent = isPro ? '✓ On' : '— Free plan';
  document.getElementById('smsFeature').className = isPro ? 'feature-on' : 'feature-off';

  document.getElementById('upgradeSection').style.display = isPro ? 'none' : '';
  document.getElementById('manageSection').style.display = isPro ? '' : 'none';
  document.getElementById('upgradeNudge').style.display = isPro ? 'none' : '';
  document.getElementById('addGuardianBtn').style.display = '';

  // Renewal banner for lifetime users whose AI checking has lapsed
  const renewalBanner = document.getElementById('renewalBanner');
  if (renewalBanner) {
    const showRenewal = isPro && userData.plan_type === 'lifetime' && !userData.api_checking_active;
    renewalBanner.style.display = showRenewal ? '' : 'none';
  }

  // Initialise plan picker price display
  updatePriceDisplay();

  await loadGuardians(isPro);
  await cacheUserDetailsForWarningPage(userData.name);
}

async function loadGuardians(isPro) {
  const list = document.getElementById('guardianList');
  list.innerHTML = '';
  let guardians = [];
  try {
    guardians = await api('/guardians');
  } catch {
    return;
  }

  const limit = isPro ? 5 : 1;
  document.getElementById('guardianCount').textContent = `(${guardians.length}/${limit})`;

  for (const g of guardians) {
    const item = document.createElement('div');
    item.className = 'guardian-item';
    item.innerHTML = `
      <div class="guardian-info">
        <div class="guardian-name">${escHtml(g.name || 'Unnamed')}</div>
        <div class="guardian-contact">${escHtml(g.email || '')}${g.phone ? '  📱' : ''}</div>
      </div>
      <button class="btn-danger" data-id="${escHtml(g.id)}">Remove</button>
    `;
    item.querySelector('.btn-danger').addEventListener('click', async () => {
      try {
        await api(`/guardians/${g.id}`, 'DELETE');
        await loadGuardians(isPro);
        await cacheUserDetailsForWarningPage(null);
      } catch (e) {
        alert(e.message);
      }
    });
    list.appendChild(item);
  }

  document.getElementById('addGuardianBtn').style.display = guardians.length >= limit ? 'none' : '';
}

// Add guardian form
document.getElementById('addGuardianBtn').addEventListener('click', () => {
  document.getElementById('addGuardianForm').style.display = '';
  document.getElementById('addGuardianBtn').style.display = 'none';
});

document.getElementById('cancelGuardianBtn').addEventListener('click', () => {
  document.getElementById('addGuardianForm').style.display = 'none';
  document.getElementById('addGuardianBtn').style.display = '';
  setMsg('guardianMsg', '');
});

document.getElementById('saveGuardianBtn').addEventListener('click', async () => {
  const name = document.getElementById('newGName').value.trim();
  const email = document.getElementById('newGEmail').value.trim();
  const phone = document.getElementById('newGPhone').value.trim();
  if (!name && !email) return setMsg('guardianMsg', 'Please enter a name or email.', 'err');
  try {
    await api('/guardians', 'POST', { name, email, phone });
    document.getElementById('addGuardianForm').style.display = 'none';
    document.getElementById('newGName').value = '';
    document.getElementById('newGEmail').value = '';
    document.getElementById('newGPhone').value = '';
    const me = await api('/account/me');
    await loadGuardians(me.plan === 'pro');
    await cacheUserDetailsForWarningPage(me.name);
  } catch (e) {
    setMsg('guardianMsg', e.message, 'err');
  }
});

// ---------------------------------------------------------------------------
// Plan picker
// ---------------------------------------------------------------------------

const PRICES = {
  personal_annual:   { label: '$9.99',  suffix: '/ year',  note: '' },
  family_annual:     { label: '$19.99', suffix: '/ year',  note: '' },
  personal_lifetime: { label: '$24.99', suffix: 'one-time', note: 'Includes 2 years of AI checking' },
  family_lifetime:   { label: '$49.99', suffix: 'one-time', note: 'Includes 2 years of AI checking' },
};

function selectedPlanKey() {
  const tier = document.querySelector('input[name="tier"]:checked')?.value || 'personal';
  const paytype = document.querySelector('input[name="paytype"]:checked')?.value || 'annual';
  return `${tier}_${paytype}`;
}

function updatePriceDisplay() {
  const key = selectedPlanKey();
  const p = PRICES[key];
  if (!p) return;
  document.getElementById('priceDisplay').innerHTML =
    `${escHtml(p.label)} <span>${escHtml(p.suffix)}</span>`;
  document.getElementById('apiNote').textContent = p.note;
}

['tierPersonal', 'tierFamily', 'payAnnual', 'payLifetime'].forEach(id => {
  document.getElementById(id)?.addEventListener('change', updatePriceDisplay);
});

document.getElementById('upgradeBtn').addEventListener('click', async () => {
  const plan_key = selectedPlanKey();
  try {
    const data = await api('/billing/checkout', 'POST', { plan_key });
    chrome.tabs.create({ url: data.url });
  } catch (e) {
    alert(e.message);
  }
});

document.getElementById('manageSubBtn').addEventListener('click', async () => {
  try {
    const data = await api('/billing/portal', 'POST');
    chrome.tabs.create({ url: data.url });
  } catch (e) {
    alert(e.message);
  }
});

document.getElementById('renewApiBtn')?.addEventListener('click', async () => {
  try {
    const data = await api('/billing/checkout', 'POST', { plan_key: 'api_renewal' });
    chrome.tabs.create({ url: data.url });
  } catch (e) {
    alert(e.message);
  }
});

document.getElementById('signOutBtn').addEventListener('click', async () => {
  await chrome.storage.local.remove(['apiKey', 'guardianName', 'userName']);
  document.getElementById('accountView').style.display = 'none';
  document.getElementById('authView').style.display = '';
  document.getElementById('loginSection').style.display = '';
  document.getElementById('registerSection').style.display = 'none';
  const badge = document.getElementById('planBadge');
  badge.textContent = 'Free';
  badge.className = 'plan-badge';
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function init() {
  const key = await getApiKey();
  if (!key) return;
  try {
    const me = await api('/account/me');
    await showAccountView(me);
  } catch {
    await chrome.storage.local.remove(['apiKey']);
  }
}

init();
