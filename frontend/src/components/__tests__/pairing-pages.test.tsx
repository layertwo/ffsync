import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { PairSupplicantPage } from "@/components/PairSupplicantPage"
import { PairAuthorityPage } from "@/components/PairAuthorityPage"
import type { AppConfig } from "@/lib/types"

const h = vi.hoisted(() => {
  class FakeChannel {
    channelId: string
    channelKey = new Uint8Array([1, 2, 3])
    closed = false
    sent: Array<Record<string, unknown>> = []
    listeners: Record<string, Array<(e: Event) => void>> = {}

    constructor(channelId: string) {
      this.channelId = channelId
    }

    async send(data: Record<string, unknown>): Promise<void> {
      this.sent.push(data)
    }

    async close(): Promise<void> {
      this.closed = true
    }

    addEventListener(type: string, cb: (e: Event) => void): void {
      ;(this.listeners[type] ??= []).push(cb)
    }

    dispatch(type: string, detail?: unknown): void {
      for (const cb of this.listeners[type] ?? []) {
        cb(new CustomEvent(type, { detail }))
      }
    }
  }
  const instances: FakeChannel[] = []
  return { FakeChannel, instances }
})

vi.mock("@/lib/pairing-channel", () => ({
  PairingChannel: {
    create: vi.fn(async () => {
      const ch = new h.FakeChannel("chan-authority")
      h.instances.push(ch)
      return ch
    }),
    connect: vi.fn(async () => {
      const ch = new h.FakeChannel("chan-supplicant")
      h.instances.push(ch)
      return ch
    }),
  },
}))

vi.mock("@/lib/pairing", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/pairing")>()),
  parsePairFragment: () => ({
    channelId: "chan-1",
    channelKey: new Uint8Array([1, 2, 3]),
  }),
  buildPairUrl: (origin: string, id: string) => `${origin}/pair/#channel_id=${id}`,
}))

const bridge = vi.hoisted(() => ({
  getPairingOAuthParams: vi.fn(),
  sendOAuthLogin: vi.fn(),
}))
vi.mock("@/lib/pairing-bridge", () => bridge)

const syncKeys = vi.hoisted(() => ({
  deriveAndEncryptSyncKeys: vi.fn(),
}))
vi.mock("@/lib/sync-keys", () => syncKeys)

const authClient = vi.hoisted(() => ({
  requestOAuthCode: vi.fn(),
}))
vi.mock("@/lib/auth-client", () => authClient)

const custody = vi.hoisted(() => ({
  getPairingCustody: vi.fn(),
  setPairingCustody: vi.fn(),
  clearPairingCustody: vi.fn(),
}))
vi.mock("@/lib/pairing-custody", () => custody)

const session = vi.hoisted(() => ({
  getAuth: vi.fn(),
  storeAuth: vi.fn(),
  clearAuth: vi.fn(),
  clearAll: vi.fn(),
}))
vi.mock("@/lib/session", () => session)

vi.mock("@/lib/webchannel", () => ({
  listenFromFirefox: () => () => {},
  sendPairComplete: () => {},
  sendPairDecline: () => {},
}))

const config: AppConfig = {
  oidcProviderUrl: "https://auth.example.com",
  clientId: "client-id",
  redirectUri: "https://prod.example.com",
  authServerUrl: "https://auth.example.com",
  pairingServerUrl: "wss://channel.example.com",
  scopes: [],
}

const BRIDGE_PARAMS = {
  state: "state-value",
  scope: "https://identity.mozilla.com/apps/oldsync profile",
  code_challenge: "challenge",
  code_challenge_method: "S256",
  keys_jwk: "e30",
}

const REQUEST = {
  client_id: "client-id",
  state: "state-1",
  scope: "https://identity.mozilla.com/apps/oldsync profile",
  code_challenge: "challenge",
  code_challenge_method: "S256",
  keys_jwk: "e30",
}

function requestMessage() {
  return { data: { message: "pair:supp:request", data: REQUEST } }
}

beforeEach(() => {
  h.instances.length = 0
  vi.resetAllMocks()
})

afterEach(() => {
  cleanup()
})

describe("PairSupplicantPage", () => {
  it("sends pair:supp:request with the browser-minted params", async () => {
    bridge.getPairingOAuthParams.mockResolvedValue(BRIDGE_PARAMS)
    render(<PairSupplicantPage config={config} />)
    const ch = h.instances[0]

    await waitFor(() => expect(ch.sent).toHaveLength(1))

    expect(ch.sent[0]).toEqual({
      message: "pair:supp:request",
      data: { client_id: "client-id", ...BRIDGE_PARAMS },
    })
  })

  it("falls back to self-generated PKCE when the bridge is absent", async () => {
    bridge.getPairingOAuthParams.mockResolvedValue(null)
    render(<PairSupplicantPage config={config} />)
    const ch = h.instances[0]

    await waitFor(() => expect(ch.sent).toHaveLength(1))

    const data = ch.sent[0].data as Record<string, unknown>
    expect(data.client_id).toBe("client-id")
    expect(data.state).toBeTruthy()
    expect(data.code_challenge).toBeTruthy()
    expect(data.code_challenge_method).toBe("S256")
    expect(data.scope).toBe(
      "https://identity.mozilla.com/apps/oldsync profile"
    )
    expect(data.keys_jwk).toBeUndefined()
  })

  it("sends pair:supp:authorize and hands off on authorize", async () => {
    bridge.getPairingOAuthParams.mockResolvedValue(BRIDGE_PARAMS)
    render(<PairSupplicantPage config={config} />)
    const ch = h.instances[0]

    await waitFor(() => expect(ch.sent).toHaveLength(1))

    act(() =>
      ch.dispatch("message", {
        data: {
          message: "pair:auth:authorize",
          data: { code: "code-1", state: "state-1" },
        },
      })
    )

    await waitFor(() =>
      expect(ch.sent).toContainEqual({ message: "pair:supp:authorize", data: {} })
    )
    expect(bridge.sendOAuthLogin).toHaveBeenCalledWith({
      code: "code-1",
      state: "state-1",
    })
  })

  it("shows a decline error on pair:auth:cancel and pair:auth:decline", async () => {
    bridge.getPairingOAuthParams.mockResolvedValue(BRIDGE_PARAMS)
    render(<PairSupplicantPage config={config} />)
    const ch = h.instances[0]

    await waitFor(() => expect(ch.sent).toHaveLength(1))

    act(() =>
      ch.dispatch("message", { data: { message: "pair:auth:cancel", data: {} } })
    )
    await waitFor(() => expect(screen.getByText(/declined/i)).toBeTruthy())
  })

  it("ignores unknown pair: messages without dropping the connection", async () => {
    bridge.getPairingOAuthParams.mockResolvedValue(BRIDGE_PARAMS)
    render(<PairSupplicantPage config={config} />)
    const ch = h.instances[0]

    await waitFor(() => expect(ch.sent).toHaveLength(1))

    act(() =>
      ch.dispatch("message", {
        data: { message: "pair:unknown", data: {} },
      })
    )

    expect(
      screen.getByText("Waiting for the other device to approve...")
    ).toBeTruthy()
  })
})

describe("PairAuthorityPage", () => {
  it("sends pair:auth:cancel and pair:auth:decline on decline", async () => {
    render(<PairAuthorityPage config={config} />)
    const ch = h.instances[0]

    await waitFor(() => expect(screen.getByText(/Scan this QR code/i)).toBeTruthy())

    act(() => ch.dispatch("message", requestMessage()))
    await waitFor(() => expect(screen.getByText("Decline")).toBeTruthy())

    fireEvent.click(screen.getByText("Decline"))

    await waitFor(() =>
      expect(ch.sent).toContainEqual({ message: "pair:auth:cancel", data: {} })
    )
    expect(ch.sent).toContainEqual({ message: "pair:auth:decline", data: {} })
  })

  it("derives scoped keys and sends pair:auth:authorize without redirect", async () => {
    session.getAuth.mockReturnValue({ sessionToken: "st", uid: "u", email: "e" })
    custody.getPairingCustody.mockReturnValue({
      keyFetchToken: "kft",
      unwrapBKey: "ubk",
    })
    syncKeys.deriveAndEncryptSyncKeys.mockResolvedValue("jwe-value")
    authClient.requestOAuthCode.mockResolvedValue({
      code: "code-1",
      state: "state-1",
      redirect: "ignored",
    })

    render(<PairAuthorityPage config={config} />)
    const ch = h.instances[0]

    await waitFor(() => expect(screen.getByText(/Scan this QR code/i)).toBeTruthy())
    act(() => ch.dispatch("message", requestMessage()))
    await waitFor(() => expect(screen.getByText("Approve")).toBeTruthy())

    fireEvent.click(screen.getByText("Approve"))

    await waitFor(() =>
      expect(syncKeys.deriveAndEncryptSyncKeys).toHaveBeenCalledWith({
        authServerUrl: "https://auth.example.com",
        keyFetchTokenHex: "kft",
        unwrapBKeyHex: "ubk",
        sessionTokenHex: "st",
        keysJwkB64: "e30",
        scope: "https://identity.mozilla.com/apps/oldsync profile",
      })
    )

    await waitFor(() =>
      expect(authClient.requestOAuthCode).toHaveBeenCalledWith(
        "https://auth.example.com",
        "st",
        "client-id",
        "https://identity.mozilla.com/apps/oldsync profile",
        "state-1",
        "challenge",
        "jwe-value",
        "urn:ietf:wg:oauth:2.0:oob:pair-auth-webchannel"
      )
    )

    await waitFor(() =>
      expect(ch.sent).toContainEqual({
        message: "pair:auth:authorize",
        data: { code: "code-1", state: "state-1" },
      })
    )
    const authorize = ch.sent.find((s) => s.message === "pair:auth:authorize")!
    expect(authorize.data).not.toHaveProperty("redirect")
  })

  it("completes without keys when the supplicant sends no keys_jwk", async () => {
    session.getAuth.mockReturnValue({ sessionToken: "st", uid: "u", email: "e" })
    custody.getPairingCustody.mockReturnValue(null)
    authClient.requestOAuthCode.mockResolvedValue({
      code: "code-1",
      state: "state-1",
      redirect: "ignored",
    })

    render(<PairAuthorityPage config={config} />)
    const ch = h.instances[0]

    await waitFor(() => expect(screen.getByText(/Scan this QR code/i)).toBeTruthy())
    act(() =>
      ch.dispatch("message", {
        data: {
          message: "pair:supp:request",
          data: { ...REQUEST, keys_jwk: undefined },
        },
      })
    )
    await waitFor(() => expect(screen.getByText("Approve")).toBeTruthy())

    fireEvent.click(screen.getByText("Approve"))

    await waitFor(() =>
      expect(ch.sent).toContainEqual({
        message: "pair:auth:authorize",
        data: { code: "code-1", state: "state-1" },
      })
    )
    expect(syncKeys.deriveAndEncryptSyncKeys).not.toHaveBeenCalled()
    expect(authClient.requestOAuthCode).toHaveBeenCalledWith(
      "https://auth.example.com",
      "st",
      "client-id",
      "https://identity.mozilla.com/apps/oldsync profile",
      "state-1",
      "challenge",
      undefined,
      "urn:ietf:wg:oauth:2.0:oob:pair-auth-webchannel"
    )
  })

  it("lands in the error state when key custody is absent", async () => {
    session.getAuth.mockReturnValue({ sessionToken: "st", uid: "u", email: "e" })
    custody.getPairingCustody.mockReturnValue(null)

    render(<PairAuthorityPage config={config} />)
    const ch = h.instances[0]

    await waitFor(() => expect(screen.getByText(/Scan this QR code/i)).toBeTruthy())
    act(() => ch.dispatch("message", requestMessage()))
    await waitFor(() => expect(screen.getByText("Approve")).toBeTruthy())

    fireEvent.click(screen.getByText("Approve"))

    await waitFor(() => expect(screen.getByText(/sign in again/i)).toBeTruthy())
  })

  it("lands in the error state when keys_jwk is present but empty", async () => {
    session.getAuth.mockReturnValue({ sessionToken: "st", uid: "u", email: "e" })
    custody.getPairingCustody.mockReturnValue({
      keyFetchToken: "kft",
      unwrapBKey: "ubk",
    })

    render(<PairAuthorityPage config={config} />)
    const ch = h.instances[0]

    await waitFor(() => expect(screen.getByText(/Scan this QR code/i)).toBeTruthy())
    act(() =>
      ch.dispatch("message", {
        data: { message: "pair:supp:request", data: { ...REQUEST, keys_jwk: "" } },
      })
    )
    await waitFor(() => expect(screen.getByText("Approve")).toBeTruthy())

    fireEvent.click(screen.getByText("Approve"))

    await waitFor(() => expect(screen.getByText(/did not provide/i)).toBeTruthy())
    expect(syncKeys.deriveAndEncryptSyncKeys).not.toHaveBeenCalled()
    expect(authClient.requestOAuthCode).not.toHaveBeenCalled()
  })

  it("lands in the error state when key derivation fails", async () => {
    session.getAuth.mockReturnValue({ sessionToken: "st", uid: "u", email: "e" })
    custody.getPairingCustody.mockReturnValue({
      keyFetchToken: "kft",
      unwrapBKey: "ubk",
    })
    syncKeys.deriveAndEncryptSyncKeys.mockRejectedValue(new Error("bad jwk"))

    render(<PairAuthorityPage config={config} />)
    const ch = h.instances[0]

    await waitFor(() => expect(screen.getByText(/Scan this QR code/i)).toBeTruthy())
    act(() => ch.dispatch("message", requestMessage()))
    await waitFor(() => expect(screen.getByText("Approve")).toBeTruthy())

    fireEvent.click(screen.getByText("Approve"))

    await waitFor(() => expect(screen.getByText(/bad jwk/)).toBeTruthy())
  })

  it("ends on a terminal error when the channel closes while waiting", async () => {
    render(<PairAuthorityPage config={config} />)
    const ch = h.instances[0]

    await waitFor(() => expect(screen.getByText(/Scan this QR code/i)).toBeTruthy())

    act(() => ch.dispatch("close"))

    await waitFor(() => expect(screen.getByText(/Pairing Error/)).toBeTruthy())
  })

  it("does not overwrite the complete state when the channel closes after success", async () => {
    session.getAuth.mockReturnValue({ sessionToken: "st", uid: "u", email: "e" })
    custody.getPairingCustody.mockReturnValue({
      keyFetchToken: "kft",
      unwrapBKey: "ubk",
    })
    syncKeys.deriveAndEncryptSyncKeys.mockResolvedValue("jwe-value")
    authClient.requestOAuthCode.mockResolvedValue({
      code: "code-1",
      state: "state-1",
      redirect: "ignored",
    })

    render(<PairAuthorityPage config={config} />)
    const ch = h.instances[0]

    await waitFor(() => expect(screen.getByText(/Scan this QR code/i)).toBeTruthy())
    act(() => ch.dispatch("message", requestMessage()))
    await waitFor(() => expect(screen.getByText("Approve")).toBeTruthy())

    fireEvent.click(screen.getByText("Approve"))
    await waitFor(() => expect(screen.getByText(/Device Paired/)).toBeTruthy())

    act(() => ch.dispatch("close"))

    expect(screen.getByText(/Device Paired/)).toBeTruthy()
  })

  it("ignores unknown pair: messages and pair:supp:authorize without throwing", async () => {
    render(<PairAuthorityPage config={config} />)
    const ch = h.instances[0]

    await waitFor(() => expect(screen.getByText(/Scan this QR code/i)).toBeTruthy())

    act(() => ch.dispatch("message", { data: { message: "pair:supp:authorize", data: {} } }))
    act(() => ch.dispatch("message", { data: { message: "pair:unknown", data: {} } }))

    expect(screen.getByText(/Scan this QR code/i)).toBeTruthy()
  })
})
