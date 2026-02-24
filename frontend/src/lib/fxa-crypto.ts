const NAMESPACE = "identity.mozilla.com/picl/v1/"

function encode(str: string): Uint8Array<ArrayBuffer> {
  return new TextEncoder().encode(str) as Uint8Array<ArrayBuffer>
}

export function toHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
}

async function hkdf(
  ikm: ArrayBuffer,
  info: string,
  length: number = 32
): Promise<ArrayBuffer> {
  const key = await crypto.subtle.importKey("raw", ikm, "HKDF", false, [
    "deriveBits",
  ])
  return crypto.subtle.deriveBits(
    {
      name: "HKDF",
      hash: "SHA-256",
      salt: new ArrayBuffer(0),
      info: encode(info),
    },
    key,
    length * 8
  )
}

function hexToBytes(hex: string): Uint8Array<ArrayBuffer> {
  const bytes = new Uint8Array(hex.length / 2) as Uint8Array<ArrayBuffer>
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substring(i, i + 2), 16)
  }
  return bytes
}

export async function deriveSessionTokenId(sessionTokenHex: string): Promise<string> {
  const tokenBytes = hexToBytes(sessionTokenHex)
  const derived = await hkdf(tokenBytes.buffer, "identity.mozilla.com/picl/v1/sessionToken", 96)
  return toHex(derived.slice(0, 32))
}

export async function stretchPassword(
  email: string,
  password: string
): Promise<{ authPW: string; unwrapBKey: string }> {
  const salt = encode(`${NAMESPACE}quickStretch:${email}`)
  const passwordBytes = encode(password)

  const baseKey = await crypto.subtle.importKey(
    "raw",
    passwordBytes,
    "PBKDF2",
    false,
    ["deriveBits"]
  )
  const quickStretched = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt, iterations: 1000, hash: "SHA-256" },
    baseKey,
    256
  )

  const authPW = await hkdf(quickStretched, `${NAMESPACE}authPW`)
  const unwrapBKey = await hkdf(quickStretched, `${NAMESPACE}unwrapBkey`)

  return { authPW: toHex(authPW), unwrapBKey: toHex(unwrapBKey) }
}
