import {firebase} from './firebase-client.js';
import {beginVerification} from './registration-verification.js';
import {attachPasswordValidation, firebasePasswordErrorMessage} from './registration-password.js';

const form = document.getElementById('organization-registration-form');
const messages = document.getElementById('page-messages');
const button = form.querySelector('button[type="submit"]');
const passwordValidation = attachPasswordValidation(form);
const limits = {org_name:150, address:255, service_area:255, city:100, contact_name:100, phone:25};
let submitting = false;


function showMessage(text, success = false) {
  const alert = document.createElement('div');
  alert.className = `alert ${success ? 'alert-success' : 'alert-danger'}`;
  alert.setAttribute('role', success ? 'status' : 'alert');
  alert.textContent = text;
  messages.replaceChildren(alert);
  alert.scrollIntoView({block:'nearest'});
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (submitting) return;
  const passwordError = passwordValidation.validate();
  if (passwordError) {
    showMessage(passwordError);
    return;
  }
  if (!form.reportValidity()) return;
  const values = Object.fromEntries(new FormData(form));
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
  const buttonText = button.textContent;
  button.textContent = 'Creating account...';
  let provider;
  let verificationStarted = false;
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
    verificationStarted = true;
    await beginVerification(provider, credential.user, {kind: 'organization', data: application});
  } catch (error) {
    const descriptions = {
      'auth/invalid-credential':'Email or password is incorrect.',
      'auth/invalid-email':'Enter a valid email address.',
      'auth/too-many-requests':'Too many attempts. Wait before retrying with the same email and password.',
      'auth/network-request-failed':'Unable to connect. Retry with the same email and password.',
    };
    showMessage(firebasePasswordErrorMessage(error.code) || descriptions[error.code] || (error.code || error.name === 'AbortError' || error instanceof TypeError
      ? 'Could not finish registration. Retry with the same email, password and details.' : error.message));
  } finally {
    values.password = values.confirm_password = '';
    form.elements.password.value = form.elements.confirm_password.value = '';
    passwordValidation.update();
    if (provider && !verificationStarted) {
      try { await provider.sdk.signOut(provider.auth); } catch (_) { /* memory-only identity */ }
    }
    submitting = false;
    button.disabled = false;
    button.textContent = buttonText;
    form.removeAttribute('aria-busy');
  }
});
