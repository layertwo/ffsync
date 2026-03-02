/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { BufferWriter, BufferReader } from "./utils"
import { ALERT_DESCRIPTION, TLSError } from "./alerts"
import { HASH_LENGTH } from "./crypto"
import {
  Extension,
  EXTENSION_TYPE,
  type ExtensionLike,
} from "./extensions"
import {
  VERSION_TLS_1_2,
  VERSION_TLS_1_3,
  TLS_AES_128_GCM_SHA256,
  VERSION_TLS_1_0,
} from "./constants"

export const HANDSHAKE_TYPE = {
  CLIENT_HELLO: 1,
  SERVER_HELLO: 2,
  NEW_SESSION_TICKET: 4,
  ENCRYPTED_EXTENSIONS: 8,
  FINISHED: 20,
} as const

type ExtensionMap = Map<number, ExtensionLike> & { lastSeenExtension?: number }

export class HandshakeMessage {
  get TYPE_TAG(): number {
    throw new Error("not implemented")
  }

  static fromBytes(bytes: Uint8Array): HandshakeMessage {
    const buf = new BufferReader(bytes)
    const msg = this.read(buf)
    if (buf.hasMoreBytes()) {
      throw new TLSError(ALERT_DESCRIPTION.DECODE_ERROR)
    }
    return msg
  }

  toBytes(): Uint8Array {
    const buf = new BufferWriter()
    this.write(buf)
    return buf.flush()
  }

  static read(buf: BufferReader): HandshakeMessage {
    const type = buf.readUint8()
    let msg: HandshakeMessage | null = null
    buf.readVector24((buf) => {
      switch (type) {
        case HANDSHAKE_TYPE.CLIENT_HELLO:
          msg = ClientHello._read(buf)
          break
        case HANDSHAKE_TYPE.SERVER_HELLO:
          msg = ServerHello._read(buf)
          break
        case HANDSHAKE_TYPE.NEW_SESSION_TICKET:
          msg = NewSessionTicket._read(buf)
          break
        case HANDSHAKE_TYPE.ENCRYPTED_EXTENSIONS:
          msg = EncryptedExtensions._read(buf)
          break
        case HANDSHAKE_TYPE.FINISHED:
          msg = Finished._read(buf)
          break
      }
      if (buf.hasMoreBytes()) {
        throw new TLSError(ALERT_DESCRIPTION.DECODE_ERROR)
      }
    })
    if (msg === null) {
      throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
    }
    return msg
  }

  write(buf: BufferWriter): void {
    buf.writeUint8(this.TYPE_TAG)
    buf.writeVector24((buf) => {
      this._write(buf)
    })
  }

  static _read(_buf: BufferReader): HandshakeMessage {
    throw new Error("not implemented")
  }

  _write(_buf: BufferWriter): void {
    throw new Error("not implemented")
  }

  static _readExtensions(
    messageType: number,
    buf: BufferReader
  ): ExtensionMap {
    const extensions: ExtensionMap = new Map()
    buf.readVector16((buf) => {
      const ext = Extension.read(messageType, buf)
      if (extensions.has(ext.TYPE_TAG)) {
        throw new TLSError(ALERT_DESCRIPTION.DECODE_ERROR)
      }
      extensions.set(ext.TYPE_TAG, ext)
      extensions.lastSeenExtension = ext.TYPE_TAG
    })
    return extensions
  }

  _writeExtensions(buf: BufferWriter, extensions: ExtensionLike[]): void {
    buf.writeVector16((buf) => {
      extensions.forEach((ext) => {
        ext.write(this.TYPE_TAG, buf)
      })
    })
  }
}

export class ClientHello extends HandshakeMessage {
  random: Uint8Array
  sessionId: Uint8Array
  extensions: ExtensionMap

  constructor(
    random: Uint8Array,
    sessionId: Uint8Array,
    extensions: ExtensionMap | ExtensionLike[]
  ) {
    super()
    this.random = random
    this.sessionId = sessionId
    if (Array.isArray(extensions)) {
      const map: ExtensionMap = new Map()
      for (const ext of extensions) {
        map.set(ext.TYPE_TAG, ext)
        map.lastSeenExtension = ext.TYPE_TAG
      }
      this.extensions = map
    } else {
      this.extensions = extensions
    }
  }

  get TYPE_TAG(): number {
    return HANDSHAKE_TYPE.CLIENT_HELLO
  }

  static _read(buf: BufferReader): ClientHello {
    if (buf.readUint16() < VERSION_TLS_1_0) {
      throw new TLSError(ALERT_DESCRIPTION.PROTOCOL_VERSION)
    }
    const random = buf.readBytes(32)
    const sessionId = buf.readVectorBytes8()
    let found = false
    buf.readVector16((buf) => {
      const cipherSuite = buf.readUint16()
      if (cipherSuite === TLS_AES_128_GCM_SHA256) {
        found = true
      }
    })
    if (!found) {
      throw new TLSError(ALERT_DESCRIPTION.HANDSHAKE_FAILURE)
    }
    const legacyCompressionMethods = buf.readVectorBytes8()
    if (legacyCompressionMethods.byteLength !== 1) {
      throw new TLSError(ALERT_DESCRIPTION.ILLEGAL_PARAMETER)
    }
    if (legacyCompressionMethods[0] !== 0x00) {
      throw new TLSError(ALERT_DESCRIPTION.ILLEGAL_PARAMETER)
    }
    const extensions = this._readExtensions(HANDSHAKE_TYPE.CLIENT_HELLO, buf)
    if (!extensions.has(EXTENSION_TYPE.SUPPORTED_VERSIONS)) {
      throw new TLSError(ALERT_DESCRIPTION.MISSING_EXTENSION)
    }
    const svExt = extensions.get(EXTENSION_TYPE.SUPPORTED_VERSIONS) as
      unknown as { versions: number[] }
    if (svExt.versions.indexOf(VERSION_TLS_1_3) === -1) {
      throw new TLSError(ALERT_DESCRIPTION.PROTOCOL_VERSION)
    }
    if (extensions.has(EXTENSION_TYPE.PRE_SHARED_KEY)) {
      if (extensions.lastSeenExtension !== EXTENSION_TYPE.PRE_SHARED_KEY) {
        throw new TLSError(ALERT_DESCRIPTION.ILLEGAL_PARAMETER)
      }
    }
    return new this(random, sessionId, extensions)
  }

  _write(buf: BufferWriter): void {
    buf.writeUint16(VERSION_TLS_1_2)
    buf.writeBytes(this.random)
    buf.writeVectorBytes8(this.sessionId)
    buf.writeVector16((buf) => {
      buf.writeUint16(TLS_AES_128_GCM_SHA256)
    })
    buf.writeVectorBytes8(new Uint8Array(1))
    this._writeExtensions(buf, Array.from(this.extensions.values()))
  }
}

export class ServerHello extends HandshakeMessage {
  random: Uint8Array
  sessionId: Uint8Array
  extensions: ExtensionMap

  constructor(
    random: Uint8Array,
    sessionId: Uint8Array,
    extensions: ExtensionMap | ExtensionLike[]
  ) {
    super()
    this.random = random
    this.sessionId = sessionId
    if (Array.isArray(extensions)) {
      const map: ExtensionMap = new Map()
      for (const ext of extensions) {
        map.set(ext.TYPE_TAG, ext)
        map.lastSeenExtension = ext.TYPE_TAG
      }
      this.extensions = map
    } else {
      this.extensions = extensions
    }
  }

  get TYPE_TAG(): number {
    return HANDSHAKE_TYPE.SERVER_HELLO
  }

  static _read(buf: BufferReader): ServerHello {
    if (buf.readUint16() !== VERSION_TLS_1_2) {
      throw new TLSError(ALERT_DESCRIPTION.ILLEGAL_PARAMETER)
    }
    const random = buf.readBytes(32)
    const sessionId = buf.readVectorBytes8()
    if (buf.readUint16() !== TLS_AES_128_GCM_SHA256) {
      throw new TLSError(ALERT_DESCRIPTION.ILLEGAL_PARAMETER)
    }
    if (buf.readUint8() !== 0) {
      throw new TLSError(ALERT_DESCRIPTION.ILLEGAL_PARAMETER)
    }
    const extensions = this._readExtensions(HANDSHAKE_TYPE.SERVER_HELLO, buf)
    if (!extensions.has(EXTENSION_TYPE.SUPPORTED_VERSIONS)) {
      throw new TLSError(ALERT_DESCRIPTION.MISSING_EXTENSION)
    }
    const svExtSH = extensions.get(EXTENSION_TYPE.SUPPORTED_VERSIONS) as
      unknown as { selectedVersion: number }
    if (svExtSH.selectedVersion !== VERSION_TLS_1_3) {
      throw new TLSError(ALERT_DESCRIPTION.ILLEGAL_PARAMETER)
    }
    return new this(random, sessionId, extensions)
  }

  _write(buf: BufferWriter): void {
    buf.writeUint16(VERSION_TLS_1_2)
    buf.writeBytes(this.random)
    buf.writeVectorBytes8(this.sessionId)
    buf.writeUint16(TLS_AES_128_GCM_SHA256)
    buf.writeUint8(0)
    this._writeExtensions(buf, Array.from(this.extensions.values()))
  }
}

export class EncryptedExtensions extends HandshakeMessage {
  extensions: ExtensionMap

  constructor(extensions: ExtensionMap | ExtensionLike[]) {
    super()
    if (Array.isArray(extensions)) {
      const map: ExtensionMap = new Map()
      for (const ext of extensions) {
        map.set(ext.TYPE_TAG, ext)
      }
      this.extensions = map
    } else {
      this.extensions = extensions
    }
  }

  get TYPE_TAG(): number {
    return HANDSHAKE_TYPE.ENCRYPTED_EXTENSIONS
  }

  static _read(buf: BufferReader): EncryptedExtensions {
    const extensions = this._readExtensions(
      HANDSHAKE_TYPE.ENCRYPTED_EXTENSIONS,
      buf
    )
    return new this(extensions)
  }

  _write(buf: BufferWriter): void {
    this._writeExtensions(buf, Array.from(this.extensions.values()))
  }
}

export class Finished extends HandshakeMessage {
  verifyData: Uint8Array

  constructor(verifyData: Uint8Array) {
    super()
    this.verifyData = verifyData
  }

  get TYPE_TAG(): number {
    return HANDSHAKE_TYPE.FINISHED
  }

  static _read(buf: BufferReader): Finished {
    const verifyData = buf.readBytes(HASH_LENGTH)
    return new this(verifyData)
  }

  _write(buf: BufferWriter): void {
    buf.writeBytes(this.verifyData)
  }
}

export class NewSessionTicket extends HandshakeMessage {
  ticketLifetime: number
  ticketAgeAdd: number
  ticketNonce: Uint8Array
  ticket: Uint8Array
  extensions: ExtensionMap

  constructor(
    ticketLifetime: number,
    ticketAgeAdd: number,
    ticketNonce: Uint8Array,
    ticket: Uint8Array,
    extensions: ExtensionMap
  ) {
    super()
    this.ticketLifetime = ticketLifetime
    this.ticketAgeAdd = ticketAgeAdd
    this.ticketNonce = ticketNonce
    this.ticket = ticket
    this.extensions = extensions
  }

  get TYPE_TAG(): number {
    return HANDSHAKE_TYPE.NEW_SESSION_TICKET
  }

  static _read(buf: BufferReader): NewSessionTicket {
    const ticketLifetime = buf.readUint32()
    const ticketAgeAdd = buf.readUint32()
    const ticketNonce = buf.readVectorBytes8()
    const ticket = buf.readVectorBytes16()
    if (ticket.byteLength < 1) {
      throw new TLSError(ALERT_DESCRIPTION.DECODE_ERROR)
    }
    const extensions = this._readExtensions(
      HANDSHAKE_TYPE.NEW_SESSION_TICKET,
      buf
    )
    return new this(
      ticketLifetime,
      ticketAgeAdd,
      ticketNonce,
      ticket,
      extensions
    )
  }

  _write(buf: BufferWriter): void {
    buf.writeUint32(this.ticketLifetime)
    buf.writeUint32(this.ticketAgeAdd)
    buf.writeVectorBytes8(this.ticketNonce)
    buf.writeVectorBytes16(this.ticket)
    this._writeExtensions(buf, Array.from(this.extensions.values()))
  }
}
