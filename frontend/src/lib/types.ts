export interface AppConfig {
  oidcProviderUrl: string
  clientId: string
  redirectUri: string
  tokenServerUrl: string
  scopes: string[]
}

export interface OIDCConfiguration {
  issuer: string
  authorizationEndpoint: string
  tokenEndpoint: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  scope?: string
  id_token?: string
  refresh_token?: string
}

export interface OAuthError {
  error: string
  error_description?: string
}

export type AppState =
  | { kind: "initializing" }
  | { kind: "landing" }
  | { kind: "processing"; message: string }
  | { kind: "success"; tokenServerUri: string }
  | { kind: "error"; title: string; message: string; details?: string }

export interface BrowserCompatibility {
  crypto: boolean
  fetch: boolean
  sessionStorage: boolean
  allSupported: boolean
}
