const KEYS = {
  codeVerifier: "ffsync_code_verifier",
  state: "ffsync_state",
  oidcConfig: "ffsync_oidc_config",
  fxaParams: "ffsync_fxa_params",
} as const

const AUTH_KEYS = {
  sessionToken: "ffsync_session_token",
  uid: "ffsync_uid",
  email: "ffsync_email",
} as const

export function storeCodeVerifier(verifier: string): void {
  sessionStorage.setItem(KEYS.codeVerifier, verifier)
}

export function getCodeVerifier(): string | null {
  return sessionStorage.getItem(KEYS.codeVerifier)
}

export function removeCodeVerifier(): void {
  sessionStorage.removeItem(KEYS.codeVerifier)
}

export function storeState(state: string): void {
  sessionStorage.setItem(KEYS.state, state)
}

export function getState(): string | null {
  return sessionStorage.getItem(KEYS.state)
}

export function removeState(): void {
  sessionStorage.removeItem(KEYS.state)
}

export function storeOIDCConfig(config: string): void {
  sessionStorage.setItem(KEYS.oidcConfig, config)
}

export function getOIDCConfig(): string | null {
  return sessionStorage.getItem(KEYS.oidcConfig)
}

export function storeFxAParams(params: string): void {
  sessionStorage.setItem(KEYS.fxaParams, params)
}

export function getFxAParams(): string | null {
  return sessionStorage.getItem(KEYS.fxaParams)
}

export function removeFxAParams(): void {
  sessionStorage.removeItem(KEYS.fxaParams)
}

export function storeAuth(sessionToken: string, uid: string, email: string): void {
  localStorage.setItem(AUTH_KEYS.sessionToken, sessionToken)
  localStorage.setItem(AUTH_KEYS.uid, uid)
  localStorage.setItem(AUTH_KEYS.email, email)
}

export function getAuth(): { sessionToken: string; uid: string; email: string } | null {
  const sessionToken = localStorage.getItem(AUTH_KEYS.sessionToken)
  const uid = localStorage.getItem(AUTH_KEYS.uid)
  const email = localStorage.getItem(AUTH_KEYS.email)
  if (!sessionToken || !uid || !email) return null
  return { sessionToken, uid, email }
}

export function clearAuth(): void {
  localStorage.removeItem(AUTH_KEYS.sessionToken)
  localStorage.removeItem(AUTH_KEYS.uid)
  localStorage.removeItem(AUTH_KEYS.email)
}

export function clearAll(): void {
  sessionStorage.removeItem(KEYS.codeVerifier)
  sessionStorage.removeItem(KEYS.state)
  sessionStorage.removeItem(KEYS.oidcConfig)
  sessionStorage.removeItem(KEYS.fxaParams)
  clearAuth()
}
