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

export function getPairingOAuthParams(): Promise<PairingOAuthParams | null> {
  return new Promise((resolve) => {
    const timeoutId = window.setTimeout(() => {
      cleanup()
      resolve(null)
    }, PAIR_OAUTH_TIMEOUT_MS)

    const cleanup = listenFromFirefox((command, data) => {
      if (command !== "fxaccounts:pair_oauth_start") return
      cleanup()
      window.clearTimeout(timeoutId)
      resolve(data as unknown as PairingOAuthParams)
    })

    // iOS replies only to a request that carries a messageId; the request data is ignored by native.
    sendToFirefox("fxaccounts:pair_oauth_start", {}, String(Date.now()))
  })
}

export function sendOAuthLogin(result: { code: string; state: string }): void {
  sendWebChannelOAuthLogin(result.code, result.state)
}
