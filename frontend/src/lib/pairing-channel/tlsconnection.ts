/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import * as STATE from "./states"
import { assertIsBytes, noop, BufferReader } from "./utils"
import { HandshakeMessage } from "./messages"
import { KeySchedule } from "./keyschedule"
import { RecordLayer, RECORD_TYPE } from "./recordlayer"
import { TLSAlert, TLSError, ALERT_DESCRIPTION, TLSCloseNotify } from "./alerts"

type StateClass = new (conn: Connection) => STATE.State

export class Connection {
  psk: Uint8Array
  pskId: Uint8Array
  connected: Promise<void>
  _onConnectionSuccess!: (() => void) | null
  _onConnectionFailure!: ((err: Error) => void) | null
  _state: STATE.State
  _handshakeRecvBuffer: BufferReader | null
  _hasSeenChangeCipherSpec: boolean
  _recordlayer: RecordLayer
  _keyschedule: KeySchedule
  _lastPromise: Promise<unknown>

  constructor(
    psk: Uint8Array,
    pskId: Uint8Array,
    sendCallback: (data: Uint8Array) => void | Promise<void>
  ) {
    this.psk = assertIsBytes(psk)
    this.pskId = assertIsBytes(pskId)
    this.connected = new Promise<void>((resolve, reject) => {
      this._onConnectionSuccess = resolve
      this._onConnectionFailure = reject
    })
    this._state = new STATE.UNINITIALIZED(this)
    this._handshakeRecvBuffer = null
    this._hasSeenChangeCipherSpec = false
    this._recordlayer = new RecordLayer(sendCallback)
    this._keyschedule = new KeySchedule()
    this._lastPromise = Promise.resolve()
  }

  static async create(
    psk: Uint8Array,
    pskId: Uint8Array,
    sendCallback: (data: Uint8Array) => void | Promise<void>
  ): Promise<Connection> {
    return new this(psk, pskId, sendCallback)
  }

  async send(data: Uint8Array): Promise<void> {
    assertIsBytes(data)
    await this.connected
    await this._synchronized(async () => {
      await this._state.sendApplicationData(data)
    })
  }

  async recv(data: Uint8Array): Promise<Uint8Array | null> {
    assertIsBytes(data)
    return await this._synchronized(async () => {
      const [type, bytes] = await this._recordlayer.recv(data)
      switch (type) {
        case RECORD_TYPE.CHANGE_CIPHER_SPEC:
          await this._state.recvChangeCipherSpec(bytes)
          return null
        case RECORD_TYPE.ALERT:
          await this._state.recvAlertMessage(TLSAlert.fromBytes(bytes))
          return null
        case RECORD_TYPE.APPLICATION_DATA:
          return await this._state.recvApplicationData(bytes)
        case RECORD_TYPE.HANDSHAKE:
          this._handshakeRecvBuffer = new BufferReader(bytes)
          if (!this._handshakeRecvBuffer.hasMoreBytes()) {
            throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
          }
          do {
            this._handshakeRecvBuffer.incr(1)
            const mlength = this._handshakeRecvBuffer.readUint24()
            this._handshakeRecvBuffer.incr(-4)
            const messageBytes = this._handshakeRecvBuffer.readBytes(
              mlength + 4
            )
            this._keyschedule.addToTranscript(messageBytes)
            await this._state.recvHandshakeMessage(
              HandshakeMessage.fromBytes(messageBytes)
            )
          } while (this._handshakeRecvBuffer.hasMoreBytes())
          this._handshakeRecvBuffer = null
          return null
        default:
          throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
      }
    })
  }

  async close(): Promise<void> {
    await this._synchronized(async () => {
      await this._state.close()
    })
  }

  _synchronized<T>(cb: () => Promise<T>): Promise<T> {
    const nextPromise = this._lastPromise
      .then(() => {
        return cb()
      })
      .catch(async (err: Error) => {
        if (err instanceof TLSCloseNotify) {
          throw err
        }
        await this._state.handleErrorAndRethrow(err)
      }) as Promise<T>
    this._lastPromise = nextPromise.then(noop, noop)
    return nextPromise
  }

  async _transition(
    StateConstructor: StateClass,
    ...args: unknown[]
  ): Promise<void> {
    this._state = new StateConstructor(this)
    await this._state.initialize(...args)
    await this._recordlayer.flush()
  }

  async _sendApplicationData(bytes: Uint8Array): Promise<void> {
    await this._recordlayer.send(RECORD_TYPE.APPLICATION_DATA, bytes)
    await this._recordlayer.flush()
  }

  async _sendHandshakeMessage(msg: HandshakeMessage): Promise<void> {
    await this._sendHandshakeMessageBytes(msg.toBytes())
  }

  async _sendHandshakeMessageBytes(bytes: Uint8Array): Promise<void> {
    this._keyschedule.addToTranscript(bytes)
    await this._recordlayer.send(RECORD_TYPE.HANDSHAKE, bytes)
  }

  async _sendAlertMessage(err: TLSAlert): Promise<void> {
    await this._recordlayer.send(RECORD_TYPE.ALERT, err.toBytes())
    await this._recordlayer.flush()
  }

  async _sendChangeCipherSpec(): Promise<void> {
    await this._recordlayer.send(
      RECORD_TYPE.CHANGE_CIPHER_SPEC,
      new Uint8Array([0x01])
    )
    await this._recordlayer.flush()
  }

  async _setSendKey(key: Uint8Array): Promise<void> {
    return await this._recordlayer.setSendKey(key)
  }

  async _setRecvKey(key: Uint8Array): Promise<void> {
    if (
      this._handshakeRecvBuffer &&
      this._handshakeRecvBuffer.hasMoreBytes()
    ) {
      throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
    }
    return await this._recordlayer.setRecvKey(key)
  }

  _setConnectionSuccess(): void {
    if (this._onConnectionSuccess !== null) {
      this._onConnectionSuccess()
      this._onConnectionSuccess = null
      this._onConnectionFailure = null
    }
  }

  _setConnectionFailure(err: Error): void {
    if (this._onConnectionFailure !== null) {
      this._onConnectionFailure(err)
      this._onConnectionSuccess = null
      this._onConnectionFailure = null
    }
  }

  _closeForSend(alert: TLSAlert): void {
    this._recordlayer.setSendError(alert)
  }

  _closeForRecv(alert: TLSAlert): void {
    this._recordlayer.setRecvError(alert)
  }
}

export class ClientConnection extends Connection {
  static async create(
    psk: Uint8Array,
    pskId: Uint8Array,
    sendCallback: (data: Uint8Array) => void | Promise<void>
  ): Promise<ClientConnection> {
    const instance = (await super.create(
      psk,
      pskId,
      sendCallback
    )) as ClientConnection
    await instance._transition(STATE.CLIENT_START)
    return instance
  }
}

export class ServerConnection extends Connection {
  static async create(
    psk: Uint8Array,
    pskId: Uint8Array,
    sendCallback: (data: Uint8Array) => void | Promise<void>
  ): Promise<ServerConnection> {
    const instance = (await super.create(
      psk,
      pskId,
      sendCallback
    )) as ServerConnection
    await instance._transition(STATE.SERVER_START)
    return instance
  }
}
