/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { utf8ToBytes, BufferWriter } from "./utils"
import { ALERT_DESCRIPTION, TLSError } from "./alerts"

export const AEAD_SIZE_INFLATION = 16
export const KEY_LENGTH = 16
export const IV_LENGTH = 12
export const HASH_LENGTH = 32

// Helper to ensure Uint8Array has an ArrayBuffer (not SharedArrayBuffer) backing,
// which is required by WebCrypto APIs in strict TypeScript.
function toBuffer(bytes: Uint8Array): Uint8Array<ArrayBuffer> {
  return bytes as Uint8Array<ArrayBuffer>
}

export async function prepareKey(
  key: Uint8Array,
  mode: "encrypt" | "decrypt"
): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", toBuffer(key), { name: "AES-GCM" }, false, [mode])
}

export async function encrypt(
  key: CryptoKey,
  iv: Uint8Array,
  plaintext: Uint8Array,
  additionalData: Uint8Array
): Promise<Uint8Array> {
  const ciphertext = await crypto.subtle.encrypt(
    {
      additionalData: toBuffer(additionalData),
      iv: toBuffer(iv),
      name: "AES-GCM",
      tagLength: AEAD_SIZE_INFLATION * 8,
    },
    key,
    toBuffer(plaintext)
  )
  return new Uint8Array(ciphertext)
}

export async function decrypt(
  key: CryptoKey,
  iv: Uint8Array,
  ciphertext: Uint8Array,
  additionalData: Uint8Array
): Promise<Uint8Array> {
  try {
    const plaintext = await crypto.subtle.decrypt(
      {
        additionalData: toBuffer(additionalData),
        iv: toBuffer(iv),
        name: "AES-GCM",
        tagLength: AEAD_SIZE_INFLATION * 8,
      },
      key,
      toBuffer(ciphertext)
    )
    return new Uint8Array(plaintext)
  } catch {
    throw new TLSError(ALERT_DESCRIPTION.BAD_RECORD_MAC)
  }
}

export async function hash(message: Uint8Array): Promise<Uint8Array> {
  return new Uint8Array(
    await crypto.subtle.digest({ name: "SHA-256" }, toBuffer(message))
  )
}

export async function hmac(
  keyBytes: Uint8Array,
  message: Uint8Array
): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey(
    "raw",
    toBuffer(keyBytes),
    {
      hash: { name: "SHA-256" },
      name: "HMAC",
    },
    false,
    ["sign"]
  )
  const sig = await crypto.subtle.sign({ name: "HMAC" }, key, toBuffer(message))
  return new Uint8Array(sig)
}

export async function verifyHmac(
  keyBytes: Uint8Array,
  signature: Uint8Array,
  message: Uint8Array
): Promise<void> {
  const key = await crypto.subtle.importKey(
    "raw",
    toBuffer(keyBytes),
    {
      hash: { name: "SHA-256" },
      name: "HMAC",
    },
    false,
    ["verify"]
  )
  if (!(await crypto.subtle.verify({ name: "HMAC" }, key, toBuffer(signature), toBuffer(message)))) {
    throw new TLSError(ALERT_DESCRIPTION.DECRYPT_ERROR)
  }
}

export async function hkdfExtract(
  salt: Uint8Array,
  ikm: Uint8Array
): Promise<Uint8Array> {
  return await hmac(salt, ikm)
}

export async function hkdfExpand(
  prk: Uint8Array,
  info: Uint8Array,
  length: number
): Promise<Uint8Array> {
  const N = Math.ceil(length / HASH_LENGTH)
  if (N <= 0) {
    throw new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
  }
  if (N >= 255) {
    throw new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
  }
  const input = new BufferWriter()
  const output = new BufferWriter()
  let T: Uint8Array = new Uint8Array(0)
  for (let i = 1; i <= N; i++) {
    input.writeBytes(T)
    input.writeBytes(info)
    input.writeUint8(i)
    T = await hmac(prk, input.flush())
    output.writeBytes(T)
  }
  return output.slice(0, length)
}

export async function hkdfExpandLabel(
  secret: Uint8Array,
  label: string,
  context: Uint8Array,
  length: number
): Promise<Uint8Array> {
  const hkdfLabel = new BufferWriter()
  hkdfLabel.writeUint16(length)
  hkdfLabel.writeVectorBytes8(utf8ToBytes("tls13 " + label))
  hkdfLabel.writeVectorBytes8(context)
  return hkdfExpand(secret, hkdfLabel.flush(), length)
}

export async function getRandomBytes(size: number): Promise<Uint8Array<ArrayBuffer>> {
  const bytes = new Uint8Array(size) as Uint8Array<ArrayBuffer>
  crypto.getRandomValues(bytes)
  return bytes
}
