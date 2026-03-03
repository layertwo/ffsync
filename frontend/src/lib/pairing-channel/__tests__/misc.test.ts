/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { describe, it, expect } from "vitest"
import { hkdfExpand } from "../crypto"
import { zeros } from "../utils"
import { TLSError } from "../alerts"
import { TEST_VECTORS } from "./test-vectors"
import { assertThrowsAsync } from "./helpers"

describe("HKDF", () => {
  it("refuses to generate ridiculously large quantities of hash output", async () => {
    await assertThrowsAsync(async () => {
      await hkdfExpand(TEST_VECTORS.PSK, zeros(32), 32 * 256)
    }, TLSError, "INTERNAL_ERROR")
  })

  it("refuses to generate zero-length hash output", async () => {
    await assertThrowsAsync(async () => {
      await hkdfExpand(TEST_VECTORS.PSK, zeros(32), 0)
    }, TLSError, "INTERNAL_ERROR")
    await assertThrowsAsync(async () => {
      await hkdfExpand(TEST_VECTORS.PSK, zeros(32), -1)
    }, TLSError, "INTERNAL_ERROR")
  })
})

describe("TLSError", () => {
  it("gives a useful default name to unknown description numbers", () => {
    const err = new TLSError(255)
    expect(err.message).toBe("TLS Alert: UNKNOWN (255)")
  })
})
