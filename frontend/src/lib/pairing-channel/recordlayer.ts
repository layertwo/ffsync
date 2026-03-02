/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { VERSION_TLS_1_2, VERSION_TLS_1_0 } from "./constants"
import { BufferReader, BufferWriter, EMPTY } from "./utils"
import { ALERT_DESCRIPTION, TLSError } from "./alerts"
import {
  encrypt,
  decrypt,
  prepareKey,
  hkdfExpandLabel,
  AEAD_SIZE_INFLATION,
  IV_LENGTH,
  KEY_LENGTH,
} from "./crypto"

export const RECORD_TYPE = {
  CHANGE_CIPHER_SPEC: 20,
  ALERT: 21,
  HANDSHAKE: 22,
  APPLICATION_DATA: 23,
} as const

const MAX_SEQUENCE_NUMBER = Math.pow(2, 24)
const MAX_RECORD_SIZE = Math.pow(2, 14)
const MAX_ENCRYPTED_RECORD_SIZE = MAX_RECORD_SIZE + 256
const RECORD_HEADER_SIZE = 5

export class CipherState {
  key: CryptoKey
  iv: Uint8Array
  seqnum: number

  constructor(key: CryptoKey, iv: Uint8Array) {
    this.key = key
    this.iv = iv
    this.seqnum = 0
  }

  static async create(
    baseKey: Uint8Array,
    mode: "encrypt" | "decrypt"
  ): Promise<CipherState> {
    const key = await prepareKey(
      await hkdfExpandLabel(baseKey, "key", EMPTY, KEY_LENGTH),
      mode
    )
    const iv = await hkdfExpandLabel(baseKey, "iv", EMPTY, IV_LENGTH)
    return new this(key, iv) as CipherState
  }

  nonce(): Uint8Array {
    const nonce = this.iv.slice()
    const dv = new DataView(nonce.buffer, nonce.byteLength - 4, 4)
    dv.setUint32(0, dv.getUint32(0) ^ this.seqnum)
    this.seqnum += 1
    if (this.seqnum > MAX_SEQUENCE_NUMBER) {
      throw new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
    }
    return nonce
  }
}

export class EncryptionState extends CipherState {
  static async create(key: Uint8Array): Promise<EncryptionState> {
    const cryptoKey = await prepareKey(
      await hkdfExpandLabel(key, "key", EMPTY, KEY_LENGTH),
      "encrypt"
    )
    const iv = await hkdfExpandLabel(key, "iv", EMPTY, IV_LENGTH)
    const state = new EncryptionState(cryptoKey, iv)
    return state
  }

  async encrypt(
    plaintext: Uint8Array,
    additionalData: Uint8Array
  ): Promise<Uint8Array> {
    return await encrypt(this.key, this.nonce(), plaintext, additionalData)
  }
}

export class DecryptionState extends CipherState {
  static async create(key: Uint8Array): Promise<DecryptionState> {
    const cryptoKey = await prepareKey(
      await hkdfExpandLabel(key, "key", EMPTY, KEY_LENGTH),
      "decrypt"
    )
    const iv = await hkdfExpandLabel(key, "iv", EMPTY, IV_LENGTH)
    const state = new DecryptionState(cryptoKey, iv)
    return state
  }

  async decrypt(
    ciphertext: Uint8Array,
    additionalData: Uint8Array
  ): Promise<Uint8Array> {
    return await decrypt(this.key, this.nonce(), ciphertext, additionalData)
  }
}

export class RecordLayer {
  sendCallback: (data: Uint8Array) => void | Promise<void>
  _sendEncryptState: EncryptionState | null
  _sendError: Error | null
  _recvDecryptState: DecryptionState | null
  _recvError: Error | null
  _pendingRecordType: number
  _pendingRecordBuf: BufferWriter | null

  constructor(sendCallback: (data: Uint8Array) => void | Promise<void>) {
    this.sendCallback = sendCallback
    this._sendEncryptState = null
    this._sendError = null
    this._recvDecryptState = null
    this._recvError = null
    this._pendingRecordType = 0
    this._pendingRecordBuf = null
  }

  async setSendKey(key: Uint8Array): Promise<void> {
    await this.flush()
    this._sendEncryptState = await EncryptionState.create(key)
  }

  async setRecvKey(key: Uint8Array): Promise<void> {
    this._recvDecryptState = await DecryptionState.create(key)
  }

  async setSendError(err: Error): Promise<void> {
    this._sendError = err
  }

  async setRecvError(err: Error): Promise<void> {
    this._recvError = err
  }

  async send(type: number, data: Uint8Array): Promise<void> {
    if (this._sendError !== null) {
      throw this._sendError
    }
    if (data.byteLength > MAX_RECORD_SIZE) {
      throw new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
    }
    if (this._pendingRecordType && this._pendingRecordType !== type) {
      await this.flush()
    }
    if (this._pendingRecordBuf !== null) {
      if (this._pendingRecordBuf.tell() + data.byteLength > MAX_RECORD_SIZE) {
        await this.flush()
      }
    }
    if (this._pendingRecordBuf === null) {
      this._pendingRecordType = type
      this._pendingRecordBuf = new BufferWriter()
      this._pendingRecordBuf.incr(RECORD_HEADER_SIZE)
    }
    this._pendingRecordBuf.writeBytes(data)
  }

  async flush(): Promise<void> {
    const buf = this._pendingRecordBuf
    let type = this._pendingRecordType
    if (!type) {
      if (buf !== null) {
        throw new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
      }
      return
    }
    if (this._sendError !== null) {
      throw this._sendError
    }
    let inflation = 0,
      innerPlaintext: Uint8Array | null = null
    if (this._sendEncryptState !== null) {
      buf!.writeUint8(type)
      innerPlaintext = buf!.slice(RECORD_HEADER_SIZE)
      inflation = AEAD_SIZE_INFLATION
      type = RECORD_TYPE.APPLICATION_DATA
    }
    const length = buf!.tell() - RECORD_HEADER_SIZE + inflation
    buf!.seek(0)
    buf!.writeUint8(type)
    buf!.writeUint16(VERSION_TLS_1_2)
    buf!.writeUint16(length)
    if (this._sendEncryptState !== null) {
      const additionalData = buf!.slice(0, RECORD_HEADER_SIZE)
      const ciphertext = await this._sendEncryptState.encrypt(
        innerPlaintext!,
        additionalData
      )
      buf!.writeBytes(ciphertext)
    } else {
      buf!.incr(length)
    }
    this._pendingRecordBuf = null
    this._pendingRecordType = 0
    await this.sendCallback(buf!.flush())
  }

  async recv(data: Uint8Array): Promise<[number, Uint8Array]> {
    if (this._recvError !== null) {
      throw this._recvError
    }
    const buf = new BufferReader(data)
    let type = buf.readUint8()
    const version = buf.readUint16()
    if (version !== VERSION_TLS_1_2) {
      if (this._recvDecryptState !== null || version !== VERSION_TLS_1_0) {
        throw new TLSError(ALERT_DESCRIPTION.DECODE_ERROR)
      }
    }
    const length = buf.readUint16()
    let result: [number, Uint8Array]
    if (
      this._recvDecryptState === null ||
      type === RECORD_TYPE.CHANGE_CIPHER_SPEC
    ) {
      result = await this._readPlaintextRecord(type, length, buf)
    } else {
      result = await this._readEncryptedRecord(type, length, buf)
    }
    if (buf.hasMoreBytes()) {
      throw new TLSError(ALERT_DESCRIPTION.DECODE_ERROR)
    }
    return result
  }

  async _readPlaintextRecord(
    type: number,
    length: number,
    buf: BufferReader
  ): Promise<[number, Uint8Array]> {
    if (length > MAX_RECORD_SIZE) {
      throw new TLSError(ALERT_DESCRIPTION.RECORD_OVERFLOW)
    }
    return [type, buf.readBytes(length)]
  }

  async _readEncryptedRecord(
    type: number,
    length: number,
    buf: BufferReader
  ): Promise<[number, Uint8Array]> {
    if (length > MAX_ENCRYPTED_RECORD_SIZE) {
      throw new TLSError(ALERT_DESCRIPTION.RECORD_OVERFLOW)
    }
    if (type !== RECORD_TYPE.APPLICATION_DATA) {
      throw new TLSError(ALERT_DESCRIPTION.DECODE_ERROR)
    }
    buf.incr(-RECORD_HEADER_SIZE)
    const additionalData = buf.readBytes(RECORD_HEADER_SIZE)
    const ciphertext = buf.readBytes(length)
    const paddedPlaintext = await this._recvDecryptState!.decrypt(
      ciphertext,
      additionalData
    )
    let i: number
    for (i = paddedPlaintext.byteLength - 1; i >= 0; i--) {
      if (paddedPlaintext[i] !== 0) {
        break
      }
    }
    if (i < 0) {
      throw new TLSError(ALERT_DESCRIPTION.UNEXPECTED_MESSAGE)
    }
    type = paddedPlaintext[i]
    if (type === RECORD_TYPE.CHANGE_CIPHER_SPEC) {
      throw new TLSError(ALERT_DESCRIPTION.DECODE_ERROR)
    }
    return [type, paddedPlaintext.slice(0, i)]
  }
}
