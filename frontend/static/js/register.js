// Integrate the existing team form without changing its fields or design.
const form = document.getElementById('registration-form');
const messages = document.getElementById('page-messages');
const button = form.querySelector('button[type="submit"]');
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
    ]).then(([appSDK, sdk]) => {
      const config = JSON.parse(document.getElementById('firebase-web-config').textContent);
      return {auth: sdk.getAuth(appSDK.initializeApp(config)), sdk};
    }).catch(error => { firebasePromise = null; throw error; });
  }
  return firebasePromise;
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (submitting || !form.reportValidity()) return;
  const values = Object.fromEntries(new FormData(form));
  if (values.password !== values.confirm_password) {
    showMessage('Passwords do not match.');
    return;
  }
  const profile = Object.fromEntries(['full_name', 'phone', 'address', 'city'].map(key => [key, values[key].trim()]));
  const [firstName, ...lastNames] = profile.full_name.split(/\s+/);
  if (!Object.values(profile).every(Boolean) || profile.full_name.length > 101 ||
      profile.address.length > 255 || profile.city.length > 100 ||
      firstName.length > 50 || lastNames.join(' ').length > 50 ||
      (profile.phone.match(/[0-9]/g) || []).length < 7 ||
      (profile.phone.match(/[0-9]/g) || []).length > 15) {
    showMessage('Check your name, phone, address and city.');
    return;
  }
  submitting = true;
  button.disabled = true;
  form.setAttribute('aria-busy', 'true');
  messages.replaceChildren();
  let provider;
  let accountExists = false;
  try {
    provider = await firebase();
    await provider.sdk.setPersistence(provider.auth, provider.sdk.inMemoryPersistence);
    let credential;
    try {
      credential = await provider.sdk.createUserWithEmailAndPassword(provider.auth, values.email.trim(), values.password);
    } catch (error) {
      if (error.code !== 'auth/email-already-in-use') throw error;
      // Recover a prior signup only by authenticating with its actual password.
      credential = await provider.sdk.signInWithEmailAndPassword(provider.auth, values.email.trim(), values.password);
    }
    accountExists = true;
    values.password = values.confirm_password = '';
    // Individual members finish registration without an email-verification step.
    const token = await credential.user.getIdToken(true);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    let response;
    try {
      response = await fetch('/api/auth/register/profile', {
        method: 'POST', headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'},
        body: JSON.stringify(profile), cache: 'no-store', signal: controller.signal,
      });
    } finally { clearTimeout(timeout); }
    let result;
    try { result = await response.json(); }
    catch (_) { throw new Error('Could not save your profile. Please retry this form.'); }
    if (!response.ok) throw new Error(result.error || 'Could not finish registration. Please retry.');
    if (result.status !== 'registered') throw new Error('Could not confirm registration. Please retry.');
    showMessage('Registration complete. You can now log in.', true);
  } catch (error) {
    const descriptions = {
      'auth/invalid-credential': 'Email or password is incorrect.',
      'auth/weak-password': 'Choose a stronger password.',
      'auth/invalid-email': 'Enter a valid email address.',
      'auth/too-many-requests': 'Too many attempts. Please wait before retrying this form.',
      'auth/network-request-failed': 'Unable to connect. Please retry this form.',
      'auth/operation-not-allowed': 'Account registration is currently unavailable.',
      'auth/unauthorized-domain': 'Account registration is currently unavailable.',
    };
    showMessage(descriptions[error.code] || (error.code || error.name === 'AbortError' || error instanceof TypeError
      ? 'Could not finish registration. Please retry this form.' : error.message));
    // Account creation and email delivery are separate Firebase operations.
    if (accountExists && error.code && error.code !== 'auth/invalid-credential') {
      showMessage('Your account exists, but registration is not finished. Please wait, then retry this form with the same email and password.');
    }
  } finally {
    values.password = values.confirm_password = '';
    form.elements.password.value = form.elements.confirm_password.value = '';
    if (provider) {
      try { await provider.sdk.signOut(provider.auth); } catch (_) { /* memory-only authentication */ }
    }
    submitting = false;
    button.disabled = false;
    form.removeAttribute('aria-busy');
  }
});
