/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { ALERT_DESCRIPTION, TLSError } from "./alerts"
import { HANDSHAKE_TYPE } from "./messages"
import { HASH_LENGTH } from "./crypto"
import type { BufferReader, BufferWriter } from "./utils"

export const EXTENSION_TYPE = {
  PRE_SHARED_KEY: 41,
  SUPPORTED_VERSIONS: 43,
  PSK_KEY_EXCHANGE_MODES: 45,
} as const

export interface ExtensionLike {
  TYPE_TAG: number
  write(messageType: number, buf: BufferWriter): void
}

export class Extension {
  get TYPE_TAG(): number {
    throw new Error("not implemented")
  }

  static read(messageType: number, buf: BufferReader): ExtensionLike {
    const type = buf.readUint16()
    let ext: ExtensionLike = {
      TYPE_TAG: type,
      write() {
        throw new Error("not implemented")
      },
    }
    buf.readVector16((buf) => {
      switch (type) {
        case EXTENSION_TYPE.PRE_SHARED_KEY:
          ext = PreSharedKeyExtension._read(messageType, buf)
          break
        case EXTENSION_TYPE.SUPPORTED_VERSIONS:
          ext = SupportedVersionsExtension._read(messageType, buf)
          break
        case EXTENSION_TYPE.PSK_KEY_EXCHANGE_MODES:
          ext = PskKeyExchangeModesExtension._read(messageType, buf)
          break
        default:
          // Skip over unrecognised extensions.
          buf.incr(buf.length())
      }
      if (buf.hasMoreBytes()) {
        throw new TLSError(ALERT_DESCRIPTION.DECODE_ERROR)
      }
    })
    return ext
  }

  write(messageType: number, buf: BufferWriter): void {
    buf.writeUint16(this.TYPE_TAG)
    buf.writeVector16((buf) => {
      this._write(messageType, buf)
    })
  }

  static _read(_messageType: number, _buf: BufferReader): Extension {
    throw new Error("not implemented")
  }

  _write(_messageType: number, _buf: BufferWriter): void {
    throw new Error("not implemented")
  }
}

export class PreSharedKeyExtension extends Extension {
  identities: Uint8Array[] | null
  binders: Uint8Array[] | null
  selectedIdentity: number | null

  constructor(
    identities: Uint8Array[] | null,
    binders: Uint8Array[] | null,
    selectedIdentity: number | null
  ) {
    super()
    this.identities = identities
    this.binders = binders
    this.selectedIdentity = selectedIdentity
  }

  get TYPE_TAG(): number {
    return EXTENSION_TYPE.PRE_SHARED_KEY
  }

  static _read(messageType: number, buf: BufferReader): PreSharedKeyExtension {
    let identities: Uint8Array[] | null = null,
      binders: Uint8Array[] | null = null,
      selectedIdentity: number | null = null
    switch (messageType) {
      case HANDSHAKE_TYPE.CLIENT_HELLO:
        identities = []
        binders = []
        buf.readVector16((buf) => {
          const identity = buf.readVectorBytes16()
          buf.readBytes(4) // Skip over the ticket age.
          identities!.push(identity)
        })
        buf.readVector16((buf) => {
          const binder = buf.readVectorBytes8()
          if (binder.byteLength < HASH_LENGTH) {
            throw new TLSError(ALERT_DESCRIPTION.ILLEGAL_PARAMETER)
          }
          binders!.push(binder)
        })
        if (identities.length !== binders.length) {
          throw new TLSError(ALERT_DESCRIPTION.ILLEGAL_PARAMETER)
        }
        break
      case HANDSHAKE_TYPE.SERVER_HELLO:
        selectedIdentity = buf.readUint16()
        break
      default:
        throw new TLSError(ALERT_DESCRIPTION.ILLEGAL_PARAMETER)
    }
    return new this(identities, binders, selectedIdentity)
  }

  _write(messageType: number, buf: BufferWriter): void {
    switch (messageType) {
      case HANDSHAKE_TYPE.CLIENT_HELLO:
        buf.writeVector16((buf) => {
          this.identities!.forEach((pskId) => {
            buf.writeVectorBytes16(pskId)
            buf.writeUint32(0)
          })
        })
        buf.writeVector16((buf) => {
          this.binders!.forEach((pskBinder) => {
            buf.writeVectorBytes8(pskBinder)
          })
        })
        break
      case HANDSHAKE_TYPE.SERVER_HELLO:
        buf.writeUint16(this.selectedIdentity!)
        break
      default:
        throw new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
    }
  }
}

export class SupportedVersionsExtension extends Extension {
  versions: number[] | null
  selectedVersion: number | null

  constructor(versions: number[] | null, selectedVersion?: number | null) {
    super()
    this.versions = versions
    this.selectedVersion = selectedVersion ?? null
  }

  get TYPE_TAG(): number {
    return EXTENSION_TYPE.SUPPORTED_VERSIONS
  }

  static _read(
    messageType: number,
    buf: BufferReader
  ): SupportedVersionsExtension {
    let versions: number[] | null = null,
      selectedVersion: number | null = null
    switch (messageType) {
      case HANDSHAKE_TYPE.CLIENT_HELLO:
        versions = []
        buf.readVector8((buf) => {
          versions!.push(buf.readUint16())
        })
        break
      case HANDSHAKE_TYPE.SERVER_HELLO:
        selectedVersion = buf.readUint16()
        break
      default:
        throw new TLSError(ALERT_DESCRIPTION.ILLEGAL_PARAMETER)
    }
    return new this(versions, selectedVersion)
  }

  _write(messageType: number, buf: BufferWriter): void {
    switch (messageType) {
      case HANDSHAKE_TYPE.CLIENT_HELLO:
        buf.writeVector8((buf) => {
          this.versions!.forEach((version) => {
            buf.writeUint16(version)
          })
        })
        break
      case HANDSHAKE_TYPE.SERVER_HELLO:
        buf.writeUint16(this.selectedVersion!)
        break
      default:
        throw new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
    }
  }
}

export class PskKeyExchangeModesExtension extends Extension {
  modes: number[]

  constructor(modes: number[]) {
    super()
    this.modes = modes
  }

  get TYPE_TAG(): number {
    return EXTENSION_TYPE.PSK_KEY_EXCHANGE_MODES
  }

  static _read(
    messageType: number,
    buf: BufferReader
  ): PskKeyExchangeModesExtension {
    const modes: number[] = []
    switch (messageType) {
      case HANDSHAKE_TYPE.CLIENT_HELLO:
        buf.readVector8((buf) => {
          modes.push(buf.readUint8())
        })
        break
      default:
        throw new TLSError(ALERT_DESCRIPTION.ILLEGAL_PARAMETER)
    }
    return new this(modes)
  }

  _write(messageType: number, buf: BufferWriter): void {
    switch (messageType) {
      case HANDSHAKE_TYPE.CLIENT_HELLO:
        buf.writeVector8((buf) => {
          this.modes.forEach((mode) => {
            buf.writeUint8(mode)
          })
        })
        break
      default:
        throw new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
    }
  }
}
