// Pending details, passwords and tokens are never persisted in browser storage.
const screen = document.getElementById('verification-screen');
const checkButton = document.getElementById('check-verification');
const resendButton = document.getElementById('resend-verification');
const completion = document.getElementById('registration-completion-form');
const kindSelect = document.getElementById('completion-kind');
let context;
let busy = false;
let resendAfter = 0;
let timer;

export function verificationMessage(text, success = false) {
  const alert = document.createElement('div');
  alert.className = `alert ${success ? 'alert-success' : 'alert-danger'}`;
  alert.setAttribute('role', success ? 'status' : 'alert');
  alert.textContent = text;
  document.getElementById('verification-messages').replaceChildren(alert);
}

export function authenticationError(error) {
  const messages = {
    'auth/invalid-credential': 'Email or password is incorrect.',
    'auth/user-not-found': 'Email or password is incorrect.',
    'auth/wrong-password': 'Email or password is incorrect.',
    'auth/invalid-email': 'Enter a valid email address.',
    'auth/too-many-requests': 'Too many attempts. Please wait before trying again.',
    'auth/network-request-failed': 'Unable to connect. Please try again.',
    'auth/user-token-expired': 'Your sign-in has expired. Return to finish registration and sign in again.',
    'auth/invalid-user-token': 'Your sign-in has expired. Return to finish registration and sign in again.',
    'auth/user-disabled': 'This account is unavailable. Contact CareConnect support.',
    'auth/expired-action-code': 'This verification link has expired. Request a new verification email.',
    'auth/invalid-action-code': 'This verification link is no longer valid. Request a new verification email.',
  };
  return messages[error.code] || error.userMessage || 'Unable to finish this step. Please retry. Your registration details are still on this page.';
}

function refreshButtons() {
  const remaining = Math.max(0, Math.ceil((resendAfter - Date.now()) / 1000));
  checkButton.disabled = busy;
  resendButton.disabled = busy || remaining > 0;
  completion.querySelector('button[type="submit"]').disabled = busy;
  document.getElementById('resend-cooldown').textContent = remaining ? `You can resend in ${remaining} seconds.` : '';
  if (!remaining && timer) { clearInterval(timer); timer = null; }
}

function cooldown() {
  resendAfter = Date.now() + 60000;
  if (timer) clearInterval(timer);
  timer = setInterval(refreshButtons, 1000);
  refreshButtons();
}

async function run(action, button, label) {
  if (busy) return;
  busy = true;
  const previous = button.textContent;
  button.textContent = label;
  screen.setAttribute('aria-busy', 'true');
  refreshButtons();
  try { await action(); }
  catch (error) {
    if (error.code === 'auth/too-many-requests') cooldown();
    verificationMessage(authenticationError(error));
  } finally {
    busy = false;
    button.textContent = previous;
    screen.removeAttribute('aria-busy');
    refreshButtons();
  }
}

async function sendVerification() {
  if (Date.now() < resendAfter) return;
  await context.provider.sdk.sendEmailVerification(context.user);
  cooldown();
  verificationMessage('Verification email sent. Check your inbox and spam folder, then open the newest link.', true);
}

async function backend(path, data, token) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(path, {
      method: data ? 'POST' : 'GET', cache: 'no-store', signal: controller.signal,
      headers: {Authorization: `Bearer ${token}`, ...(data ? {'Content-Type': 'application/json'} : {})},
      ...(data ? {body: JSON.stringify(data)} : {}),
    });
    const result = await response.json();
    if (!response.ok && result.code !== 'registration-required') {
      throw Object.assign(new Error(), {userMessage: result.error || 'Unable to complete registration. Please retry.'});
    }
    return result;
  } finally { clearTimeout(timeout); }
}

async function finished(kind) {
  await context.provider.sdk.signOut(context.provider.auth);
  context.data = null;
  window.location.assign(`/login?registered=${kind || 'verified'}`);
}

function chooseKind() {
  for (const fields of completion.querySelectorAll('[data-completion-kind]')) {
    fields.hidden = fields.dataset.completionKind !== kindSelect.value;
    fields.disabled = fields.hidden;
  }
  document.getElementById('completion-approval-note').hidden = kindSelect.value !== 'organization';
}

async function completeRegistration(token) {
  const kind = context.kind;
  const result = await backend(kind === 'organization' ? '/api/auth/register/organization' : '/api/auth/register/profile', context.data, token);
  if (result.status !== (kind === 'organization' ? 'submitted' : 'registered')) throw new Error();
  verificationMessage(kind === 'organization' ? 'Registration complete. Your organization is awaiting coordinator approval.' : 'Registration complete. You can now log in.', true);
  await finished(kind);
}

async function checkVerification() {
  await context.provider.sdk.reload(context.user);
  // Refreshing a user alone does not refresh cached ID-token claims.
  const token = await context.user.getIdToken(true);
  if (!context.user.emailVerified) {
    verificationMessage('Your email is not verified yet. Open the newest link in your inbox or spam folder, then try again.');
    return;
  }
  if (context.data) { await completeRegistration(token); return; }
  const account = await backend('/api/auth/me', null, token);
  if (account.code !== 'registration-required') { await finished(); return; }
  verificationMessage('Email verified. Complete the details below to finish registration.', true);
  completion.hidden = false;
  kindSelect.value = context.kind || 'individual';
  chooseKind();
  kindSelect.focus();
}

export async function beginVerification(provider, user, {kind = null, data = null} = {}) {
  context = {provider, user, kind, data};
  document.getElementById('auth-entry').hidden = true;
  document.getElementById('page-messages').replaceChildren();
  document.getElementById('verification-email').textContent = user.email;
  screen.hidden = false;
  history.replaceState({}, '', `/register/verify${kind ? `?kind=${kind}` : ''}`);
  document.getElementById('verification-heading').focus();
  if (user.emailVerified) await run(checkVerification, checkButton, 'Checking…');
  else await run(sendVerification, resendButton, 'Sending…');
}

checkButton.addEventListener('click', () => run(checkVerification, checkButton, 'Checking…'));
resendButton.addEventListener('click', () => run(sendVerification, resendButton, 'Sending…'));
kindSelect.addEventListener('change', chooseKind);
completion.addEventListener('submit', event => {
  event.preventDefault();
  if (!completion.reportValidity() || busy) return;
  const fields = completion.querySelector('[data-completion-kind]:not([disabled])');
  const data = Object.fromEntries([...fields.querySelectorAll('input')].map(field => [field.name, field.value.trim()]));
  if (!Object.values(data).every(Boolean)) { verificationMessage('Complete all required fields using more than spaces.'); return; }
  context.kind = kindSelect.value;
  context.data = data;
  run(checkVerification, completion.querySelector('button[type="submit"]'), 'Completing…');
});
