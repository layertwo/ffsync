/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { describe, it, expect, beforeEach } from "vitest"
import { bytesAreEqual } from "../utils"
import { TLSError } from "../alerts"
import { KeySchedule } from "../keyschedule"
import { TEST_VECTORS } from "./test-vectors"
import { assertThrowsAsync } from "./helpers"

describe("the KeySchedule class", () => {
  let ks: KeySchedule

  beforeEach(() => {
    ks = new KeySchedule()
  })

  it("errors if adding ECDHE output before PSK", async () => {
    await assertThrowsAsync(async () => {
      await ks.addECDHE(null)
    }, TLSError, "INTERNAL_ERROR")
  })

  it("errors if finalizing before PSK", async () => {
    await assertThrowsAsync(async () => {
      await ks.finalize()
    }, TLSError, "INTERNAL_ERROR")
  })

  describe("accepts a PSK, and then", () => {
    beforeEach(async () => {
      await ks.addPSK(TEST_VECTORS.PSK)
    })

    it("calculates the correct intermediate keys", () => {
      expect(bytesAreEqual(ks.extBinderKey!, TEST_VECTORS.KEYS_EXT_BINDER)).toBe(true)
      expect(ks.clientHandshakeTrafficSecret).toBeNull()
      expect(ks.serverHandshakeTrafficSecret).toBeNull()
      expect(ks.clientApplicationTrafficSecret).toBeNull()
      expect(ks.serverApplicationTrafficSecret).toBeNull()
    })

    it("errors if adding PSK again", async () => {
      await assertThrowsAsync(async () => {
        await ks.addPSK(TEST_VECTORS.PSK)
      }, TLSError, "INTERNAL_ERROR")
    })

    it("errors if finalizing before ECDHE output", async () => {
      await assertThrowsAsync(async () => {
        await ks.finalize()
      }, TLSError, "INTERNAL_ERROR")
    })

    describe("accepts ECDHE output, and then", () => {
      beforeEach(async () => {
        ks.addToTranscript(TEST_VECTORS.KEYS_PLAINTEXT_TRANSCRIPT)
        await ks.addECDHE(null)
      })

      it("calculates the correct intermediate keys", () => {
        expect(ks.extBinderKey).toBeNull()
        expect(
          bytesAreEqual(
            ks.clientHandshakeTrafficSecret!,
            TEST_VECTORS.KEYS_CLIENT_HANDSHAKE_TRAFFIC_SECRET
          )
        ).toBe(true)
        expect(
          bytesAreEqual(
            ks.serverHandshakeTrafficSecret!,
            TEST_VECTORS.KEYS_SERVER_HANDSHAKE_TRAFFIC_SECRET
          )
        ).toBe(true)
        expect(ks.clientApplicationTrafficSecret).toBeNull()
        expect(ks.serverApplicationTrafficSecret).toBeNull()
      })

      it("errors if adding PSK again", async () => {
        await assertThrowsAsync(async () => {
          await ks.addPSK(null)
        }, TLSError, "INTERNAL_ERROR")
      })

      it("errors if adding ECDHE output again", async () => {
        await assertThrowsAsync(async () => {
          await ks.addECDHE(null)
        }, TLSError, "INTERNAL_ERROR")
      })

      describe("can be finalized, and then", () => {
        beforeEach(async () => {
          ks.addToTranscript(TEST_VECTORS.KEYS_ENCRYPTED_TRANSCRIPT)
          await ks.finalize()
        })

        it("calculates the correct final keys", () => {
          expect(ks.extBinderKey).toBeNull()
          expect(ks.clientHandshakeTrafficSecret).toBeNull()
          expect(ks.serverHandshakeTrafficSecret).toBeNull()
          expect(
            bytesAreEqual(
              ks.clientApplicationTrafficSecret!,
              TEST_VECTORS.KEYS_CLIENT_APPLICATION_TRAFFIC_SECRET_0
            )
          ).toBe(true)
          expect(
            bytesAreEqual(
              ks.serverApplicationTrafficSecret!,
              TEST_VECTORS.KEYS_SERVER_APPLICATION_TRAFFIC_SECRET_0
            )
          ).toBe(true)
        })

        it("errors if adding PSK again", async () => {
          await assertThrowsAsync(async () => {
            await ks.addPSK(null)
          }, TLSError, "INTERNAL_ERROR")
        })

        it("errors if adding ECDHE output again", async () => {
          await assertThrowsAsync(async () => {
            await ks.addECDHE(null)
          }, TLSError, "INTERNAL_ERROR")
        })

        it("errors if finalizing again", async () => {
          await assertThrowsAsync(async () => {
            await ks.finalize()
          }, TLSError, "INTERNAL_ERROR")
        })
      })
    })
  })
})
