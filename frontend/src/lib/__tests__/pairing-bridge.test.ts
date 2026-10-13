import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  getPairingOAuthParams,
  sendOAuthLogin,
} from "@/lib/pairing-bridge"

const PARAMS = {
  state: "state-value",
  scope: "https://identity.mozilla.com/apps/oldsync profile",
  code_challenge: "challenge",
  code_challenge_method: "S256",
  keys_jwk: "{}",
}

function replyFromFirefox(
  command: string,
  data: Record<string, unknown>,
  messageId?: string
) {
  const sent = messagesToChrome()
  const id = messageId ?? (sent[sent.length - 1]?.messageId as string | undefined)
  window.dispatchEvent(
    new CustomEvent("WebChannelMessageToContent", {
      detail: JSON.stringify({
        id: "account_updates",
        message: { command, data, messageId: id },
      }),
    })
  )
}

function messagesToChrome(): Array<{
  command: string
  data: Record<string, unknown>
  messageId?: string
}> {
  return chromeMessages.map((d) => JSON.parse(d).message)
}

const chromeMessages: string[] = []
const chromeListener = (event: Event) =>
  chromeMessages.push((event as CustomEvent).detail as string)

beforeEach(() => {
  chromeMessages.length = 0
  window.addEventListener("WebChannelMessageToChrome", chromeListener)
})

afterEach(() => {
  window.removeEventListener("WebChannelMessageToChrome", chromeListener)
  vi.useRealTimers()
})

describe("getPairingOAuthParams", () => {
  it("resolves the browser-minted OAuth params from a pair_oauth_start reply", async () => {
    const promise = getPairingOAuthParams()
    replyFromFirefox("fxaccounts:pair_oauth_start", PARAMS)
    await expect(promise).resolves.toEqual(PARAMS)
  })

  it("requests params from the browser with fxaccounts:pair_oauth_start", async () => {
    const promise = getPairingOAuthParams()
    replyFromFirefox("fxaccounts:pair_oauth_start", PARAMS)
    await promise
    expect(messagesToChrome()[0].command).toBe("fxaccounts:pair_oauth_start")
    // iOS drops a bridge request that carries no messageId, so it must be sent.
    expect(messagesToChrome()[0].messageId).toBeTruthy()
  })

  it("resolves null when the bridge never answers", async () => {
    vi.useFakeTimers()
    const promise = getPairingOAuthParams()
    vi.advanceTimersByTime(10_000)
    await expect(promise).resolves.toBeNull()
  })

  it("resolves null on an error reply", async () => {
    const promise = getPairingOAuthParams()
    replyFromFirefox("fxaccounts:pair_oauth_start", {
      error: { message: "Failed to begin a pairing OAuth flow" },
    })
    await expect(promise).resolves.toBeNull()
  })

  it("resolves null when a required param field is missing", async () => {
    const promise = getPairingOAuthParams()
    const { keys_jwk: _keysJwk, ...partial } = PARAMS
    replyFromFirefox("fxaccounts:pair_oauth_start", partial)
    await expect(promise).resolves.toBeNull()
  })

  it("ignores a reply with a mismatched messageId and waits for the matching one", async () => {
    vi.useFakeTimers()
    const promise = getPairingOAuthParams()

    replyFromFirefox("fxaccounts:pair_oauth_start", PARAMS, "other-id")

    let settled = false
    promise.then(() => {
      settled = true
    })

    await vi.advanceTimersByTimeAsync(5_000)
    expect(settled).toBe(false)

    replyFromFirefox("fxaccounts:pair_oauth_start", PARAMS)
    await expect(promise).resolves.toEqual(PARAMS)
  })
})

describe("sendOAuthLogin", () => {
  it("posts fxaccounts:oauth_login with the code and state", () => {
    sendOAuthLogin({ code: "code-value", state: "state-value" })
    const msg = messagesToChrome()[0]
    expect(msg.command).toBe("fxaccounts:oauth_login")
    expect(msg.data.code).toBe("code-value")
    expect(msg.data.state).toBe("state-value")
  })
})
