import { beforeEach, describe, expect, it } from "vitest"

import {
  clearAll,
  clearAuth,
  consumePairingPending,
  getAuth,
  storeAuth,
  storePairingPending,
} from "@/lib/session"

describe("session auth storage", () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
  })

  it("keeps the session token session-scoped, never in localStorage", () => {
    storeAuth("token", "uid", "user@example.com")

    expect(sessionStorage.length).toBe(3)
    expect(localStorage.length).toBe(0)
  })

  it("round-trips the auth record", () => {
    storeAuth("token", "uid", "user@example.com")

    expect(getAuth()).toEqual({
      sessionToken: "token",
      uid: "uid",
      email: "user@example.com",
    })
  })

  it("returns null when part of the record is missing", () => {
    storeAuth("token", "uid", "user@example.com")
    sessionStorage.clear()
    sessionStorage.setItem("ffsync_session_token", "token")

    expect(getAuth()).toBeNull()
  })

  it("clears every auth key", () => {
    storeAuth("token", "uid", "user@example.com")

    clearAuth()

    expect(getAuth()).toBeNull()
    expect(sessionStorage.length).toBe(0)
  })
})

describe("pending pairing intent", () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
  })

  it("survives clearAuth, which the pairing page calls to force a fresh sign-in", () => {
    storePairingPending()

    clearAuth()

    expect(consumePairingPending()).toBe(true)
  })

  it("is consumed once so a later sign-in does not bounce back to /pair", () => {
    storePairingPending()

    expect(consumePairingPending()).toBe(true)
    expect(consumePairingPending()).toBe(false)
  })

  it("is dropped by clearAll on sign-out", () => {
    storePairingPending()

    clearAll()

    expect(consumePairingPending()).toBe(false)
  })
})
