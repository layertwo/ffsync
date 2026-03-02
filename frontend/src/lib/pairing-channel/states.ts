/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { bytesAreEqual, BufferWriter, zeros } from "./utils"
import { getRandomBytes, HASH_LENGTH } from "./crypto"
import { TLSAlert, TLSCloseNotify, TLSError, ALERT_DESCRIPTION } from "./alerts"
import {
  ClientHello,
  ServerHello,
  EncryptedExtensions,
  Finished,
  NewSessionTicket,
  type HandshakeMessage,
} from "./messages"
import {
  SupportedVersionsExtension,
  PskKeyExchangeModesExtension,
  PreSharedKeyExtension,
  EXTENSION_TYPE,
} from "./extensions"
import { VERSION_TLS_1_3, PSK_MODE_KE } from "./constants"
import type { Connection } from "./tlsconnection"

export class State {
  conn: Connection

  constructor(conn: Connection) {
    this.conn = conn
  }

  async initialize(..._args: unknown[]): Promise<void> {
    // By default, nothing to do when entering the state.
  }

  async sendApplicationData(_bytes: Uint8Array): Promise<void> {
    throw new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
  }

  async recvApplicationData(_bytes: Uint8Array): Promise<Uint8Array> {
    throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
  }

  async recvHandshakeMessage(_msg: HandshakeMessage): Promise<void> {
    throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
  }

  async recvAlertMessage(alert: TLSAlert): Promise<void> {
    switch (alert.description) {
      case ALERT_DESCRIPTION.CLOSE_NOTIFY:
        this.conn._closeForRecv(alert)
        throw alert
      default:
        return await this.handleErrorAndRethrow(alert)
    }
  }

  async recvChangeCipherSpec(_bytes: Uint8Array): Promise<void> {
    throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
  }

  async handleErrorAndRethrow(err: Error): Promise<never> {
    let alert: TLSAlert = err as TLSAlert
    if (!(alert instanceof TLSAlert)) {
      alert = new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
    }
    try {
      await this.conn._sendAlertMessage(alert)
    } catch {
      // ignore
    }
    await this.conn._transition(ERROR, err)
    throw err
  }

  async close(): Promise<void> {
    const alert = new TLSCloseNotify()
    await this.conn._sendAlertMessage(alert)
    this.conn._closeForSend(alert)
  }
}

export class UNINITIALIZED extends State {
  async initialize(): Promise<void> {
    throw new Error("uninitialized state")
  }
  async sendApplicationData(_bytes: Uint8Array): Promise<void> {
    throw new Error("uninitialized state")
  }
  async recvApplicationData(_bytes: Uint8Array): Promise<Uint8Array> {
    throw new Error("uninitialized state")
  }
  async recvHandshakeMessage(_msg: HandshakeMessage): Promise<void> {
    throw new Error("uninitialized state")
  }
  async recvChangeCipherSpec(_bytes: Uint8Array): Promise<void> {
    throw new Error("uninitialized state")
  }
  async handleErrorAndRethrow(err: Error): Promise<never> {
    throw err
  }
  async close(): Promise<void> {
    throw new Error("uninitialized state")
  }
}

export class ERROR extends State {
  error!: Error

  async initialize(err: Error): Promise<void> {
    this.error = err
    this.conn._setConnectionFailure(err)
    this.conn._recordlayer.setSendError(err)
    this.conn._recordlayer.setRecvError(err)
  }
  async sendApplicationData(_bytes: Uint8Array): Promise<void> {
    throw this.error
  }
  async recvApplicationData(_bytes: Uint8Array): Promise<Uint8Array> {
    throw this.error
  }
  async recvHandshakeMessage(_msg: HandshakeMessage): Promise<void> {
    throw this.error
  }
  async recvAlertMessage(_err: TLSAlert): Promise<void> {
    throw this.error
  }
  async recvChangeCipherSpec(_bytes: Uint8Array): Promise<void> {
    throw this.error
  }
  async handleErrorAndRethrow(err: Error): Promise<never> {
    throw err
  }
  async close(): Promise<void> {
    throw this.error
  }
}

export class CONNECTED extends State {
  async initialize(): Promise<void> {
    this.conn._setConnectionSuccess()
  }
  async sendApplicationData(bytes: Uint8Array): Promise<void> {
    await this.conn._sendApplicationData(bytes)
  }
  async recvApplicationData(bytes: Uint8Array): Promise<Uint8Array> {
    return bytes
  }
  async recvChangeCipherSpec(_bytes: Uint8Array): Promise<void> {
    throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
  }
}

class MidHandshakeState extends State {
  async recvChangeCipherSpec(bytes: Uint8Array): Promise<void> {
    if (this.conn._hasSeenChangeCipherSpec) {
      throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
    }
    if (bytes.byteLength !== 1 || bytes[0] !== 1) {
      throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
    }
    this.conn._hasSeenChangeCipherSpec = true
  }
}

export class CLIENT_START extends State {
  async initialize(): Promise<void> {
    const keyschedule = this.conn._keyschedule
    await keyschedule.addPSK(this.conn.psk)
    const clientHello = new ClientHello(
      await getRandomBytes(32),
      await getRandomBytes(32),
      [
        new SupportedVersionsExtension([VERSION_TLS_1_3]),
        new PskKeyExchangeModesExtension([PSK_MODE_KE]),
        new PreSharedKeyExtension([this.conn.pskId], [zeros(HASH_LENGTH)], null),
      ]
    )
    const buf = new BufferWriter()
    clientHello.write(buf)
    const PSK_BINDERS_SIZE = HASH_LENGTH + 1 + 2
    const truncatedTranscript = buf.slice(0, buf.tell() - PSK_BINDERS_SIZE)
    const pskBinder = await keyschedule.calculateFinishedMAC(
      keyschedule.extBinderKey!,
      truncatedTranscript
    )
    buf.incr(-HASH_LENGTH)
    buf.writeBytes(pskBinder)
    await this.conn._sendHandshakeMessageBytes(buf.flush())
    await this.conn._transition(CLIENT_WAIT_SH, clientHello.sessionId)
  }
}

class CLIENT_WAIT_SH extends State {
  _sessionId!: Uint8Array

  async initialize(sessionId: Uint8Array): Promise<void> {
    this._sessionId = sessionId
  }
  async recvHandshakeMessage(msg: HandshakeMessage): Promise<void> {
    if (!(msg instanceof ServerHello)) {
      throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
    }
    if (!bytesAreEqual(msg.sessionId, this._sessionId)) {
      throw new TLSError(ALERT_DESCRIPTION.ILLEGAL_PARAMETER)
    }
    const pskExt = msg.extensions.get(EXTENSION_TYPE.PRE_SHARED_KEY) as
      | { selectedIdentity: number }
      | undefined
    if (!pskExt) {
      throw new TLSError(ALERT_DESCRIPTION.MISSING_EXTENSION)
    }
    if (msg.extensions.size !== 2) {
      throw new TLSError(ALERT_DESCRIPTION.UNSUPPORTED_EXTENSION)
    }
    if (pskExt.selectedIdentity !== 0) {
      throw new TLSError(ALERT_DESCRIPTION.ILLEGAL_PARAMETER)
    }
    await this.conn._keyschedule.addECDHE(null)
    // If we sent a non-empty sessionId, send a CCS for backward compatibility
    // before switching to encrypted keys.
    if (this._sessionId.byteLength > 0) {
      await this.conn._sendChangeCipherSpec()
    }
    await this.conn._setSendKey(
      this.conn._keyschedule.clientHandshakeTrafficSecret!
    )
    await this.conn._setRecvKey(
      this.conn._keyschedule.serverHandshakeTrafficSecret!
    )
    await this.conn._transition(CLIENT_WAIT_EE)
  }
}

class CLIENT_WAIT_EE extends MidHandshakeState {
  async recvHandshakeMessage(msg: HandshakeMessage): Promise<void> {
    if (!(msg instanceof EncryptedExtensions)) {
      throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
    }
    if (msg.extensions.size !== 0) {
      throw new TLSError(ALERT_DESCRIPTION.UNSUPPORTED_EXTENSION)
    }
    const keyschedule = this.conn._keyschedule
    const serverFinishedTranscript = keyschedule.getTranscript()
    await this.conn._transition(
      CLIENT_WAIT_FINISHED,
      serverFinishedTranscript
    )
  }
}

class CLIENT_WAIT_FINISHED extends State {
  _serverFinishedTranscript!: Uint8Array

  async initialize(serverFinishedTranscript: Uint8Array): Promise<void> {
    this._serverFinishedTranscript = serverFinishedTranscript
  }
  async recvHandshakeMessage(msg: HandshakeMessage): Promise<void> {
    if (!(msg instanceof Finished)) {
      throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
    }
    const keyschedule = this.conn._keyschedule
    await keyschedule.verifyFinishedMAC(
      keyschedule.serverHandshakeTrafficSecret!,
      msg.verifyData,
      this._serverFinishedTranscript
    )
    const clientFinishedMAC = await keyschedule.calculateFinishedMAC(
      keyschedule.clientHandshakeTrafficSecret!
    )
    await keyschedule.finalize()
    await this.conn._sendHandshakeMessage(new Finished(clientFinishedMAC))
    await this.conn._setSendKey(
      keyschedule.clientApplicationTrafficSecret!
    )
    await this.conn._setRecvKey(
      keyschedule.serverApplicationTrafficSecret!
    )
    await this.conn._transition(CLIENT_CONNECTED)
  }
}

export class CLIENT_CONNECTED extends CONNECTED {
  async recvHandshakeMessage(msg: HandshakeMessage): Promise<void> {
    if (!(msg instanceof NewSessionTicket)) {
      throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
    }
  }
}

export class SERVER_START extends State {
  async recvHandshakeMessage(msg: HandshakeMessage): Promise<void> {
    if (!(msg instanceof ClientHello)) {
      throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
    }
    const pskExt = msg.extensions.get(EXTENSION_TYPE.PRE_SHARED_KEY) as
      | { identities: Uint8Array[]; binders: Uint8Array[] }
      | undefined
    const pskModesExt = msg.extensions.get(
      EXTENSION_TYPE.PSK_KEY_EXCHANGE_MODES
    ) as { modes: number[] } | undefined
    if (!pskExt || !pskModesExt) {
      throw new TLSError(ALERT_DESCRIPTION.MISSING_EXTENSION)
    }
    if (pskModesExt.modes.indexOf(PSK_MODE_KE) === -1) {
      throw new TLSError(ALERT_DESCRIPTION.HANDSHAKE_FAILURE)
    }
    const pskIndex = pskExt.identities.findIndex((pskId) =>
      bytesAreEqual(pskId, this.conn.pskId)
    )
    if (pskIndex === -1) {
      throw new TLSError(ALERT_DESCRIPTION.UNKNOWN_PSK_IDENTITY)
    }
    await this.conn._keyschedule.addPSK(this.conn.psk)
    const keyschedule = this.conn._keyschedule
    const transcript = keyschedule.getTranscript()
    let pskBindersSize = 2
    for (const binder of pskExt.binders) {
      pskBindersSize += binder.byteLength + 1
    }
    await keyschedule.verifyFinishedMAC(
      keyschedule.extBinderKey!,
      pskExt.binders[pskIndex],
      transcript.slice(0, -pskBindersSize)
    )
    await this.conn._transition(SERVER_NEGOTIATED, msg.sessionId, pskIndex)
  }
}

class SERVER_NEGOTIATED extends MidHandshakeState {
  async initialize(
    sessionId: Uint8Array,
    pskIndex: number
  ): Promise<void> {
    await this.conn._sendHandshakeMessage(
      new ServerHello(await getRandomBytes(32), sessionId, [
        new SupportedVersionsExtension(null, VERSION_TLS_1_3),
        new PreSharedKeyExtension(null, null, pskIndex),
      ])
    )
    if (sessionId.byteLength > 0) {
      await this.conn._sendChangeCipherSpec()
    }
    const keyschedule = this.conn._keyschedule
    await keyschedule.addECDHE(null)
    await this.conn._setSendKey(keyschedule.serverHandshakeTrafficSecret!)
    await this.conn._setRecvKey(keyschedule.clientHandshakeTrafficSecret!)
    await this.conn._sendHandshakeMessage(new EncryptedExtensions([]))
    const serverFinishedMAC = await keyschedule.calculateFinishedMAC(
      keyschedule.serverHandshakeTrafficSecret!
    )
    await this.conn._sendHandshakeMessage(new Finished(serverFinishedMAC))
    const clientFinishedTranscript = keyschedule.getTranscript()
    const clientHandshakeTrafficSecret =
      keyschedule.clientHandshakeTrafficSecret!
    await keyschedule.finalize()
    await this.conn._setSendKey(keyschedule.serverApplicationTrafficSecret!)
    await this.conn._transition(
      SERVER_WAIT_FINISHED,
      clientHandshakeTrafficSecret,
      clientFinishedTranscript
    )
  }
}

class SERVER_WAIT_FINISHED extends MidHandshakeState {
  _clientHandshakeTrafficSecret!: Uint8Array | null
  _clientFinishedTranscript!: Uint8Array | null

  async initialize(
    clientHandshakeTrafficSecret: Uint8Array,
    clientFinishedTranscript: Uint8Array
  ): Promise<void> {
    this._clientHandshakeTrafficSecret = clientHandshakeTrafficSecret
    this._clientFinishedTranscript = clientFinishedTranscript
  }
  async recvHandshakeMessage(msg: HandshakeMessage): Promise<void> {
    if (!(msg instanceof Finished)) {
      throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
    }
    const keyschedule = this.conn._keyschedule
    await keyschedule.verifyFinishedMAC(
      this._clientHandshakeTrafficSecret!,
      msg.verifyData,
      this._clientFinishedTranscript!
    )
    this._clientHandshakeTrafficSecret = this._clientFinishedTranscript = null
    await this.conn._setRecvKey(keyschedule.clientApplicationTrafficSecret!)
    await this.conn._transition(CONNECTED)
  }
}
