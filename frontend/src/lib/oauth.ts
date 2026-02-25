import type { AppConfig, OIDCConfiguration } from "./types"
import { generatePKCE } from "./pkce"
import { sanitizeExternal } from "./sanitize"
import * as session from "./session"

export function initiateOAuthFlow(
  config: AppConfig,
  oidc: OIDCConfiguration
): void {
  const state = crypto.randomUUID()
  session.storeState(state)

  generatePKCE().then(({ codeVerifier, codeChallenge }) => {
    session.storeCodeVerifier(codeVerifier)

    const params = new URLSearchParams({
      client_id: config.clientId,
      response_type: "code",
      redirect_uri: config.redirectUri,
      scope: config.scopes.join(" "),
      state,
      code_challenge: codeChallenge,
      code_challenge_method: "S256",
    })

    window.location.href = `${oidc.authorizationEndpoint}?${params.toString()}`
  })
}

export function detectCallback(): URLSearchParams | null {
  const params = new URLSearchParams(window.location.search)
  if (params.has("code") || params.has("error")) {
    return params
  }
  return null
}


export function validateCallback(params: URLSearchParams): string {
  if (params.has("error")) {
    const error = sanitizeExternal(params.get("error") ?? "unknown_error")
    const desc = sanitizeExternal(
      params.get("error_description") ?? "No details provided"
    )
    throw new Error(`${error}: ${desc}`)
  }

  const returnedState = params.get("state")
  const storedState = session.getState()

  if (!returnedState || !storedState) {
    throw new Error("Missing state parameter. This may indicate a CSRF attack.")
  }

  if (returnedState !== storedState) {
    throw new Error(
      "State parameter mismatch. This may indicate a CSRF attack. Please try again."
    )
  }

  session.removeState()

  const code = params.get("code")
  if (!code) {
    throw new Error("No authorization code received from the OIDC provider.")
  }

  return code
}

