// Password inputs intentionally have no names: native fallback cannot post them to Flask.
const form=document.getElementById('password-change-form');
const messages=document.getElementById('page-messages');
const fields=['old_password','password','confirm_password'].map(id=>form.querySelector('#'+id));
const button=form.querySelector('button[type="submit"]');
let submitting=false;
let firebasePromise;

function show(text,success=false) {
  const alert=document.createElement('div');
  alert.className=`alert ${success ? 'alert-success' : 'alert-danger'}`;
  alert.setAttribute('role',success ? 'status' : 'alert');
  alert.textContent=text;
  messages.replaceChildren(alert);
  alert.scrollIntoView({block:'nearest'});
}

async function firebase() {
  if (!firebasePromise) {
    firebasePromise=Promise.all([
      import('https://www.gstatic.com/firebasejs/12.0.0/firebase-app.js'),
      import('https://www.gstatic.com/firebasejs/12.0.0/firebase-auth.js'),
    ]).then(([appSDK,sdk])=>({sdk,auth:sdk.getAuth(appSDK.initializeApp(
      JSON.parse(document.getElementById('firebase-web-config').textContent)))}))
      .catch(error=>{firebasePromise=null;throw error;});
  }
  return firebasePromise;
}

async function call(url,options={}) {
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),12000);
  try {
    const response=await fetch(url,{...options,credentials:'same-origin',cache:'no-store',signal:controller.signal});
    if (response.redirected) throw new Error('Sign in again before changing your password.');
    let data;
    try {data=await response.json();} catch (_) {throw new Error('Account service unavailable. Please retry.');}
    if (!response.ok) throw new Error(data.error || 'Account service unavailable. Please retry.');
    return data;
  } finally {clearTimeout(timer);}
}

form.addEventListener('submit',async event=>{
  event.preventDefault();
  if (submitting || !form.reportValidity()) return;
  if (fields[1].value!==fields[2].value) {show('Passwords do not match.');return;}
  if (fields[0].value===fields[1].value) {show('Choose a new password different from your current password.');return;}
  submitting=true;button.disabled=true;form.setAttribute('aria-busy','true');
  let provider;
  let changed=false;
  try {
    const identity=await call(form.dataset.contextUrl);
    if (typeof identity.uid!=='string' || !identity.uid || typeof identity.email!=='string' || !identity.email) {
      throw new Error('Sign in again before changing your password.');
    }
    provider=await firebase();
    await provider.sdk.setPersistence(provider.auth,provider.sdk.inMemoryPersistence);
    const credential=await provider.sdk.signInWithEmailAndPassword(provider.auth,identity.email,fields[0].value);
    if (credential.user.uid!==identity.uid) throw new Error('Account changed. Sign in again before retrying.');
    // Fresh password sign-in satisfies Firebase's recent-authentication requirement.
    await provider.sdk.updatePassword(credential.user,fields[1].value);
    changed=true;
    show('Password changed. Sign in again with your new password.',true);
  } catch (error) {
    const descriptions={
      'auth/invalid-credential':'Current password is incorrect.',
      'auth/wrong-password':'Current password is incorrect.',
      'auth/weak-password':'Choose a stronger new password.',
      'auth/password-does-not-meet-requirements':'Choose a new password that meets the account password policy.',
      'auth/requires-recent-login':'Sign in again before changing your password.',
      'auth/too-many-requests':'Too many attempts. Wait before retrying.',
      'auth/network-request-failed':'Unable to connect. Please retry.',
    };
    show(descriptions[error.code] || (error.code || error.name==='AbortError' || error instanceof TypeError
      ? 'Unable to change your password. Please retry.' : error.message));
  } finally {
    fields.forEach(field=>{field.value='';});
    if (provider) {try {await provider.sdk.signOut(provider.auth);} catch (_) { /* memory-only session */ }}
    if (changed) {
      try {
        await call('/api/auth/logout-browser',{method:'POST',headers:{'X-CSRF-Token':form.querySelector('[name="csrf_token"]').value}});
      } catch (_) {show('Password changed. Sign in again with your new password before continuing.',true);}
      // Never retry an already-successful password change with the old password.
      window.setTimeout(()=>window.location.assign('/login'),1200);
    } else {button.disabled=false;submitting=false;form.removeAttribute('aria-busy');}
  }
});
