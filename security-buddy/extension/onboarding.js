const DEFAULT_BACKEND = 'https://api.safetybuddy.app';

async function getBackend() {
  return new Promise(resolve =>
    chrome.storage.local.get(['backendUrl'], ({ backendUrl }) =>
      resolve(backendUrl || DEFAULT_BACKEND)
    )
  );
}

async function api(path, method = 'GET', body = null) {
  const [backend, { apiKey }] = await Promise.all([
    getBackend(),
    new Promise(resolve => chrome.storage.local.get(['apiKey'], resolve)),
  ]);
  const headers = { 'Content-Type': 'application/json' };
  if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`;
  const res = await fetch(`${backend}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Request failed');
  return data;
}

function setMsg(id, text) {
  document.getElementById(id).textContent = text;
}

function show(id) {
  ['screenRegister', 'screenSignIn', 'screenGuardian', 'screenDone'].forEach(s => {
    document.getElementById(s).style.display = s === id ? '' : 'none';
  });
}

// The name of the person being protected — set after registration or sign-in.
let protectedName = '';

// ---------------------------------------------------------------------------
// Register
// ---------------------------------------------------------------------------

document.getElementById('regBtn').addEventListener('click', async () => {
  const name     = document.getElementById('regName').value.trim();
  const email    = document.getElementById('regEmail').value.trim();
  const password = document.getElementById('regPassword').value;

  if (!name)             return setMsg('regMsg', 'Please enter your name.');
  if (!email)            return setMsg('regMsg', 'Please enter your email.');
  if (password.length < 8) return setMsg('regMsg', 'Password must be at least 8 characters.');

  document.getElementById('regBtn').textContent = 'Setting up…';
  document.getElementById('regBtn').disabled = true;

  try {
    const data = await api('/auth/register', 'POST', { name, email, password });
    await chrome.storage.local.set({ apiKey: data.api_key, userName: name });
    protectedName = name;
    show('screenGuardian');
  } catch (e) {
    setMsg('regMsg', e.message);
    document.getElementById('regBtn').textContent = 'Continue →';
    document.getElementById('regBtn').disabled = false;
  }
});

// ---------------------------------------------------------------------------
// Sign in (reinstalls / returning users)
// ---------------------------------------------------------------------------

document.getElementById('showSignIn').addEventListener('click', () => show('screenSignIn'));
document.getElementById('showRegister').addEventListener('click', () => show('screenRegister'));

document.getElementById('siBtn').addEventListener('click', async () => {
  const email    = document.getElementById('siEmail').value.trim();
  const password = document.getElementById('siPassword').value;

  if (!email || !password) return setMsg('siMsg', 'Please fill in both fields.');

  document.getElementById('siBtn').textContent = 'Signing in…';
  document.getElementById('siBtn').disabled = true;

  try {
    const data = await api('/auth/login', 'POST', { email, password });
    await chrome.storage.local.set({ apiKey: data.api_key, userName: data.name || '' });
    protectedName = data.name || '';
    show('screenGuardian');
  } catch (e) {
    setMsg('siMsg', e.message);
    document.getElementById('siBtn').textContent = 'Sign in';
    document.getElementById('siBtn').disabled = false;
  }
});

// ---------------------------------------------------------------------------
// Guardian
// ---------------------------------------------------------------------------

async function finishWithGuardian(guardianName) {
  const nameDisplay  = escHtml(protectedName || 'you');
  const guardDisplay = escHtml(guardianName);

  if (guardianName) {
    document.getElementById('doneHeadline').textContent =
      `${guardianName} is now watching over ${protectedName || 'you'}.`;
    document.getElementById('doneDetail').textContent =
      `If ${protectedName || 'you'} click something dangerous online, ${guardianName} will get a message immediately.`;
    document.getElementById('safeNote').innerHTML =
      `Safety Buddy works automatically in the background — you don't need to do anything. ` +
      `<strong>${guardDisplay}</strong> will only hear from us if something looks wrong.`;
  } else {
    document.getElementById('doneHeadline').textContent =
      `${protectedName || 'You'} ${protectedName ? 'are' : 'are'} now protected.`;
    document.getElementById('doneDetail').textContent =
      `Safety Buddy will check links before you visit them and warn you if something looks wrong.`;
    document.getElementById('safeNote').innerHTML =
      `You can add a family contact anytime from the Safety Buddy icon in your browser toolbar. ` +
      `They'll be notified if you ever click something dangerous.`;
  }

  show('screenDone');
}

document.getElementById('gBtn').addEventListener('click', async () => {
  const name  = document.getElementById('gName').value.trim();
  const email = document.getElementById('gEmail').value.trim();
  const phone = document.getElementById('gPhone').value.trim();

  if (!name && !email) return setMsg('gMsg', 'Please enter at least a name or email for your contact.');

  document.getElementById('gBtn').textContent = 'Setting up…';
  document.getElementById('gBtn').disabled = true;

  try {
    await api('/guardians', 'POST', { name, email, phone });
    await chrome.storage.local.set({ guardianName: name });
    await finishWithGuardian(name);
  } catch (e) {
    setMsg('gMsg', e.message);
    document.getElementById('gBtn').textContent = 'Set up Safety Buddy →';
    document.getElementById('gBtn').disabled = false;
  }
});

document.getElementById('gSkipBtn').addEventListener('click', () => finishWithGuardian(''));

// ---------------------------------------------------------------------------
// Done
// ---------------------------------------------------------------------------

document.getElementById('doneBtn').addEventListener('click', () => window.close());

// ---------------------------------------------------------------------------
// Init — skip screens if the user is already partially or fully set up
// ---------------------------------------------------------------------------

async function init() {
  const { apiKey, userName, guardianName } = await new Promise(resolve =>
    chrome.storage.local.get(['apiKey', 'userName', 'guardianName'], resolve)
  );

  if (apiKey && guardianName) {
    // Fully set up — show confirmation so they know everything is active
    protectedName = userName || '';
    await finishWithGuardian(guardianName);
  } else if (apiKey) {
    // Registered but no guardian yet
    protectedName = userName || '';
    show('screenGuardian');
  }
  // Otherwise: default register screen is already visible
}

init();
