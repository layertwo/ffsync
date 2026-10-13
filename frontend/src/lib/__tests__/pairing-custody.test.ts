import { beforeEach, describe, expect, it } from "vitest"

import {
  clearPairingCustody,
  getPairingCustody,
  setPairingCustody,
} from "@/lib/pairing-custody"

describe("pairing custody", () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    clearPairingCustody()
  })

  it("round-trips the key material in memory", () => {
    setPairingCustody({ keyFetchToken: "kft", unwrapBKey: "ubk" })

    expect(getPairingCustody()).toEqual({
      keyFetchToken: "kft",
      unwrapBKey: "ubk",
    })
  })

  it("clears the key material", () => {
    setPairingCustody({ keyFetchToken: "kft", unwrapBKey: "ubk" })

    clearPairingCustody()

    expect(getPairingCustody()).toBeNull()
  })

  it("never persists key material to sessionStorage or localStorage", () => {
    setPairingCustody({ keyFetchToken: "kft", unwrapBKey: "ubk" })

    expect(sessionStorage.length).toBe(0)
    expect(localStorage.length).toBe(0)
  })
})
