import { clearPairingCustody } from "@/lib/pairing-custody"

const KEYS = {
  codeVerifier: "ffsync_code_verifier",
  state: "ffsync_state",
  oidcConfig: "ffsync_oidc_config",
  fxaParams: "ffsync_fxa_params",
  pairPending: "ffsync_pair_pending",
} as const

// Session-scoped, never persisted to disk or shared across tabs: FxA keeps its
// account/session data in sessionStorage too, and only the theme in localStorage.
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
  sessionStorage.setItem(AUTH_KEYS.sessionToken, sessionToken)
  sessionStorage.setItem(AUTH_KEYS.uid, uid)
  sessionStorage.setItem(AUTH_KEYS.email, email)
}

export function getAuth(): { sessionToken: string; uid: string; email: string } | null {
  const sessionToken = sessionStorage.getItem(AUTH_KEYS.sessionToken)
  const uid = sessionStorage.getItem(AUTH_KEYS.uid)
  const email = sessionStorage.getItem(AUTH_KEYS.email)
  if (!sessionToken || !uid || !email) return null
  return { sessionToken, uid, email }
}

export function clearAuth(): void {
  sessionStorage.removeItem(AUTH_KEYS.sessionToken)
  sessionStorage.removeItem(AUTH_KEYS.uid)
  sessionStorage.removeItem(AUTH_KEYS.email)
  clearPairingCustody()
}

// Key custody only exists in the document whose sign-in flow set it, so a
// pairing bounce records its intent here and returns to /pair client-side.
export function storePairingPending(): void {
  sessionStorage.setItem(KEYS.pairPending, "1")
}

export function consumePairingPending(): boolean {
  const pending = sessionStorage.getItem(KEYS.pairPending) === "1"
  if (pending) sessionStorage.removeItem(KEYS.pairPending)
  return pending
}

export function clearAll(): void {
  sessionStorage.removeItem(KEYS.codeVerifier)
  sessionStorage.removeItem(KEYS.state)
  sessionStorage.removeItem(KEYS.oidcConfig)
  sessionStorage.removeItem(KEYS.fxaParams)
  sessionStorage.removeItem(KEYS.pairPending)
  clearAuth()
}
