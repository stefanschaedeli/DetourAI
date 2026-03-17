'use strict';

// ---------------------------------------------------------------------------
// In-memory token store — never persisted to localStorage/sessionStorage
// ---------------------------------------------------------------------------
let _accessToken = null;          // JWT, lives 15 min
let _refreshPromise = null;       // single in-flight refresh promise (serialises concurrent 401s)

function authGetToken() {
  return _accessToken;
}

function authSetToken(token) {
  _accessToken = token;
}

function authClearToken() {
  _accessToken = null;
}

// ---------------------------------------------------------------------------
// Silent refresh — serialised so concurrent 401s only fire one request
// ---------------------------------------------------------------------------

async function authSilentRefresh() {
  if (_refreshPromise) return _refreshPromise;

  _refreshPromise = (async () => {
    try {
      const res = await fetch('/api/auth/refresh', {
        method: 'POST',
        credentials: 'include',   // send HTTP-only refresh cookie
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
        authClearToken();
        S.currentUser = null;
        return null;
      }
      const data = await res.json();
      authSetToken(data.access_token);
      return data.access_token;
    } catch (_) {
      authClearToken();
      S.currentUser = null;
      return null;
    } finally {
      _refreshPromise = null;
    }
  })();

  return _refreshPromise;
}

// ---------------------------------------------------------------------------
// Login / Logout helpers (called from UI layer)
// ---------------------------------------------------------------------------

async function authLogin(username, password) {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Anmeldung fehlgeschlagen');
  }
  const data = await res.json();
  authSetToken(data.access_token);

  // Fetch user info and store in global state
  const meRes = await fetch('/api/auth/me', {
    credentials: 'include',
    headers: { Authorization: `Bearer ${_accessToken}` },
  });
  if (meRes.ok) {
    S.currentUser = await meRes.json();
  }
  return S.currentUser;
}

async function authLogout() {
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...((_accessToken) ? { Authorization: `Bearer ${_accessToken}` } : {}),
      },
    });
  } catch (_) { /* best-effort */ }
  authClearToken();
  S.currentUser = null;
}

// ---------------------------------------------------------------------------
// Restore session on page load (try silent refresh with existing cookie)
// ---------------------------------------------------------------------------

async function authRestoreSession() {
  const token = await authSilentRefresh();
  if (!token) return null;

  const meRes = await fetch('/api/auth/me', {
    credentials: 'include',
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!meRes.ok) {
    authClearToken();
    S.currentUser = null;
    return null;
  }
  S.currentUser = await meRes.json();
  return S.currentUser;
}
