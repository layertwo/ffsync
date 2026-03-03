/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// A wrapper that combines a WebSocket to the channelserver
// with some client-side encryption for securing the channel.

import { ClientConnection, ServerConnection } from "./tlsconnection"
import { TLSCloseNotify, TLSError } from "./alerts"
import {
  base64urlToBytes,
  bytesToBase64url,
  bytesToHex,
  bytesToUtf8,
  hexToBytes,
  utf8ToBytes,
} from "./utils"

const CLOSE_FLUSH_BUFFER_INTERVAL_MS = 200
const CLOSE_FLUSH_BUFFER_MAX_TRIES = 5

export class PairingChannel extends EventTarget {
  _channelId: string
  _channelKey: Uint8Array
  _socket: WebSocket | null
  _connection: ClientConnection | ServerConnection | null
  _selfClosed: boolean
  _peerClosed: boolean

  constructor(
    channelId: string,
    channelKey: Uint8Array,
    socket: WebSocket,
    connection: ClientConnection | ServerConnection
  ) {
    super()
    this._channelId = channelId
    this._channelKey = channelKey
    this._socket = socket
    this._connection = connection
    this._selfClosed = false
    this._peerClosed = false
    this._setupListeners()
  }

  /**
   * Create a new pairing channel.
   *
   * This will open a channel on the channelserver, and generate a random client-side
   * encryption key. When the promise resolves, `this.channelId` and `this.channelKey`
   * can be transferred to another client to allow it to securely connect to the channel.
   *
   * @returns Promise<PairingChannel>
   */
  static create(channelServerURI: string): Promise<PairingChannel> {
    const wsURI = channelServerURI.replace(/\/+$/, "")
    const channelKey = crypto.getRandomValues(new Uint8Array(32))
    // The one who creates the channel plays the role of 'server' in the underlying TLS exchange.
    return this._makePairingChannel(wsURI, ServerConnection, channelKey)
  }

  /**
   * Connect to an existing pairing channel.
   *
   * This will connect to a channel on the channelserver previously established by
   * another client calling `create`. The `channelId` and `channelKey` must have been
   * obtained via some out-of-band mechanism (such as by scanning from a QR code).
   *
   * @returns Promise<PairingChannel>
   */
  static connect(
    channelServerURI: string,
    channelId: string,
    channelKey: Uint8Array
  ): Promise<PairingChannel> {
    const wsURI = `${channelServerURI.replace(/\/+$/, "")}?channelId=${channelId}`
    // The one who connects to an existing channel plays the role of 'client'
    // in the underlying TLS exchange.
    return this._makePairingChannel(wsURI, ClientConnection, channelKey)
  }

  static _makePairingChannel(
    wsUri: string,
    ConnectionClass: typeof ClientConnection | typeof ServerConnection,
    psk: Uint8Array
  ): Promise<PairingChannel> {
    const socket = new WebSocket(wsUri)
    return new Promise((resolve, reject) => {
      let stopListening: () => void
      const onConnectionError = async () => {
        stopListening()
        reject(new Error("Error while creating the pairing channel"))
      }
      const onFirstMessage = async (event: MessageEvent) => {
        stopListening()
        try {
          const { channelid: channelId } = JSON.parse(event.data)
          const pskId = utf8ToBytes(channelId)
          const connection = await ConnectionClass.create(
            psk,
            pskId,
            (data: Uint8Array) => {
              socket.send(bytesToBase64url(data))
            }
          )
          const instance = new this(channelId, psk, socket, connection)
          resolve(instance)
        } catch (err) {
          reject(err)
        }
      }
      stopListening = () => {
        socket.removeEventListener("close", onConnectionError)
        socket.removeEventListener("error", onConnectionError)
        socket.removeEventListener("message", onFirstMessage)
      }
      socket.addEventListener("close", onConnectionError)
      socket.addEventListener("error", onConnectionError)
      socket.addEventListener("message", onFirstMessage)
    })
  }

  _setupListeners(): void {
    this._socket!.addEventListener("message", async (event: MessageEvent) => {
      try {
        const channelServerEnvelope = JSON.parse(event.data)
        const payload = await this._connection!.recv(
          base64urlToBytes(channelServerEnvelope.message)
        )
        if (payload !== null) {
          const data = JSON.parse(bytesToUtf8(payload))
          this.dispatchEvent(
            new CustomEvent("message", {
              detail: {
                data,
                sender: channelServerEnvelope.sender,
              },
            })
          )
        }
      } catch (error) {
        let event: CustomEvent
        if (error instanceof TLSCloseNotify) {
          this._peerClosed = true
          if (this._selfClosed) {
            this._shutdown()
          }
          event = new CustomEvent("close")
        } else {
          event = new CustomEvent("error", {
            detail: {
              error,
            },
          })
        }
        this.dispatchEvent(event)
      }
    })
    this._socket!.addEventListener("error", () => {
      this._shutdown()
      this.dispatchEvent(
        new CustomEvent("error", {
          detail: {
            error: new Error("WebSocket error."),
          },
        })
      )
    })
    this._socket!.addEventListener("close", () => {
      this._shutdown()
      if (!this._peerClosed) {
        this.dispatchEvent(
          new CustomEvent("error", {
            detail: {
              error: new Error("WebSocket unexpectedly closed"),
            },
          })
        )
      }
    })
  }

  async send(data: Record<string, unknown>): Promise<void> {
    const payload = utf8ToBytes(JSON.stringify(data))
    await this._connection!.send(payload)
  }

  async close(): Promise<void> {
    this._selfClosed = true
    await this._connection!.close()
    try {
      let tries = 0
      while (this._socket!.bufferedAmount > 0) {
        if (++tries > CLOSE_FLUSH_BUFFER_MAX_TRIES) {
          throw new Error("Could not flush the outgoing buffer in time.")
        }
        await new Promise((res) => setTimeout(res, CLOSE_FLUSH_BUFFER_INTERVAL_MS))
      }
    } finally {
      if (this._peerClosed) {
        this._shutdown()
      }
    }
  }

  _shutdown(): void {
    if (this._socket) {
      this._socket.close()
      this._socket = null
      this._connection = null
    }
  }

  get closed(): boolean {
    return !this._socket || this._socket.readyState === 3
  }

  get channelId(): string {
    return this._channelId
  }

  get channelKey(): Uint8Array {
    return this._channelKey
  }
}

// Re-export helpful utilities for calling code to use.
export {
  base64urlToBytes,
  bytesToBase64url,
  bytesToHex,
  bytesToUtf8,
  hexToBytes,
  TLSCloseNotify,
  TLSError,
  utf8ToBytes,
}
