const KEYS = {
  codeVerifier: "ffsync_code_verifier",
  state: "ffsync_state",
  oidcConfig: "ffsync_oidc_config",
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

export function clearAll(): void {
  sessionStorage.removeItem(KEYS.codeVerifier)
  sessionStorage.removeItem(KEYS.state)
  sessionStorage.removeItem(KEYS.oidcConfig)
}
