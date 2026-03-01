import { buildHawkHeader } from "./fxa-crypto"

interface AccountStatusResponse {
  exists: boolean
}

interface AccountResponse {
  uid: string
  sessionToken: string
  keyFetchToken: string
  verified: boolean
}

interface OAuthCodeResponse {
  code: string
  state: string
  redirect: string
}

export async function authFetch<T>(
  url: string,
  options: RequestInit
): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, options)
  } catch {
    throw new Error(`Network error connecting to auth server at ${url}`)
  }

  if (!response.ok) {
    let detail = ""
    try {
      const body = await response.json()
      detail = body.message ?? body.error ?? response.statusText
    } catch {
      detail = response.statusText
    }
    throw new Error(
      `Auth server error (${response.status}): ${detail}`
    )
  }

  return (await response.json()) as T
}

interface OIDCCodeExchangeResponse {
  email: string
  access_token: string
  account_exists: boolean
}

export async function exchangeOIDCCode(
  authServerUrl: string,
  code: string,
  codeVerifier: string,
  redirectUri: string
): Promise<OIDCCodeExchangeResponse> {
  return authFetch<OIDCCodeExchangeResponse>(
    `${authServerUrl}/v1/oidc/exchange`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code,
        code_verifier: codeVerifier,
        redirect_uri: redirectUri,
      }),
    }
  )
}

export async function checkAccountStatus(
  authServerUrl: string,
  email: string
): Promise<AccountStatusResponse> {
  const params = new URLSearchParams({ email })
  return authFetch<AccountStatusResponse>(
    `${authServerUrl}/v1/account/status?${params}`,
    { method: "GET" }
  )
}

export async function createAccount(
  authServerUrl: string,
  email: string,
  authPW: string,
  oidcToken: string
): Promise<AccountResponse> {
  return authFetch<AccountResponse>(
    `${authServerUrl}/v1/account/create`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${oidcToken}`,
      },
      body: JSON.stringify({ email, authPW }),
    }
  )
}

export async function login(
  authServerUrl: string,
  email: string,
  authPW: string
): Promise<AccountResponse> {
  return authFetch<AccountResponse>(
    `${authServerUrl}/v1/account/login?keys=true`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, authPW }),
    }
  )
}

export async function requestOAuthCode(
  authServerUrl: string,
  sessionToken: string,
  clientId: string,
  scope: string,
  state: string,
  codeChallenge: string,
  keysJwe?: string
): Promise<OAuthCodeResponse> {
  const url = `${authServerUrl}/v1/oauth/authorization`
  const authorization = await buildHawkHeader(sessionToken, "POST", url)
  const bodyObj: Record<string, string> = {
    client_id: clientId,
    scope,
    state,
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
    access_type: "offline",
  }
  if (keysJwe) {
    bodyObj.keys_jwe = keysJwe
  }
  return authFetch<OAuthCodeResponse>(
    url,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: authorization,
      },
      body: JSON.stringify(bodyObj),
    }
  )
}

interface SessionStatusResponse {
  state: string
  uid: string
}

export async function checkSessionStatus(
  authServerUrl: string,
  sessionToken: string
): Promise<SessionStatusResponse> {
  const url = `${authServerUrl}/v1/session/status`
  const authorization = await buildHawkHeader(sessionToken, "GET", url)
  return authFetch<SessionStatusResponse>(url, {
    method: "GET",
    headers: { Authorization: authorization },
  })
}
