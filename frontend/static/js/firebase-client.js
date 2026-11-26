// SDK authentication stays in memory. Flask owns authenticated browser cookies.
let pending;
export async function firebase() {
  if (!pending) {
    pending = Promise.all([
      import('https://www.gstatic.com/firebasejs/12.0.0/firebase-app.js'),
      import('https://www.gstatic.com/firebasejs/12.0.0/firebase-auth.js'),
    ]).then(async ([appSDK, sdk]) => {
      const config = JSON.parse(document.getElementById('firebase-web-config').textContent);
      const app = appSDK.initializeApp(config);
      const auth = sdk.getAuth(app);
      await sdk.setPersistence(auth, sdk.inMemoryPersistence);
      return {auth, sdk};
    }).catch(error => { pending = null; throw error; });
  }
  return pending;
}
