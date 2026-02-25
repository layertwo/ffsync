import * as session from "./session"
import type { OIDCConfiguration } from "./types"

export async function discoverOIDC(
  authServerUrl: string
): Promise<OIDCConfiguration> {
  const cached = session.getOIDCConfig()
  if (cached) {
    return JSON.parse(cached) as OIDCConfiguration
  }

  const url = `${authServerUrl}/v1/oidc/config`
  let response: Response
  try {
    response = await fetch(url)
  } catch {
    throw new Error(
      `Could not reach the auth server at ${authServerUrl}. Check your network connection.`
    )
  }

  if (!response.ok) {
    throw new Error(
      `OIDC config request failed (${response.status}) from ${url}.`
    )
  }

  const data = await response.json()

  if (!data.authorization_endpoint) {
    throw new Error(
      "OIDC config response is missing authorization_endpoint."
    )
  }

  const config: OIDCConfiguration = {
    authorizationEndpoint: data.authorization_endpoint,
  }

  session.storeOIDCConfig(JSON.stringify(config))
  return config
}
