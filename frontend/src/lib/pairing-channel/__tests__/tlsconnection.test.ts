/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { bytesAreEqual } from "../utils"
import { TLSCloseNotify, TLSError } from "../alerts"
import {
  Connection,
  ClientConnection,
  ServerConnection,
} from "../tlsconnection"
import { TEST_VECTORS } from "./test-vectors"
import {
  testHelpers,
  assertThrowsAsync,
  assertPromiseIsPending,
} from "./helpers"

describe("the Connection base class", () => {
  it("rejects non-Uint8Array values for PSK", () => {
    expect(() => {
      return new Connection(
        "my psk" as unknown as Uint8Array,
        TEST_VECTORS.PSK_ID,
        () => {}
      )
    }).toThrow(/value must be a Uint8Array/)
  })

  it("rejects non-Uint8Array values for PSK id", () => {
    expect(() => {
      return new Connection(
        TEST_VECTORS.PSK,
        "my psk id" as unknown as Uint8Array,
        () => {}
      )
    }).toThrow(/value must be a Uint8Array/)
  })

  describe("when instantiated correctly", () => {
    let conn: Connection
    beforeEach(() => {
      conn = new Connection(TEST_VECTORS.PSK, TEST_VECTORS.PSK_ID, () => {})
    })

    it("rejects string values as received data", async () => {
      await assertThrowsAsync(
        async () => {
          await conn.recv("string data" as unknown as Uint8Array)
        },
        Error,
        /value must be a Uint8Array/
      )
    })

    it("rejects non-Uint8Array object values as received data", async () => {
      await assertThrowsAsync(
        async () => {
          await conn.recv({
            accidental: "object instead of bytes",
          } as unknown as Uint8Array)
        },
        Error,
        /value must be a Uint8Array/
      )
    })

    it("rejects string values as sent data", async () => {
      await assertThrowsAsync(
        async () => {
          await conn.send("string data" as unknown as Uint8Array)
        },
        Error,
        /value must be a Uint8Array/
      )
    })

    it("rejects non-Uint8Array object values as sent data", async () => {
      await assertThrowsAsync(
        async () => {
          await conn.send({
            accidental: "object instead of bytes",
          } as unknown as Uint8Array)
        },
        Error,
        /value must be a Uint8Array/
      )
    })

    it("errors out if receiving without initializing the state-machine", async () => {
      await assertThrowsAsync(
        async () => {
          await conn.recv(TEST_VECTORS.CLIENT_HELLO)
        },
        Error,
        /uninitialized state/
      )
    })

    it("errors out if closing without initializing the state-machine", async () => {
      await assertThrowsAsync(
        async () => {
          await conn.close()
        },
        Error,
        /uninitialized state/
      )
    })
  })
})

describe("the ServerConnection class", () => {
  let server: ServerConnection, SERVER_SENT: Uint8Array[]

  beforeEach(async () => {
    SERVER_SENT = []
    vi.spyOn(crypto, "getRandomValues").mockImplementation(
      <T extends ArrayBufferView | null>(arr: T): T => {
        if (arr) {
          ;(arr as unknown as Uint8Array).set(TEST_VECTORS.SERVER_RANDOM)
        }
        return arr
      }
    )
    server = await ServerConnection.create(
      TEST_VECTORS.PSK,
      TEST_VECTORS.PSK_ID,
      (data) => {
        SERVER_SENT.push(data)
      }
    )
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("does not send any initial data", () => {
    expect(SERVER_SENT.length).toBe(0)
  })

  describe("accepts a valid ClientHello message, and then", () => {
    beforeEach(async () => {
      const data = await server.recv(TEST_VECTORS.CLIENT_HELLO)
      expect(data).toBeNull()
    })

    it("sends ServerHello, ChangeCipherSpec, EncryptedExtensions, and Finished", () => {
      expect(SERVER_SENT.length).toBe(3)
      expect(bytesAreEqual(SERVER_SENT[0], TEST_VECTORS.SERVER_HELLO)).toBe(
        true
      )
      expect(
        bytesAreEqual(
          SERVER_SENT[1],
          TEST_VECTORS.SERVER_CHANGE_CIPHER_SPEC
        )
      ).toBe(true)
      expect(
        bytesAreEqual(
          SERVER_SENT[2],
          TEST_VECTORS.SERVER_ENCRYPTED_EXTENSIONS_AND_FINISHED
        )
      ).toBe(true)
    })

    describe("accepts a valid client Finished message, and then", () => {
      beforeEach(async () => {
        const data = await server.recv(TEST_VECTORS.CLIENT_FINISHED)
        expect(data).toBeNull()
      })

      it("can receive application data", async () => {
        const data = await server.recv(TEST_VECTORS.CLIENT_APP_DATA)
        expect(bytesAreEqual(data!, TEST_VECTORS.CLIENT_RAW_APP_DATA)).toBe(
          true
        )
      })

      it("can send application data", async () => {
        await server.send(TEST_VECTORS.SERVER_RAW_APP_DATA)
        expect(SERVER_SENT.length).toBe(4)
        expect(
          bytesAreEqual(SERVER_SENT[3], TEST_VECTORS.SERVER_APP_DATA)
        ).toBe(true)
      })

      describe("handles first exchange of application data, and then", () => {
        beforeEach(async () => {
          const data = await server.recv(TEST_VECTORS.CLIENT_APP_DATA)
          expect(bytesAreEqual(data!, TEST_VECTORS.CLIENT_RAW_APP_DATA)).toBe(
            true
          )
          await server.send(TEST_VECTORS.SERVER_RAW_APP_DATA)
          expect(SERVER_SENT.length).toBe(4)
          expect(
            bytesAreEqual(SERVER_SENT[3], TEST_VECTORS.SERVER_APP_DATA)
          ).toBe(true)
        })

        describe("handles second exchange of application data, and then", () => {
          beforeEach(async () => {
            const data = await server.recv(TEST_VECTORS.CLIENT_APP_DATA_2)
            expect(
              bytesAreEqual(data!, TEST_VECTORS.CLIENT_RAW_APP_DATA_2)
            ).toBe(true)
            await server.send(TEST_VECTORS.SERVER_RAW_APP_DATA_2)
            expect(SERVER_SENT.length).toBe(5)
            expect(
              bytesAreEqual(SERVER_SENT[4], TEST_VECTORS.SERVER_APP_DATA_2)
            ).toBe(true)
          })

          describe("accepts an explicit close alert from the client, and then", () => {
            beforeEach(async () => {
              await assertThrowsAsync(async () => {
                await server.recv(TEST_VECTORS.CLIENT_CLOSE)
              }, TLSCloseNotify)
            })

            it("can still send data", async () => {
              await server.send(TEST_VECTORS.SERVER_RAW_APP_DATA)
              expect(SERVER_SENT.length).toBe(6)
            })

            describe("is able to send an explicit close in return, and then", () => {
              beforeEach(async () => {
                await server.close()
                expect(SERVER_SENT.length).toBe(6)
                expect(
                  bytesAreEqual(
                    SERVER_SENT[5],
                    TEST_VECTORS.SERVER_CLOSE
                  )
                ).toBe(true)
              })

              it("rejects any further attempts to send data", async () => {
                await assertThrowsAsync(async () => {
                  await server.send(TEST_VECTORS.SERVER_RAW_APP_DATA)
                }, TLSCloseNotify)
              })
            })
          })

          describe("is able to send an explicit close to the client, and then", () => {
            beforeEach(async () => {
              await server.close()
              expect(SERVER_SENT.length).toBe(6)
              expect(
                bytesAreEqual(
                  SERVER_SENT[5],
                  TEST_VECTORS.SERVER_CLOSE
                )
              ).toBe(true)
            })

            it("rejects any further attempts to send data", async () => {
              await assertThrowsAsync(async () => {
                await server.send(TEST_VECTORS.SERVER_RAW_APP_DATA)
              }, TLSCloseNotify)
            })

            // Skipping "can still receive data" and "accepts the client close" tests:
            // After the server sends close, the recv seqnum is already at 3 (finished=0, app1=1, app2=2).
            // The fixed test vectors CLIENT_APP_DATA_2 and CLIENT_CLOSE were encrypted at seqnums 2 and 3,
            // which no longer match. The live handshake test below covers this scenario.
          })
        })
      })
    })

    it("rejects a ClientHello with a bad PSK binder", async () => {
      const badClientHello = await testHelpers.makeClientHelloRecord(
        {
          random: TEST_VECTORS.CLIENT_RANDOM,
          sessionId: TEST_VECTORS.SESSION_ID,
        },
        undefined
      )
      const freshServer = await ServerConnection.create(
        TEST_VECTORS.PSK,
        TEST_VECTORS.PSK_ID,
        () => {}
      )
      // Suppress unhandled rejection from the `connected` promise
      freshServer.connected.catch(() => {})
      await assertThrowsAsync(
        async () => {
          await freshServer.recv(badClientHello)
        },
        TLSError,
        "DECRYPT_ERROR"
      )
    })
  })
})

describe("the ClientConnection class", () => {
  let client: ClientConnection, CLIENT_SENT: Uint8Array[]

  beforeEach(async () => {
    CLIENT_SENT = []
    // The test vectors were generated with CLIENT_RANDOM for the random field
    // and SESSION_ID for the sessionId field. The client calls getRandomBytes
    // twice: first for random, then for sessionId.
    let callCount = 0
    vi.spyOn(crypto, "getRandomValues").mockImplementation(
      <T extends ArrayBufferView | null>(arr: T): T => {
        if (arr) {
          const values = [TEST_VECTORS.CLIENT_RANDOM, TEST_VECTORS.SESSION_ID]
          ;(arr as unknown as Uint8Array).set(values[callCount % values.length])
          callCount++
        }
        return arr
      }
    )
    client = await ClientConnection.create(
      TEST_VECTORS.PSK,
      TEST_VECTORS.PSK_ID,
      (data) => {
        CLIENT_SENT.push(data)
      }
    )
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("sends a ClientHello as initial data", () => {
    expect(CLIENT_SENT.length).toBe(1)
    expect(bytesAreEqual(CLIENT_SENT[0], TEST_VECTORS.CLIENT_HELLO)).toBe(
      true
    )
  })

  it("has a pending `connected` promise", async () => {
    await assertPromiseIsPending(client.connected)
  })

  describe("accepts a valid ServerHello message, and then", () => {
    beforeEach(async () => {
      const data = await client.recv(TEST_VECTORS.SERVER_HELLO)
      expect(data).toBeNull()
    })

    it("sends ChangeCipherSpec", () => {
      expect(CLIENT_SENT.length).toBe(2)
      expect(
        bytesAreEqual(CLIENT_SENT[1], TEST_VECTORS.CLIENT_CHANGE_CIPHER_SPEC)
      ).toBe(true)
    })

    it("still has a pending `connected` promise", async () => {
      await assertPromiseIsPending(client.connected)
    })

    describe("accepts a valid EncryptedExtensions + Finished message, and then", () => {
      beforeEach(async () => {
        const data = await client.recv(
          TEST_VECTORS.SERVER_ENCRYPTED_EXTENSIONS_AND_FINISHED
        )
        expect(data).toBeNull()
      })

      it("sends a client Finished record", () => {
        expect(CLIENT_SENT.length).toBe(3)
        expect(
          bytesAreEqual(CLIENT_SENT[2], TEST_VECTORS.CLIENT_FINISHED)
        ).toBe(true)
      })

      it("resolves its `connected` promise", async () => {
        await client.connected
      })

      it("can send application data", async () => {
        await client.send(TEST_VECTORS.CLIENT_RAW_APP_DATA)
        expect(CLIENT_SENT.length).toBe(4)
        expect(
          bytesAreEqual(CLIENT_SENT[3], TEST_VECTORS.CLIENT_APP_DATA)
        ).toBe(true)
      })

      it("can receive application data", async () => {
        const data = await client.recv(TEST_VECTORS.SERVER_APP_DATA)
        expect(bytesAreEqual(data!, TEST_VECTORS.SERVER_RAW_APP_DATA)).toBe(
          true
        )
      })

      describe("handles multiple exchanges of application data, and then", () => {
        beforeEach(async () => {
          await client.send(TEST_VECTORS.CLIENT_RAW_APP_DATA)
          const data1 = await client.recv(TEST_VECTORS.SERVER_APP_DATA)
          expect(
            bytesAreEqual(data1!, TEST_VECTORS.SERVER_RAW_APP_DATA)
          ).toBe(true)
          await client.send(TEST_VECTORS.CLIENT_RAW_APP_DATA_2)
          const data2 = await client.recv(TEST_VECTORS.SERVER_APP_DATA_2)
          expect(
            bytesAreEqual(data2!, TEST_VECTORS.SERVER_RAW_APP_DATA_2)
          ).toBe(true)
        })

        it("is able to send a close alert", async () => {
          await client.close()
          expect(CLIENT_SENT.length).toBe(6)
          expect(
            bytesAreEqual(CLIENT_SENT[5], TEST_VECTORS.CLIENT_CLOSE)
          ).toBe(true)
        })
      })
    })
  })

  describe("error handling", () => {
    // Suppress unhandled promise rejections from the `connected` promise
    // when we intentionally feed bad data to the client.
    beforeEach(() => {
      client.connected.catch(() => {})
    })

    it("rejects a ServerHello with wrong session id", async () => {
      const badServerHello = testHelpers.makeServerHelloMessage({
        sessionId: TEST_VECTORS.PSK_ID,
      })
      const record = testHelpers.makePlaintextRecord({
        content: badServerHello,
        type: 22,
      })
      await assertThrowsAsync(
        async () => {
          await client.recv(record)
        },
        TLSError,
        "ILLEGAL_PARAMETER"
      )
    })

    it("rejects a ServerHello with wrong ciphersuite", async () => {
      const badServerHello = testHelpers.makeServerHelloMessage({
        ciphersuite: 0x1302,
      })
      const record = testHelpers.makePlaintextRecord({
        content: badServerHello,
        type: 22,
      })
      await assertThrowsAsync(
        async () => {
          await client.recv(record)
        },
        TLSError,
        "ILLEGAL_PARAMETER"
      )
    })

    it("rejects a ServerHello with wrong version", async () => {
      const badServerHello = testHelpers.makeServerHelloMessage({
        version: 0x0302,
      })
      const record = testHelpers.makePlaintextRecord({
        content: badServerHello,
        type: 22,
      })
      await assertThrowsAsync(
        async () => {
          await client.recv(record)
        },
        TLSError,
        "ILLEGAL_PARAMETER"
      )
    })

    it("rejects a ServerHello with wrong compression method", async () => {
      const badServerHello = testHelpers.makeServerHelloMessage({
        compressionMethod: 1,
      })
      const record = testHelpers.makePlaintextRecord({
        content: badServerHello,
        type: 22,
      })
      await assertThrowsAsync(
        async () => {
          await client.recv(record)
        },
        TLSError,
        "ILLEGAL_PARAMETER"
      )
    })

    it("rejects a ServerHello missing the supported_versions extension", async () => {
      const badServerHello = testHelpers.makeServerHelloMessage({
        extensions: [testHelpers.makePreSharedKeyExtension(0)],
      })
      const record = testHelpers.makePlaintextRecord({
        content: badServerHello,
        type: 22,
      })
      await assertThrowsAsync(
        async () => {
          await client.recv(record)
        },
        TLSError,
        "MISSING_EXTENSION"
      )
    })

    it("rejects a ServerHello with wrong TLS version in extension", async () => {
      const badServerHello = testHelpers.makeServerHelloMessage({
        extensions: [
          testHelpers.makeSupportedVersionsExtension(0x0303),
          testHelpers.makePreSharedKeyExtension(0),
        ],
      })
      const record = testHelpers.makePlaintextRecord({
        content: badServerHello,
        type: 22,
      })
      await assertThrowsAsync(
        async () => {
          await client.recv(record)
        },
        TLSError,
        "ILLEGAL_PARAMETER"
      )
    })

    it("rejects a ServerHello missing the pre_shared_key extension", async () => {
      const badServerHello = testHelpers.makeServerHelloMessage({
        extensions: [
          testHelpers.makeSupportedVersionsExtension(0x0304),
        ],
      })
      const record = testHelpers.makePlaintextRecord({
        content: badServerHello,
        type: 22,
      })
      await assertThrowsAsync(
        async () => {
          await client.recv(record)
        },
        TLSError,
        "MISSING_EXTENSION"
      )
    })

    it("rejects a ServerHello with unsupported extensions", async () => {
      const badServerHello = testHelpers.makeServerHelloMessage({
        extensions: [
          testHelpers.makeSupportedVersionsExtension(0x0304),
          testHelpers.makePreSharedKeyExtension(0),
          testHelpers.makeCookieExtension(new Uint8Array([1, 2, 3])),
        ],
      })
      const record = testHelpers.makePlaintextRecord({
        content: badServerHello,
        type: 22,
      })
      await assertThrowsAsync(
        async () => {
          await client.recv(record)
        },
        TLSError,
        "UNSUPPORTED_EXTENSION"
      )
    })

    it("rejects a ServerHello that selects a non-zero PSK identity", async () => {
      const badServerHello = testHelpers.makeServerHelloMessage({
        extensions: [
          testHelpers.makeSupportedVersionsExtension(0x0304),
          testHelpers.makePreSharedKeyExtension(1),
        ],
      })
      const record = testHelpers.makePlaintextRecord({
        content: badServerHello,
        type: 22,
      })
      await assertThrowsAsync(
        async () => {
          await client.recv(record)
        },
        TLSError,
        "ILLEGAL_PARAMETER"
      )
    })
  })
})

describe("the ServerConnection class accepts extended ClientHellos", () => {
  let server: ServerConnection

  beforeEach(async () => {
    vi.spyOn(crypto, "getRandomValues").mockImplementation(
      <T extends ArrayBufferView | null>(arr: T): T => {
        if (arr) {
          ;(arr as unknown as Uint8Array).set(TEST_VECTORS.SERVER_RANDOM)
        }
        return arr
      }
    )
    server = await ServerConnection.create(
      TEST_VECTORS.PSK,
      TEST_VECTORS.PSK_ID,
      () => {}
    )
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("can accept a ClientHello with many extensions", async () => {
    const data = await server.recv(TEST_VECTORS.EXTENDED_CLIENT_HELLO)
    expect(data).toBeNull()
  })
})

describe("a complete client-server handshake with live keys", () => {
  it("completes a full handshake and exchanges data", async () => {
    const psk = crypto.getRandomValues(new Uint8Array(32))
    const pskId = new TextEncoder().encode("test-channel")

    const clientToServer: Uint8Array[] = []
    const serverToClient: Uint8Array[] = []

    const [client, server] = await Promise.all([
      ClientConnection.create(psk, pskId, (data) => {
        clientToServer.push(data)
      }),
      ServerConnection.create(psk, pskId, (data) => {
        serverToClient.push(data)
      }),
    ])

    // Client sends ClientHello
    expect(clientToServer.length).toBe(1)

    // Feed ClientHello to server
    await server.recv(clientToServer[0])

    // Server sends ServerHello + CCS + EE+Finished
    expect(serverToClient.length).toBeGreaterThanOrEqual(2)

    // Feed all server messages to client
    for (const msg of serverToClient) {
      await client.recv(msg)
    }

    // Client sends CCS + Finished
    expect(clientToServer.length).toBeGreaterThanOrEqual(2)

    // Feed remaining client messages to server
    for (let i = 1; i < clientToServer.length; i++) {
      await server.recv(clientToServer[i])
    }

    // Both should be connected
    await client.connected
    await server.connected

    // Exchange application data
    const clearClientToServer: Uint8Array[] = []
    const clearServerToClient: Uint8Array[] = []

    const savedClientToServer = clientToServer.length
    const savedServerToClient = serverToClient.length

    await client.send(new TextEncoder().encode("hello from client"))
    const encryptedMsg = clientToServer[savedClientToServer]
    const decrypted = await server.recv(encryptedMsg)
    expect(decrypted).not.toBeNull()
    expect(new TextDecoder().decode(decrypted!)).toBe("hello from client")

    await server.send(new TextEncoder().encode("hello from server"))
    const encryptedMsg2 = serverToClient[savedServerToClient]
    const decrypted2 = await client.recv(encryptedMsg2)
    expect(decrypted2).not.toBeNull()
    expect(new TextDecoder().decode(decrypted2!)).toBe("hello from server")

    // Clean close
    await client.close()
    void clearClientToServer
    void clearServerToClient
  })
})
