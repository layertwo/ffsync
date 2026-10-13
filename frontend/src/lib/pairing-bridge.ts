import {
  listenFromFirefox,
  sendOAuthLogin as sendWebChannelOAuthLogin,
  sendToFirefox,
} from "@/lib/webchannel"

// From fxa-settings firefox.ts `PairOAuthStartState` and iOS `FxAPairingOAuthHandler.parameterNames`:
// the pair_oauth_start reply carries these five fields, has no client_id, and keys_jwk is required.
export interface PairingOAuthParams {
  state: string
  scope: string
  code_challenge: string
  code_challenge_method: string
  keys_jwk: string
}

const PAIR_OAUTH_TIMEOUT_MS = 10_000

const PARAM_FIELDS = [
  "state",
  "scope",
  "code_challenge",
  "code_challenge_method",
  "keys_jwk",
] as const

function isPairingOAuthParams(data: unknown): data is PairingOAuthParams {
  const record = data as Record<string, unknown>
  return PARAM_FIELDS.every((field) => typeof record[field] === "string")
}

export function getPairingOAuthParams(): Promise<PairingOAuthParams | null> {
  return new Promise((resolve) => {
    const timeoutId = window.setTimeout(() => {
      cleanup()
      resolve(null)
    }, PAIR_OAUTH_TIMEOUT_MS)

    const messageId = String(Date.now())
    const cleanup = listenFromFirefox((command, data, replyId) => {
      if (command !== "fxaccounts:pair_oauth_start") return
      if (replyId !== messageId) return
      cleanup()
      window.clearTimeout(timeoutId)
      // iOS sends an error reply under the same command; treat it as "no answer".
      resolve(isPairingOAuthParams(data) ? data : null)
    })

    // iOS replies only to a request that carries a messageId; the request data is ignored by native.
    sendToFirefox("fxaccounts:pair_oauth_start", {}, messageId)
  })
}

export function sendOAuthLogin(result: { code: string; state: string }): void {
  sendWebChannelOAuthLogin(result.code, result.state)
}
