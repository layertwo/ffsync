/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { PairingChannel, CHANNEL_HANDSHAKE_TIMEOUT_MS } from "../index"

vi.mock("../tlsconnection", () => {
  const connection = { connected: Promise.resolve() }
  return {
    ClientConnection: { create: async () => connection },
    ServerConnection: { create: async () => connection },
  }
})

class MockWebSocket {
  static instances: MockWebSocket[] = []
  readyState = 1
  closed = false
  sent: string[] = []
  private listeners = new Map<string, Array<(e: unknown) => void>>()

  constructor(_url: string) {
    MockWebSocket.instances.push(this)
  }

  addEventListener(type: string, cb: (e: unknown) => void): void {
    const list = this.listeners.get(type) ?? []
    list.push(cb)
    this.listeners.set(type, list)
  }

  removeEventListener(type: string, cb: (e: unknown) => void): void {
    const list = this.listeners.get(type)
    if (list) {
      this.listeners.set(type, list.filter((l) => l !== cb))
    }
  }

  send(data: string): void {
    this.sent.push(data)
  }

  close(): void {
    this.closed = true
  }

  emit(type: string, event: unknown = {}): void {
    for (const cb of this.listeners.get(type) ?? []) cb(event)
  }
}

describe("PairingChannel handshake", () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal("WebSocket", MockWebSocket)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it("rejects and closes the socket when no first message arrives in time", async () => {
    vi.useFakeTimers()

    const promise = PairingChannel.create("wss://example.test/")
    const socket = MockWebSocket.instances[0]
    const assertion = expect(promise).rejects.toThrow("Timed out creating the pairing channel")

    await vi.advanceTimersByTimeAsync(CHANNEL_HANDSHAKE_TIMEOUT_MS)
    await assertion
    expect(socket.closed).toBe(true)
  })

  it("resolves and clears the timer when the first message arrives", async () => {
    vi.useFakeTimers()

    const promise = PairingChannel.create("wss://example.test/")
    const socket = MockWebSocket.instances[0]
    socket.emit("message", { data: JSON.stringify({ channelid: "chan-123" }) })

    const channel = await promise
    expect(channel.channelId).toBe("chan-123")
    expect(vi.getTimerCount()).toBe(0)
  })
})
