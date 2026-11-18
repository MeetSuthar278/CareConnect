// Bind the team's existing form. No new fields, labels or layout are introduced.
const form = document.getElementById('login-form');
const email = document.getElementById('email');
const password = document.getElementById('password');
const button = form.querySelector('button[type="submit"]');
const messages = document.getElementById('page-messages');
let submitting = false;
let firebasePromise;

function showMessage(text, success = false) {
  const alert = document.createElement('div');
  alert.className = `alert ${success ? 'alert-success' : 'alert-danger'}`;
  alert.setAttribute('role', success ? 'status' : 'alert');
  alert.textContent = text;
  messages.replaceChildren(alert);
}

async function firebase() {
  if (!firebasePromise) {
    firebasePromise = Promise.all([
      import('https://www.gstatic.com/firebasejs/12.0.0/firebase-app.js'),
      import('https://www.gstatic.com/firebasejs/12.0.0/firebase-auth.js'),
    ]).then(([appSDK, authSDK]) => {
      const config = JSON.parse(document.getElementById('firebase-web-config').textContent);
      const app = appSDK.initializeApp(config);
      return {auth: authSDK.getAuth(app), sdk: authSDK};
    }).catch(error => { firebasePromise = null; throw error; });
  }
  return firebasePromise;
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (submitting || !form.reportValidity()) return;
  submitting = true;
  button.disabled = true;
  form.setAttribute('aria-busy', 'true');
  messages.replaceChildren();
  let provider;
  let backendVerified = false;
  try {
    provider = await firebase();
    // Browser SDK credentials stay in memory; supported roles get an HttpOnly server cookie.
    await provider.sdk.setPersistence(provider.auth, provider.sdk.inMemoryPersistence);
    const credential = await provider.sdk.signInWithEmailAndPassword(
      provider.auth, email.value.trim(), password.value);
    password.value = '';
    // The backend applies email verification using the account's SQL-owned role.
    const token = await credential.user.getIdToken(true);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    let response;
    try {
      response = await fetch('/api/auth/me', {
        headers: {Authorization: `Bearer ${token}`},
        cache: 'no-store', signal: controller.signal,
      });
    } finally { clearTimeout(timeout); }
    let account;
    try { account = await response.json(); }
    catch (_) { throw new Error('Unable to verify your account. Please try again.'); }
    if (!response.ok) throw new Error(account.error || 'Unable to verify your account.');
    if (!Number.isInteger(account.user_id) ||
        !['member', 'representative', 'coordinator'].includes(account.role)) {
      throw new Error('Unable to verify your account. Please try again.');
    }
    if (['member', 'representative', 'coordinator'].includes(account.role)) {
      const destinations = {
        member: ['/api/auth/session', '/member'],
        representative: ['/api/auth/organization-session', '/organization'],
        coordinator: ['/api/auth/coordinator-session', '/coordinator'],
      };
      const [sessionUrl, destination] = destinations[account.role];
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 12000);
      let sessionResponse;
      try {
        sessionResponse = await fetch(sessionUrl, {
          method: 'POST', cache: 'no-store', signal: controller.signal,
          headers: {Authorization: `Bearer ${token}`,
            'X-CSRF-Token': JSON.parse(document.getElementById('login-csrf').textContent)},
        });
      } finally { clearTimeout(timeout); }
      const result = await sessionResponse.json();
      if (!sessionResponse.ok) throw new Error(result.error || 'Unable to start your session.');
      if (result.redirect_url !== destination) throw new Error('Unable to start your session.');
      backendVerified = true;
      try { await provider.sdk.signOut(provider.auth); } catch (_) { /* server session owns navigation */ }
      window.location.assign(destination);
      return;
    }
  } catch (error) {
    const descriptions = {
      'auth/invalid-credential': 'Email or password is incorrect.',
      'auth/user-not-found': 'Email or password is incorrect.',
      'auth/wrong-password': 'Email or password is incorrect.',
      'auth/too-many-requests': 'Too many attempts. Please try again later.',
      'auth/network-request-failed': 'Unable to connect. Please try again.',
      'auth/operation-not-allowed': 'Sign-in is currently unavailable.',
      'auth/unauthorized-domain': 'Sign-in is currently unavailable.',
    };
    showMessage(descriptions[error.code] ||
      (error.name === 'AbortError' || error instanceof TypeError
        ? 'Unable to connect. Please try again.'
        : error.code ? 'Sign-in failed. Please try again.' : error.message));
  } finally {
    password.value = '';
    if (provider && !backendVerified) {
      try { await provider.sdk.signOut(provider.auth); } catch (_) { /* no session authorized */ }
    }
    submitting = false;
    button.disabled = false;
    form.removeAttribute('aria-busy');
  }
});
