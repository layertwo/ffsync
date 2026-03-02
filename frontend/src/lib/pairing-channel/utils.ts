/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { ALERT_DESCRIPTION, TLSError } from "./alerts"

//
// Various low-level utility functions.
//
// These are mostly conveniences for working with Uint8Arrays as
// the primitive "bytes" type.
//

const UTF8_ENCODER = new TextEncoder()
const UTF8_DECODER = new TextDecoder()

export function noop(): void {}

export function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    throw new Error("assert failed: " + msg)
  }
}

export function assertIsBytes(
  value: unknown,
  msg = "value must be a Uint8Array"
): Uint8Array {
  // Using `value instanceof Uint8Array` seems to fail in Firefox chrome code
  // for inscrutable reasons, so we do a less direct check.
  assert(ArrayBuffer.isView(value), msg)
  assert((value as unknown as { BYTES_PER_ELEMENT: number }).BYTES_PER_ELEMENT === 1, msg)
  return value as Uint8Array
}

export const EMPTY: Uint8Array = new Uint8Array(0)

export function zeros(n: number): Uint8Array {
  return new Uint8Array(n)
}

export function arrayToBytes(value: number[]): Uint8Array {
  return new Uint8Array(value)
}

export function bytesToHex(bytes: Uint8Array): string {
  return Array.prototype.map
    .call(bytes, (byte: number) => {
      let s = byte.toString(16)
      if (s.length === 1) {
        s = "0" + s
      }
      return s
    })
    .join("")
}

export function hexToBytes(hexstr: string): Uint8Array {
  assert(hexstr.length % 2 === 0, "hexstr.length must be even")
  const pairs: string[] = []
  for (let i = 0; i < hexstr.length; i += 2) {
    pairs.push(hexstr[i] + hexstr[i + 1])
  }
  return new Uint8Array(pairs.map((s) => parseInt(s, 16)))
}

export function bytesToUtf8(bytes: Uint8Array): string {
  return UTF8_DECODER.decode(bytes)
}

export function utf8ToBytes(str: string): Uint8Array {
  return UTF8_ENCODER.encode(str)
}

export function bytesToBase64url(bytes: Uint8Array): string {
  const charCodes = String.fromCharCode.apply(String, bytes as unknown as number[])
  return btoa(charCodes).replace(/\+/g, "-").replace(/\//g, "_")
}

export function base64urlToBytes(str: string): Uint8Array {
  str = atob(str.replace(/-/g, "+").replace(/_/g, "/"))
  const bytes = new Uint8Array(str.length)
  for (let i = 0; i < str.length; i++) {
    bytes[i] = str.charCodeAt(i)
  }
  return bytes
}

export function bytesAreEqual(v1: Uint8Array, v2: Uint8Array): boolean {
  assertIsBytes(v1)
  assertIsBytes(v2)
  if (v1.length !== v2.length) {
    return false
  }
  for (let i = 0; i < v1.length; i++) {
    if (v1[i] !== v2[i]) {
      return false
    }
  }
  return true
}

// The `BufferReader` and `BufferWriter` classes are helpers for dealing with the
// binary struct format that's used for various TLS message.

class BufferWithPointer {
  _buffer: Uint8Array
  _dataview: DataView
  _pos: number

  constructor(buf: Uint8Array) {
    this._buffer = buf
    this._dataview = new DataView(buf.buffer, buf.byteOffset, buf.byteLength)
    this._pos = 0
  }

  length(): number {
    return this._buffer.byteLength
  }

  tell(): number {
    return this._pos
  }

  seek(pos: number): void {
    if (pos < 0) {
      throw new TLSError(ALERT_DESCRIPTION.DECODE_ERROR)
    }
    if (pos > this.length()) {
      throw new TLSError(ALERT_DESCRIPTION.DECODE_ERROR)
    }
    this._pos = pos
  }

  incr(offset: number): void {
    this.seek(this._pos + offset)
  }
}

export class BufferReader extends BufferWithPointer {
  hasMoreBytes(): boolean {
    return this.tell() < this.length()
  }

  readBytes(length: number): Uint8Array {
    const start = this._buffer.byteOffset + this.tell()
    this.incr(length)
    return new Uint8Array(this._buffer.buffer, start, length)
  }

  _rangeErrorToAlert<T>(cb: (self: this) => T): T {
    try {
      return cb(this)
    } catch (err) {
      if (err instanceof RangeError) {
        throw new TLSError(ALERT_DESCRIPTION.DECODE_ERROR)
      }
      throw err
    }
  }

  readUint8(): number {
    return this._rangeErrorToAlert(() => {
      const n = this._dataview.getUint8(this._pos)
      this.incr(1)
      return n
    })
  }

  readUint16(): number {
    return this._rangeErrorToAlert(() => {
      const n = this._dataview.getUint16(this._pos)
      this.incr(2)
      return n
    })
  }

  readUint24(): number {
    return this._rangeErrorToAlert(() => {
      let n = this._dataview.getUint16(this._pos)
      n = (n << 8) | this._dataview.getUint8(this._pos + 2)
      this.incr(3)
      return n
    })
  }

  readUint32(): number {
    return this._rangeErrorToAlert(() => {
      const n = this._dataview.getUint32(this._pos)
      this.incr(4)
      return n
    })
  }

  _readVector(length: number, cb: (buf: BufferReader, n: number) => void): void {
    const contentsBuf = new BufferReader(this.readBytes(length))
    const expectedEnd = this.tell()
    let n = 0
    while (contentsBuf.hasMoreBytes()) {
      const prevPos = contentsBuf.tell()
      cb(contentsBuf, n)
      if (contentsBuf.tell() <= prevPos) {
        throw new TLSError(ALERT_DESCRIPTION.DECODE_ERROR)
      }
      n += 1
    }
    if (this.tell() !== expectedEnd) {
      throw new TLSError(ALERT_DESCRIPTION.DECODE_ERROR)
    }
  }

  readVector8(cb: (buf: BufferReader, n: number) => void): void {
    const length = this.readUint8()
    return this._readVector(length, cb)
  }

  readVector16(cb: (buf: BufferReader, n: number) => void): void {
    const length = this.readUint16()
    return this._readVector(length, cb)
  }

  readVector24(cb: (buf: BufferReader, n: number) => void): void {
    const length = this.readUint24()
    return this._readVector(length, cb)
  }

  readVectorBytes8(): Uint8Array {
    return this.readBytes(this.readUint8())
  }

  readVectorBytes16(): Uint8Array {
    return this.readBytes(this.readUint16())
  }

  readVectorBytes24(): Uint8Array {
    return this.readBytes(this.readUint24())
  }
}

export class BufferWriter extends BufferWithPointer {
  constructor(size = 1024) {
    super(new Uint8Array(size))
  }

  _maybeGrow(n: number): void {
    const curSize = this._buffer.byteLength
    const newPos = this._pos + n
    const shortfall = newPos - curSize
    if (shortfall > 0) {
      const incr = Math.min(curSize, 4 * 1024)
      const newbuf = new Uint8Array(curSize + Math.ceil(shortfall / incr) * incr)
      newbuf.set(this._buffer, 0)
      this._buffer = newbuf
      this._dataview = new DataView(
        newbuf.buffer,
        newbuf.byteOffset,
        newbuf.byteLength
      )
    }
  }

  slice(start = 0, end = this.tell()): Uint8Array {
    if (end < 0) {
      end = this.tell() + end
    }
    if (start < 0) {
      throw new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
    }
    if (end < 0) {
      throw new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
    }
    if (end > this.length()) {
      throw new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
    }
    return this._buffer.slice(start, end)
  }

  flush(): Uint8Array {
    const slice = this.slice()
    this.seek(0)
    return slice
  }

  writeBytes(data: Uint8Array): void {
    this._maybeGrow(data.byteLength)
    this._buffer.set(data, this.tell())
    this.incr(data.byteLength)
  }

  writeUint8(n: number): void {
    this._maybeGrow(1)
    this._dataview.setUint8(this._pos, n)
    this.incr(1)
  }

  writeUint16(n: number): void {
    this._maybeGrow(2)
    this._dataview.setUint16(this._pos, n)
    this.incr(2)
  }

  writeUint24(n: number): void {
    this._maybeGrow(3)
    this._dataview.setUint16(this._pos, n >> 8)
    this._dataview.setUint8(this._pos + 2, n & 0xff)
    this.incr(3)
  }

  writeUint32(n: number): void {
    this._maybeGrow(4)
    this._dataview.setUint32(this._pos, n)
    this.incr(4)
  }

  _writeVector(
    maxLength: number,
    writeLength: (len: number) => void,
    cb: (buf: BufferWriter) => void
  ): number {
    const lengthPos = this.tell()
    writeLength(0)
    const bodyPos = this.tell()
    cb(this)
    const length = this.tell() - bodyPos
    if (length >= maxLength) {
      throw new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
    }
    this.seek(lengthPos)
    writeLength(length)
    this.incr(length)
    return length
  }

  writeVector8(cb: (buf: BufferWriter) => void): number {
    return this._writeVector(
      Math.pow(2, 8),
      (len) => this.writeUint8(len),
      cb
    )
  }

  writeVector16(cb: (buf: BufferWriter) => void): number {
    return this._writeVector(
      Math.pow(2, 16),
      (len) => this.writeUint16(len),
      cb
    )
  }

  writeVector24(cb: (buf: BufferWriter) => void): number {
    return this._writeVector(
      Math.pow(2, 24),
      (len) => this.writeUint24(len),
      cb
    )
  }

  writeVectorBytes8(bytes: Uint8Array): number {
    return this.writeVector8((buf) => {
      buf.writeBytes(bytes)
    })
  }

  writeVectorBytes16(bytes: Uint8Array): number {
    return this.writeVector16((buf) => {
      buf.writeBytes(bytes)
    })
  }

  writeVectorBytes24(bytes: Uint8Array): number {
    return this.writeVector24((buf) => {
      buf.writeBytes(bytes)
    })
  }
}
