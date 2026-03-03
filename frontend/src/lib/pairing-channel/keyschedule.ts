/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { BufferWriter, EMPTY, zeros } from "./utils"
import { ALERT_DESCRIPTION, TLSError } from "./alerts"
import {
  hkdfExtract,
  hkdfExpandLabel,
  HASH_LENGTH,
  hash,
  hmac,
  verifyHmac,
} from "./crypto"

const STAGE_UNINITIALIZED = 0
const STAGE_EARLY_SECRET = 1
const STAGE_HANDSHAKE_SECRET = 2
const STAGE_MASTER_SECRET = 3

export class KeySchedule {
  stage: number
  transcript: BufferWriter
  secret: Uint8Array | null
  extBinderKey: Uint8Array | null
  clientHandshakeTrafficSecret: Uint8Array | null
  serverHandshakeTrafficSecret: Uint8Array | null
  clientApplicationTrafficSecret: Uint8Array | null
  serverApplicationTrafficSecret: Uint8Array | null

  constructor() {
    this.stage = STAGE_UNINITIALIZED
    this.transcript = new BufferWriter()
    this.secret = null
    this.extBinderKey = null
    this.clientHandshakeTrafficSecret = null
    this.serverHandshakeTrafficSecret = null
    this.clientApplicationTrafficSecret = null
    this.serverApplicationTrafficSecret = null
  }

  async addPSK(psk: Uint8Array | null): Promise<void> {
    if (psk === null) {
      psk = zeros(HASH_LENGTH)
    }
    if (this.stage !== STAGE_UNINITIALIZED) {
      throw new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
    }
    this.stage = STAGE_EARLY_SECRET
    this.secret = await hkdfExtract(zeros(HASH_LENGTH), psk)
    this.extBinderKey = await this.deriveSecret("ext binder", EMPTY)
    this.secret = await this.deriveSecret("derived", EMPTY)
  }

  async addECDHE(ecdhe: Uint8Array | null): Promise<void> {
    if (ecdhe === null) {
      ecdhe = zeros(HASH_LENGTH)
    }
    if (this.stage !== STAGE_EARLY_SECRET) {
      throw new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
    }
    this.stage = STAGE_HANDSHAKE_SECRET
    this.extBinderKey = null
    this.secret = await hkdfExtract(this.secret!, ecdhe)
    this.clientHandshakeTrafficSecret = await this.deriveSecret("c hs traffic")
    this.serverHandshakeTrafficSecret = await this.deriveSecret("s hs traffic")
    this.secret = await this.deriveSecret("derived", EMPTY)
  }

  async finalize(): Promise<void> {
    if (this.stage !== STAGE_HANDSHAKE_SECRET) {
      throw new TLSError(ALERT_DESCRIPTION.INTERNAL_ERROR)
    }
    this.stage = STAGE_MASTER_SECRET
    this.clientHandshakeTrafficSecret = null
    this.serverHandshakeTrafficSecret = null
    this.secret = await hkdfExtract(this.secret!, zeros(HASH_LENGTH))
    this.clientApplicationTrafficSecret = await this.deriveSecret("c ap traffic")
    this.serverApplicationTrafficSecret = await this.deriveSecret("s ap traffic")
    this.secret = null
  }

  addToTranscript(bytes: Uint8Array): void {
    this.transcript.writeBytes(bytes)
  }

  getTranscript(): Uint8Array {
    return this.transcript.slice()
  }

  async deriveSecret(
    label: string,
    transcript?: Uint8Array
  ): Promise<Uint8Array> {
    transcript = transcript || this.getTranscript()
    return await hkdfExpandLabel(
      this.secret!,
      label,
      await hash(transcript),
      HASH_LENGTH
    )
  }

  async calculateFinishedMAC(
    baseKey: Uint8Array,
    transcript?: Uint8Array
  ): Promise<Uint8Array> {
    transcript = transcript || this.getTranscript()
    const finishedKey = await hkdfExpandLabel(
      baseKey,
      "finished",
      EMPTY,
      HASH_LENGTH
    )
    return await hmac(finishedKey, await hash(transcript))
  }

  async verifyFinishedMAC(
    baseKey: Uint8Array,
    mac: Uint8Array,
    transcript?: Uint8Array
  ): Promise<void> {
    transcript = transcript || this.getTranscript()
    const finishedKey = await hkdfExpandLabel(
      baseKey,
      "finished",
      EMPTY,
      HASH_LENGTH
    )
    await verifyHmac(finishedKey, mac, await hash(transcript))
  }
}
