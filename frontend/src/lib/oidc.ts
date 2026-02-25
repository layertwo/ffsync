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
      `Could not reach the auth server at ${authServerUrl}. Check your network connection and server URL.`
    )
  }

  if (!response.ok) {
    throw new Error(
      `OIDC discovery failed (${response.status}) from ${url}. Verify the auth server URL is correct.`
    )
  }

  const data = await response.json()

  if (!data.authorization_endpoint || !data.token_endpoint) {
    throw new Error(
      "OIDC discovery document is missing required endpoints (authorization_endpoint, token_endpoint)."
    )
  }

  const config: OIDCConfiguration = {
    issuer: data.issuer,
    authorizationEndpoint: data.authorization_endpoint,
    tokenEndpoint: data.token_endpoint,
    userinfoEndpoint: data.userinfo_endpoint,
  }

  session.storeOIDCConfig(JSON.stringify(config))
  return config
}
