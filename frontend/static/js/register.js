import {firebase} from './firebase-client.js';
import {beginVerification} from './registration-verification.js';
import {attachPasswordValidation, firebasePasswordErrorMessage} from './registration-password.js';

const form = document.getElementById('registration-form');
const messages = document.getElementById('page-messages');
const button = form.querySelector('button[type="submit"]');
const passwordValidation = attachPasswordValidation(form);
let submitting = false;


function showMessage(text, success = false) {
  const alert = document.createElement('div');
  alert.className = `alert ${success ? 'alert-success' : 'alert-danger'}`;
  alert.setAttribute('role', success ? 'status' : 'alert');
  alert.textContent = text;
  messages.replaceChildren(alert);
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
  const buttonText = button.textContent;
  button.textContent = 'Creating account...';
  let provider;
  let verificationStarted = false;
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
    values.password = values.confirm_password = '';
    verificationStarted = true;
    await beginVerification(provider, credential.user, {kind: 'individual', data: profile});
  } catch (error) {
    const descriptions = {
      'auth/invalid-credential': 'Email or password is incorrect.',
      'auth/invalid-email': 'Enter a valid email address.',
      'auth/too-many-requests': 'Too many attempts. Please wait before retrying this form.',
      'auth/network-request-failed': 'Unable to connect. Please retry this form.',
      'auth/operation-not-allowed': 'Account registration is currently unavailable.',
      'auth/unauthorized-domain': 'Account registration is currently unavailable.',
    };
    showMessage(firebasePasswordErrorMessage(error.code) || descriptions[error.code] || (error.code || error.name === 'AbortError' || error instanceof TypeError
      ? 'Could not finish registration. Please retry this form.' : error.message));

  } finally {
    values.password = values.confirm_password = '';
    form.elements.password.value = form.elements.confirm_password.value = '';
    passwordValidation.update();
    if (provider && !verificationStarted) {
      try { await provider.sdk.signOut(provider.auth); } catch (_) { /* memory-only authentication */ }
    }
    submitting = false;
    button.disabled = false;
    button.textContent = buttonText;
    form.removeAttribute('aria-busy');
  }
});
