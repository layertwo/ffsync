import { cleanup, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { PairAuthorityPage } from "@/components/PairAuthorityPage"
import type { AppConfig } from "@/lib/types"

const { created } = vi.hoisted(() => ({ created: [] as unknown[] }))

vi.mock("@/lib/pairing-channel", () => ({
  PairingChannel: {
    create: vi.fn(async () => {
      const channel = {
        channelId: `chan-${created.length}`,
        channelKey: new Uint8Array([1, 2, 3]),
        closed: false,
        addEventListener: vi.fn(),
        close: vi.fn(async () => {}),
      }
      created.push(channel)
      return channel
    }),
  },
}))

vi.mock("@/lib/webchannel", () => ({
  listenFromFirefox: () => () => {},
  sendPairComplete: () => {},
  sendPairDecline: () => {},
}))

const config: AppConfig = {
  oidcProviderUrl: "https://auth.example.com",
  clientId: "client",
  redirectUri: "https://prod.example.com",
  pairingServerUrl: "wss://channel.example.com",
  scopes: [],
}

describe("PairAuthorityPage", () => {
  beforeEach(() => {
    created.length = 0
  })

  afterEach(() => {
    cleanup()
  })

  it("starts a fresh channel for each pairing", async () => {
    render(<PairAuthorityPage config={config} />)
    await waitFor(() => expect(created).toHaveLength(1))

    cleanup()
    render(<PairAuthorityPage config={config} />)
    await waitFor(() => expect(created).toHaveLength(2))

    expect(created[0]).not.toBe(created[1])
  })
})
