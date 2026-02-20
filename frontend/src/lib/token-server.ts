import { sanitizeExternal } from "./sanitize"

export async function validateWithTokenServer(
  tokenServerUrl: string,
  accessToken: string
): Promise<void> {
  const url = `${tokenServerUrl}/1.0/sync/1.5`

  let response: Response
  try {
    response = await fetch(url, {
      method: "GET",
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  } catch {
    throw new Error(
      `Could not reach the Token Server at ${url}. Check that the server is running and accessible.`
    )
  }

  if (response.status === 401) {
    throw new Error(
      "The Token Server rejected the access token (401 Unauthorized). " +
        "This usually means the token is invalid or the Token Server is not configured to accept tokens from this OIDC provider."
    )
  }

  if (response.status === 503) {
    throw new Error(
      "The Token Server is currently unavailable (503). Please try again later."
    )
  }

  if (!response.ok) {
    let detail = ""
    try {
      const body = await response.text()
      detail = sanitizeExternal(body, 500)
    } catch {
      detail = response.statusText
    }
    throw new Error(
      `Token Server returned an error (${response.status}): ${detail}`
    )
  }
}
