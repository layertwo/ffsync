import type { AppConfig, OIDCConfiguration, TokenResponse } from "./types"
import { generatePKCE } from "./pkce"
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
    const error = params.get("error")
    const desc = params.get("error_description") ?? "No details provided"
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

export async function exchangeCodeForToken(
  config: AppConfig,
  oidc: OIDCConfiguration,
  code: string
): Promise<TokenResponse> {
  const codeVerifier = session.getCodeVerifier()
  if (!codeVerifier) {
    throw new Error(
      "Missing code verifier. The session may have expired. Please try again."
    )
  }

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: config.clientId,
    code,
    redirect_uri: config.redirectUri,
    code_verifier: codeVerifier,
  })

  let response: Response
  try {
    response = await fetch(oidc.tokenEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    })
  } catch {
    throw new Error(
      "Network error during token exchange. Check your connection and try again."
    )
  }

  if (!response.ok) {
    let detail = ""
    try {
      const err = await response.json()
      detail = err.error_description ?? err.error ?? ""
    } catch {
      detail = response.statusText
    }
    throw new Error(`Token exchange failed (${response.status}): ${detail}`)
  }

  session.removeCodeVerifier()

  return (await response.json()) as TokenResponse
}
