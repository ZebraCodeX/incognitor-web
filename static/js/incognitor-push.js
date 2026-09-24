// Incognitor Web Push registration. Registers the service worker and, once the
// user grants permission, subscribes this browser to VAPID push.
(function () {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;

  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[2]) : "";
  }

  function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = atob(base64);
    const output = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) output[i] = raw.charCodeAt(i);
    return output;
  }

  async function postSubscription(sub) {
    const json = sub.toJSON();
    await fetch("/api/push/subscribe/", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({
        endpoint: json.endpoint,
        keys: json.keys,
      }),
    });
  }

  async function registration() {
    return navigator.serviceWorker.register("/sw.js", { scope: "/" });
  }

  async function publicKey() {
    const resp = await fetch("/api/push/vapid_public_key/", {
      credentials: "same-origin",
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    return data.enabled && data.public_key ? data.public_key : null;
  }

  async function ensureSubscribed(key) {
    const reg = await registration();
    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(key),
      });
    }
    await postSubscription(sub);
    return sub;
  }

  // Called from a user gesture (button) so the permission prompt is allowed.
  window.incognitorEnablePush = async function () {
    try {
      if (Notification.permission !== "granted") {
        const perm = await Notification.requestPermission();
        if (perm !== "granted") return { ok: false, reason: "denied" };
      }
      const key = await publicKey();
      if (!key) return { ok: false, reason: "not_configured" };
      await ensureSubscribed(key);
      return { ok: true };
    } catch (e) {
      return { ok: false, reason: String(e) };
    }
  };

  // On load: register quietly and refresh an existing subscription.
  (async function () {
    try {
      await registration();
      if (Notification.permission !== "granted") return;
      const key = await publicKey();
      if (key) await ensureSubscribed(key);
    } catch (e) {
      /* non-fatal */
    }
  })();
})();
