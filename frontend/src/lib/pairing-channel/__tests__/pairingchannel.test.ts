/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { PairingChannel, CHANNEL_HANDSHAKE_TIMEOUT_MS, ACK_TIMEOUT_MS, bytesToBase64url } from "../index"

const mockTls = vi.hoisted(() => ({
  sendCallback: null as ((data: Uint8Array) => void | Promise<void>) | null,
}))

vi.mock("../tlsconnection", () => {
  const connection = { connected: Promise.resolve() }
  const capture = (
    sendCallback: (data: Uint8Array) => void | Promise<void>
  ) => {
    mockTls.sendCallback = sendCallback
    return connection
  }
  return {
    ClientConnection: { create: async (_p: unknown, _i: unknown, cb: (data: Uint8Array) => void | Promise<void>) => capture(cb) },
    ServerConnection: { create: async (_p: unknown, _i: unknown, cb: (data: Uint8Array) => void | Promise<void>) => capture(cb) },
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

  it("does not send the next frame until the previous frame's ack arrives", async () => {
    const promise = PairingChannel.create("wss://example.test/")
    const socket = MockWebSocket.instances[0]
    socket.emit("message", { data: JSON.stringify({ channelid: "chan-123" }) })
    await promise

    const send = mockTls.sendCallback!
    const frame1 = bytesToBase64url(new Uint8Array([1, 2, 3]))
    const frame2 = bytesToBase64url(new Uint8Array([4, 5, 6]))

    const p1 = send(new Uint8Array([1, 2, 3]))
    const p2 = send(new Uint8Array([4, 5, 6]))

    // Flush microtasks: only frame1 reaches the socket (frame2 waits for the ack).
    await Promise.resolve()
    expect(socket.sent).toEqual([frame1])

    socket.emit("message", { data: JSON.stringify({ ack: 1 }) })
    await p1
    expect(socket.sent).toEqual([frame1, frame2])

    socket.emit("message", { data: JSON.stringify({ ack: 1 }) })
    await p2
  })

  it("rejects the send when the relay ack never arrives", async () => {
    vi.useFakeTimers()

    const promise = PairingChannel.create("wss://example.test/")
    const socket = MockWebSocket.instances[0]
    socket.emit("message", { data: JSON.stringify({ channelid: "chan-123" }) })
    await promise

    const send = mockTls.sendCallback!
    const p = send(new Uint8Array([1, 2, 3]))
    const assertion = expect(p).rejects.toThrow("Timed out waiting for the relay ack")

    await vi.advanceTimersByTimeAsync(ACK_TIMEOUT_MS)
    await assertion
  })
})
