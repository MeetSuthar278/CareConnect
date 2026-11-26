import {firebase} from './firebase-client.js';
import {beginVerification, authenticationError} from './registration-verification.js';

const form = document.getElementById('registration-recovery-form');
let busy = false;
form.addEventListener('submit', async event => {
  event.preventDefault();
  if (busy || !form.reportValidity()) return;
  busy = true;
  const button = form.querySelector('button');
  button.disabled = true;
  button.textContent = 'Signing in…';
  form.setAttribute('aria-busy', 'true');
  let provider;
  let started = false;
  try {
    provider = await firebase();
    const credential = await provider.sdk.signInWithEmailAndPassword(provider.auth, form.elements.email.value.trim(), form.elements.password.value);
    form.elements.password.value = '';
    const selected = new URLSearchParams(location.search).get('kind');
    started = true;
    await beginVerification(provider, credential.user, {kind: ['individual', 'organization'].includes(selected) ? selected : null});
  } catch (error) {
    const alert = document.createElement('div');
    alert.className = 'alert alert-danger';
    alert.setAttribute('role', 'alert');
    alert.textContent = authenticationError(error);
    document.getElementById('page-messages').replaceChildren(alert);
  } finally {
    form.elements.password.value = '';
    if (provider && !started) { try { await provider.sdk.signOut(provider.auth); } catch (_) { /* memory only */ } }
    busy = false;
    button.disabled = false;
    button.textContent = 'Continue registration';
    form.removeAttribute('aria-busy');
  }
});
