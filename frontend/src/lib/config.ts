import type { AppConfig } from "./types"

const REQUIRED_FIELDS: (keyof AppConfig)[] = [
  "oidcProviderUrl",
  "clientId",
  "redirectUri",
]

export async function loadConfig(): Promise<AppConfig> {
  const response = await fetch("/config.json")
  if (!response.ok) {
    throw new Error(
      `Failed to load config.json (${response.status}). Ensure config.json exists in the public directory.`
    )
  }

  const config: AppConfig = await response.json()
  const missing = REQUIRED_FIELDS.filter((f) => !config[f])
  if (missing.length > 0) {
    throw new Error(
      `Missing required configuration fields: ${missing.join(", ")}`
    )
  }

  if (!config.tokenServerUrl && !config.authServerUrl) {
    throw new Error(
      "Configuration must include either tokenServerUrl or authServerUrl."
    )
  }

  if (!config.scopes || config.scopes.length === 0) {
    config.scopes = ["openid", "profile", "email"]
  }

  config.oidcProviderUrl = config.oidcProviderUrl.replace(/\/+$/, "")
  if (config.tokenServerUrl) {
    config.tokenServerUrl = config.tokenServerUrl.replace(/\/+$/, "")
  }
  if (config.authServerUrl) {
    config.authServerUrl = config.authServerUrl.replace(/\/+$/, "")
  }

  return config
}
