/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { describe, it, expect, beforeEach } from "vitest"
import {
  bytesAreEqual,
  bytesToUtf8,
  bytesToHex,
  utf8ToBytes,
  arrayToBytes,
  zeros,
} from "../utils"
import { TLSError } from "../alerts"
import {
  EncryptionState,
  DecryptionState,
  RecordLayer,
} from "../recordlayer"
import { TEST_VECTORS } from "./test-vectors"
import { testHelpers, assertThrowsAsync } from "./helpers"

const MAX_RECORD_SIZE = Math.pow(2, 14)
const MAX_ENCRYPTED_RECORD_SIZE = MAX_RECORD_SIZE + 256
const MAX_SEQUENCE_NUMBER = Math.pow(2, 24)

describe("the EncryptionState and DecryptionState classes", () => {
  let es: EncryptionState, ds: DecryptionState

  beforeEach(async () => {
    es = await EncryptionState.create(zeros(32))
    ds = await DecryptionState.create(zeros(32))
  })

  it("uses crypto.subtle to encrypt and decrypt stuff", async () => {
    const data = await es.encrypt(
      TEST_VECTORS.SERVER_RAW_APP_DATA,
      zeros(12)
    )
    expect(
      bytesAreEqual(
        await ds.decrypt(data, zeros(12)),
        TEST_VECTORS.SERVER_RAW_APP_DATA
      )
    ).toBe(true)
  })

  it("prevent wrapping of the sequence number", async () => {
    es.seqnum = MAX_SEQUENCE_NUMBER - 1
    await es.encrypt(TEST_VECTORS.SERVER_RAW_APP_DATA, zeros(12))
    expect(es.seqnum).toBe(MAX_SEQUENCE_NUMBER)
    await assertThrowsAsync(async () => {
      await es.encrypt(TEST_VECTORS.SERVER_RAW_APP_DATA, zeros(12))
    }, TLSError, "INTERNAL_ERROR")

    ds.seqnum = MAX_SEQUENCE_NUMBER
    await assertThrowsAsync(async () => {
      await ds.decrypt(TEST_VECTORS.SERVER_RAW_APP_DATA, zeros(12))
    }, TLSError, "INTERNAL_ERROR")
  })
})

describe("the RecordLayer class", () => {
  let rl: RecordLayer, SENT_DATA: Uint8Array[]

  beforeEach(() => {
    SENT_DATA = []
    rl = new RecordLayer((data: Uint8Array) => {
      SENT_DATA.push(data)
    })
  })

  describe("when sending", () => {
    it("starts off sending plaintext records", async () => {
      await rl.send(22, utf8ToBytes("hello world"))
      expect(SENT_DATA.length).toBe(0)
      await rl.flush()
      expect(SENT_DATA.length).toBe(1)
      expect(SENT_DATA[0][0]).toBe(22)
      expect(SENT_DATA[0][1]).toBe(0x03)
      expect(SENT_DATA[0][2]).toBe(0x03)
      expect(SENT_DATA[0][3]).toBe(0)
      expect(SENT_DATA[0][4]).toBe(11)
      expect(bytesToUtf8(SENT_DATA[0].slice(5))).toBe("hello world")
    })

    it("does not send anything on flush if no data is buffered", async () => {
      await rl.flush()
      expect(SENT_DATA.length).toBe(0)
    })

    it("combines multiple sends of the same type into a single record", async () => {
      await rl.send(22, utf8ToBytes("hello world"))
      await rl.send(22, utf8ToBytes("hello again"))
      expect(SENT_DATA.length).toBe(0)
      await rl.flush()
      expect(SENT_DATA.length).toBe(1)
      expect(SENT_DATA[0][0]).toBe(22)
      expect(SENT_DATA[0][1]).toBe(0x03)
      expect(SENT_DATA[0][2]).toBe(0x03)
      expect(SENT_DATA[0][3]).toBe(0)
      expect(SENT_DATA[0][4]).toBe(22)
      expect(bytesToUtf8(SENT_DATA[0].slice(5))).toBe(
        "hello worldhello again"
      )
    })

    it("refuses to send data that would exceed the max record size", async () => {
      await assertThrowsAsync(async () => {
        await rl.send(22, zeros(MAX_RECORD_SIZE + 1))
      }, TLSError, "INTERNAL_ERROR")
    })

    it("flushes multiple sends when they would combine to exceed the max record size", async () => {
      await rl.send(22, utf8ToBytes("hello world"))
      await rl.send(22, zeros(MAX_RECORD_SIZE - 1))
      expect(SENT_DATA.length).toBe(1)
      await rl.flush()
      expect(SENT_DATA.length).toBe(2)
      expect(bytesToUtf8(SENT_DATA[0].slice(5))).toBe("hello world")
      expect(bytesToHex(SENT_DATA[1].slice(5, 10))).toBe("0000000000")
    })

    describe("after setting a send key", () => {
      let decryptor: DecryptionState

      async function decryptInnerPlaintext(
        bytes: Uint8Array
      ): Promise<[Uint8Array, number]> {
        const plaintext = await testHelpers.decryptInnerPlaintext(
          decryptor,
          bytes
        )
        return [plaintext.slice(0, -1), plaintext[plaintext.byteLength - 1]]
      }

      beforeEach(async () => {
        const key = zeros(32)
        crypto.getRandomValues(key)
        decryptor = await DecryptionState.create(key)
        await rl.setSendKey(key)
        expect(rl._sendEncryptState).toBeTruthy()
        expect(rl._recvDecryptState).toBeNull()
      })

      it("will send encrypted handshake records", async () => {
        await rl.send(22, utf8ToBytes("hello world"))
        await rl.flush()
        expect(SENT_DATA.length).toBe(1)
        expect(SENT_DATA[0][0]).toBe(23)
        expect(SENT_DATA[0][1]).toBe(0x03)
        expect(SENT_DATA[0][2]).toBe(0x03)
        expect(SENT_DATA[0][3]).toBe(0)
        expect(SENT_DATA[0][4]).toBe(11 + 1 + 16)
        const ciphertext = SENT_DATA[0].slice(5)
        expect(ciphertext.byteLength).toBe(11 + 1 + 16)
        const [content, type] = await decryptInnerPlaintext(SENT_DATA[0])
        expect(bytesToUtf8(content)).toBe("hello world")
        expect(type).toBe(22)
      })

      it("will send encrypted application data records", async () => {
        await rl.send(23, utf8ToBytes("hello world"))
        await rl.flush()
        expect(SENT_DATA.length).toBe(1)
        expect(SENT_DATA[0][0]).toBe(23)
        expect(SENT_DATA[0][1]).toBe(0x03)
        expect(SENT_DATA[0][2]).toBe(0x03)
        expect(SENT_DATA[0][3]).toBe(0)
        expect(SENT_DATA[0][4]).toBe(11 + 1 + 16)
        const ciphertext = SENT_DATA[0].slice(5)
        expect(ciphertext.byteLength).toBe(11 + 1 + 16)
        const [content, type] = await decryptInnerPlaintext(SENT_DATA[0])
        expect(bytesToUtf8(content)).toBe("hello world")
        expect(type).toBe(23)
      })

      it("flushes between multiple sends when they have different types", async () => {
        await rl.send(22, utf8ToBytes("handshake"))
        await rl.send(22, utf8ToBytes("handshake"))
        await rl.send(23, utf8ToBytes("app-data"))
        expect(SENT_DATA.length).toBe(1)
        await rl.flush()
        expect(SENT_DATA.length).toBe(2)

        expect(SENT_DATA[0][0]).toBe(23)
        expect(SENT_DATA[0][1]).toBe(0x03)
        expect(SENT_DATA[0][2]).toBe(0x03)
        expect(SENT_DATA[0][3]).toBe(0)
        expect(SENT_DATA[0][4]).toBe(18 + 1 + 16)
        let [content, type] = await decryptInnerPlaintext(SENT_DATA[0])
        expect(bytesToUtf8(content)).toBe("handshakehandshake")
        expect(type).toBe(22)

        expect(SENT_DATA[1][0]).toBe(23)
        expect(SENT_DATA[1][1]).toBe(0x03)
        expect(SENT_DATA[1][2]).toBe(0x03)
        expect(SENT_DATA[1][3]).toBe(0)
        expect(SENT_DATA[1][4]).toBe(8 + 1 + 16)
        ;[content, type] = await decryptInnerPlaintext(SENT_DATA[1])
        expect(bytesToUtf8(content)).toBe("app-data")
        expect(type).toBe(23)
      })
    })
  })

  describe("when receiving", () => {
    const makePlaintextRecord = testHelpers.makePlaintextRecord

    it("starts off receiving plaintext records", () => {
      expect(rl._recvDecryptState).toBeNull()
    })

    it("accepts plaintext handshake messages", async () => {
      const [type, bytes] = await rl.recv(
        makePlaintextRecord({ type: 22 })
      )
      expect(type).toBe(22)
      expect(bytesAreEqual(bytes, arrayToBytes([1, 2, 3, 4, 5]))).toBe(true)
    })

    it("accepts legacy version number on plaintext records", async () => {
      const [type, bytes] = await rl.recv(
        makePlaintextRecord({ type: 22, version: 0x0301 })
      )
      expect(type).toBe(22)
      expect(bytesAreEqual(bytes, arrayToBytes([1, 2, 3, 4, 5]))).toBe(true)
    })

    it("rejects record headers with unknown version numbers", async () => {
      await assertThrowsAsync(async () => {
        await rl.recv(makePlaintextRecord({ version: 0x0000 }))
      }, TLSError, "DECODE_ERROR")
      await assertThrowsAsync(async () => {
        await rl.recv(makePlaintextRecord({ version: 0x1234 }))
      }, TLSError, "DECODE_ERROR")
    })

    it("rejects records that are too large", async () => {
      await assertThrowsAsync(async () => {
        await rl.recv(
          makePlaintextRecord({ contentLength: MAX_RECORD_SIZE })
        )
      }, TLSError, "DECODE_ERROR")
      await assertThrowsAsync(async () => {
        await rl.recv(
          makePlaintextRecord({ contentLength: MAX_RECORD_SIZE + 1 })
        )
      }, TLSError, "RECORD_OVERFLOW")
    })

    it("refuses to accept any data after a single record", async () => {
      await assertThrowsAsync(async () => {
        await rl.recv(
          makePlaintextRecord({
            trailer: zeros(12),
            type: 22,
          })
        )
      }, TLSError, "DECODE_ERROR")
    })

    it("refuses to accept a partial record", async () => {
      await assertThrowsAsync(async () => {
        await rl.recv(makePlaintextRecord({ type: 22 }).slice(0, -1))
      }, TLSError, "DECODE_ERROR")
    })

    describe("after setting a recv key", () => {
      let encryptor: EncryptionState

      async function makeEncryptedInnerPlaintext(
        opts: Record<string, unknown>
      ): Promise<Uint8Array> {
        return await testHelpers.makeEncryptedInnerPlaintext(
          encryptor,
          opts as Parameters<typeof testHelpers.makeEncryptedInnerPlaintext>[1]
        )
      }

      async function makeEncryptedRecord(
        opts: Record<string, unknown>
      ): Promise<Uint8Array> {
        return await testHelpers.makeEncryptedRecord(
          encryptor,
          opts as Parameters<typeof testHelpers.makeEncryptedRecord>[1]
        )
      }

      beforeEach(async () => {
        const key = zeros(32)
        crypto.getRandomValues(key)
        encryptor = await EncryptionState.create(key)
        await rl.setRecvKey(key)
        expect(rl._recvDecryptState).toBeTruthy()
        expect(rl._sendEncryptState).toBeNull()
      })

      it("accepts records generated by our helper functions above", async () => {
        const [type, bytes] = await rl.recv(await makeEncryptedRecord({}))
        expect(type).toBe(23)
        expect(bytesAreEqual(bytes, arrayToBytes([1, 2, 3, 4, 5]))).toBe(true)
      })

      it("accepts encrypted handshake message records", async () => {
        const [type, bytes] = await rl.recv(
          await makeEncryptedRecord({ type: 22 })
        )
        expect(type).toBe(22)
        expect(bytesAreEqual(bytes, arrayToBytes([1, 2, 3, 4, 5]))).toBe(true)
      })

      it("accepts encrypted application-data records", async () => {
        const [type, bytes] = await rl.recv(
          await makeEncryptedRecord({
            content: utf8ToBytes("hello world"),
            type: 23,
          })
        )
        expect(type).toBe(23)
        expect(bytesAreEqual(bytes, utf8ToBytes("hello world"))).toBe(true)
      })

      it("accepts empty encrypted application-data records", async () => {
        const [type, bytes] = await rl.recv(
          await makeEncryptedRecord({
            content: arrayToBytes([]),
            type: 23,
          })
        )
        expect(type).toBe(23)
        expect(bytes.byteLength).toBe(0)
      })

      it("correctly strips padding from padded encrypted records", async () => {
        const PAD_LENGTH = 12
        const paddedCiphertext = await makeEncryptedInnerPlaintext({
          content: utf8ToBytes("hello world"),
          padding: PAD_LENGTH,
          type: 23,
        })
        const unpaddedCiphertext = await makeEncryptedInnerPlaintext({
          content: utf8ToBytes("hello world"),
          type: 23,
        })
        expect(
          paddedCiphertext.byteLength - unpaddedCiphertext.byteLength
        ).toBe(PAD_LENGTH)
        const [type, bytes] = await rl.recv(
          await makeEncryptedRecord({ ciphertext: paddedCiphertext })
        )
        expect(type).toBe(23)
        expect(bytesAreEqual(bytes, utf8ToBytes("hello world"))).toBe(true)
      })

      it("correctly strips padding from empty encrypted records", async () => {
        const PAD_LENGTH = 12
        const paddedCiphertext = await makeEncryptedInnerPlaintext({
          content: arrayToBytes([]),
          padding: PAD_LENGTH,
          type: 23,
        })
        const unpaddedCiphertext = await makeEncryptedInnerPlaintext({
          content: arrayToBytes([]),
          type: 23,
        })
        expect(
          paddedCiphertext.byteLength - unpaddedCiphertext.byteLength
        ).toBe(PAD_LENGTH)
        const [type, bytes] = await rl.recv(
          await makeEncryptedRecord({ ciphertext: paddedCiphertext })
        )
        expect(type).toBe(23)
        expect(bytes.byteLength).toBe(0)
      })

      it("refuses to accept any data after a single record", async () => {
        await assertThrowsAsync(async () => {
          await rl.recv(
            await makeEncryptedRecord({
              outerTrailer: zeros(12),
              type: 22,
            })
          )
        }, TLSError, "DECODE_ERROR")
      })

      it("refuses to accept a partial record", async () => {
        await assertThrowsAsync(async () => {
          await rl.recv(
            (await makeEncryptedRecord({ type: 22 })).slice(0, -1)
          )
        }, TLSError, "DECODE_ERROR")
      })

      it("refuses to accept encrypted ChangeCipherSpec records", async () => {
        await assertThrowsAsync(async () => {
          await rl.recv(await makeEncryptedRecord({ type: 20 }))
        }, TLSError, "DECODE_ERROR")
      })

      it("rejects encrypted records with unknown version numbers", async () => {
        await assertThrowsAsync(async () => {
          await rl.recv(
            await makeEncryptedRecord({ outerVersion: 0x0000 })
          )
        }, TLSError, "DECODE_ERROR")
        await assertThrowsAsync(async () => {
          await rl.recv(
            await makeEncryptedRecord({ outerVersion: 0x1234 })
          )
        }, TLSError, "DECODE_ERROR")
      })

      it("rejects legacy version number on encrypted records", async () => {
        await assertThrowsAsync(async () => {
          await rl.recv(
            await makeEncryptedRecord({ outerVersion: 0x0301 })
          )
        }, TLSError, "DECODE_ERROR")
      })

      it("rejects encrypted records where the outer type is not application-data", async () => {
        await assertThrowsAsync(async () => {
          await rl.recv(await makeEncryptedRecord({ outerType: 22 }))
        }, TLSError, "DECODE_ERROR")
      })

      it("rejects encrypted records that are too large", async () => {
        await assertThrowsAsync(async () => {
          await rl.recv(
            await makeEncryptedRecord({
              outerContentLength: MAX_ENCRYPTED_RECORD_SIZE,
            })
          )
        }, TLSError, "DECODE_ERROR")
        await assertThrowsAsync(async () => {
          await rl.recv(
            await makeEncryptedRecord({
              outerContentLength: MAX_ENCRYPTED_RECORD_SIZE + 1,
            })
          )
        }, TLSError, "RECORD_OVERFLOW")
      })

      it("rejects encrypted records where the plaintext is all padding", async () => {
        await assertThrowsAsync(async () => {
          await rl.recv(
            await makeEncryptedRecord({ innerPlaintext: zeros(7) })
          )
        }, TLSError, "UNEXPECTED_MESSAGE")
      })

      it("rejects encrypted records where the ciphertext has been tampered with", async () => {
        let ciphertext = await makeEncryptedInnerPlaintext({
          content: utf8ToBytes("hello world"),
          type: 23,
        })
        ciphertext = testHelpers.tamper(ciphertext)
        await assertThrowsAsync(async () => {
          await rl.recv(await makeEncryptedRecord({ ciphertext }))
        }, TLSError, "BAD_RECORD_MAC")
      })

      it("rejects encrypted records where the additional data has been tampered with", async () => {
        const record = await makeEncryptedRecord({
          content: utf8ToBytes("hello world"),
          outerVersion: 0x0301,
          type: 23,
        })
        record[1] = 0x03
        record[2] = 0x03
        await assertThrowsAsync(async () => {
          await rl.recv(record)
        }, TLSError, "BAD_RECORD_MAC")
      })
    })
  })
})
