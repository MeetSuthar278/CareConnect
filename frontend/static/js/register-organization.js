// Keep the team form and use Firebase only for identity and email verification.
const form = document.getElementById('organization-registration-form');
const messages = document.getElementById('page-messages');
const button = form.querySelector('button[type="submit"]');
const limits = {org_name:150, address:255, service_area:255, city:100, contact_name:100, phone:25};
let submitting = false;
let firebasePromise;

function showMessage(text, success = false) {
  const alert = document.createElement('div');
  alert.className = `alert ${success ? 'alert-success' : 'alert-danger'}`;
  alert.setAttribute('role', success ? 'status' : 'alert');
  alert.textContent = text;
  messages.replaceChildren(alert);
  alert.scrollIntoView({block:'nearest'});
}

async function firebase() {
  if (!firebasePromise) {
    firebasePromise = Promise.all([
      import('https://www.gstatic.com/firebasejs/12.0.0/firebase-app.js'),
      import('https://www.gstatic.com/firebasejs/12.0.0/firebase-auth.js'),
    ]).then(([appSDK, sdk]) => {
      const config = JSON.parse(document.getElementById('firebase-web-config').textContent);
      return {auth:sdk.getAuth(appSDK.initializeApp(config)), sdk};
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
  const application = Object.fromEntries(Object.keys(limits).map(key => [key, values[key].trim()]));
  if (!Object.entries(application).every(([key,value]) => value.length && value.length <= limits[key]) ||
      !/^[+0-9() .\-]{7,25}$/.test(application.phone) ||
      (application.phone.match(/[0-9]/g) || []).length < 7 ||
      (application.phone.match(/[0-9]/g) || []).length > 15) {
    showMessage('Check the organization and contact details.');
    return;
  }
  submitting = true;
  button.disabled = true;
  form.setAttribute('aria-busy','true');
  messages.replaceChildren();
  let provider;
  try {
    provider = await firebase();
    await provider.sdk.setPersistence(provider.auth,provider.sdk.inMemoryPersistence);
    let credential;
    try {
      credential = await provider.sdk.createUserWithEmailAndPassword(provider.auth,values.email.trim(),values.password);
    } catch (error) {
      if (error.code !== 'auth/email-already-in-use') throw error;
      credential = await provider.sdk.signInWithEmailAndPassword(provider.auth,values.email.trim(),values.password);
    }
    values.password = values.confirm_password = '';
    if (!credential.user.emailVerified) {
      await provider.sdk.sendEmailVerification(credential.user);
      showMessage('Verification email sent. Verify your email, then return to this form and submit again with the same details and password. Your application has not been submitted yet.',true);
      return;
    }
    const token = await credential.user.getIdToken(true);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(),12000);
    let response;
    try {
      response = await fetch('/api/auth/register/organization',{
        method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},
        body:JSON.stringify(application),cache:'no-store',signal:controller.signal,
      });
    } finally { clearTimeout(timeout); }
    let result;
    try { result = await response.json(); }
    catch (_) { throw new Error('Could not save your application. Retry with the same details.'); }
    if (!response.ok) throw new Error(result.error || 'Could not save your application. Retry with the same details.');
    if (result.status !== 'submitted') throw new Error('Could not confirm submission. Retry with the same details.');
    showMessage('Application submitted. You can log in to view its status. Coordinator approval is required before receiving referrals.',true);
  } catch (error) {
    const descriptions = {
      'auth/invalid-credential':'Email or password is incorrect.',
      'auth/weak-password':'Choose a stronger password.',
      'auth/invalid-email':'Enter a valid email address.',
      'auth/too-many-requests':'Too many attempts. Wait before retrying with the same email and password.',
      'auth/network-request-failed':'Unable to connect. Retry with the same email and password.',
    };
    showMessage(descriptions[error.code] || (error.code || error.name === 'AbortError' || error instanceof TypeError
      ? 'Could not finish registration. Retry with the same email, password and details.' : error.message));
  } finally {
    values.password = values.confirm_password = '';
    form.elements.password.value = form.elements.confirm_password.value = '';
    if (provider) {
      try { await provider.sdk.signOut(provider.auth); } catch (_) { /* memory-only identity */ }
    }
    submitting = false;
    button.disabled = false;
    form.removeAttribute('aria-busy');
  }
});
