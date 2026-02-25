export interface AppConfig {
  oidcProviderUrl: string
  clientId: string
  redirectUri: string
  tokenServerUrl?: string
  authServerUrl?: string
  scopes: string[]
}

export interface OIDCConfiguration {
  authorizationEndpoint: string
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
