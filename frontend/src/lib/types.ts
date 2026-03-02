export interface AppConfig {
  oidcProviderUrl: string
  clientId: string
  redirectUri: string
  tokenServerUrl?: string
  authServerUrl?: string
  pairingServerUrl?: string
  scopes: string[]
}

export interface OIDCConfiguration {
  authorizationEndpoint: string
}

export interface BrowserCompatibility {
  crypto: boolean
  fetch: boolean
  sessionStorage: boolean
  allSupported: boolean
}
