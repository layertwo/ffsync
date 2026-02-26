import { CompactEncrypt, importJWK } from "jose"
import {
  hkdf,
  hexToBytes,
  toHex,
  buildHawkHeaderWithInfo,
} from "./fxa-crypto"
import { authFetch } from "./auth-client"

const SESSION_TOKEN_INFO = "identity.mozilla.com/picl/v1/sessionToken"
const KEY_FETCH_TOKEN_INFO = "identity.mozilla.com/picl/v1/keyFetchToken"
const ACCOUNT_KEYS_INFO = "identity.mozilla.com/picl/v1/account/keys"
const OLDSYNC_INFO = "identity.mozilla.com/picl/v1/oldsync"

interface KeyBundle {
  kA: string
  wrapKB: string
}

interface ScopedKeyData {
  identifier: string
  keyRotationSecret: string
  keyRotationTimestamp: number
}

interface ScopedKeyJWK {
  kid: string
  k: string
  kty: string
}

export interface DeriveAndEncryptParams {
  authServerUrl: string
  keyFetchTokenHex: string
  unwrapBKeyHex: string
  sessionTokenHex: string
  keysJwkB64: string
  scope: string
}

export async function fetchAccountKeys(
  authServerUrl: string,
  keyFetchTokenHex: string
): Promise<string> {
  const url = `${authServerUrl}/v1/account/keys`
  const authorization = await buildHawkHeaderWithInfo(
    keyFetchTokenHex,
    "GET",
    url,
    KEY_FETCH_TOKEN_INFO
  )
  const response = await authFetch<{ bundle: string }>(url, {
    method: "GET",
    headers: { Authorization: authorization },
  })
  return response.bundle
}

export async function decryptKeyBundle(
  keyFetchTokenHex: string,
  bundleHex: string
): Promise<KeyBundle> {
  const tokenBytes = hexToBytes(keyFetchTokenHex)

  // Derive the bundle key from keyFetchToken
  const derived = await hkdf(tokenBytes.buffer, KEY_FETCH_TOKEN_INFO, 96)
  const bundleKey = derived.slice(64, 96)

  // Derive hmacKey and xorKey from bundleKey
  const keys = await hkdf(bundleKey, ACCOUNT_KEYS_INFO, 96)
  const hmacKey = keys.slice(0, 32)
  const xorKey = new Uint8Array(keys.slice(32, 96))

  // Parse the bundle (96 bytes = 64 ciphertext + 32 MAC)
  const bundleBytes = hexToBytes(bundleHex)
  const ciphertext = bundleBytes.slice(0, 64)
  const mac = bundleBytes.slice(64, 96)

  // Verify HMAC-SHA256
  const hmacCryptoKey = await crypto.subtle.importKey(
    "raw",
    hmacKey,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  )
  const valid = await crypto.subtle.verify(
    "HMAC",
    hmacCryptoKey,
    mac,
    ciphertext
  )
  if (!valid) {
    throw new Error("Key bundle HMAC verification failed")
  }

  // XOR ciphertext with xorKey to get kA + wrapKB
  const plaintext = new Uint8Array(64)
  for (let i = 0; i < 64; i++) {
    plaintext[i] = ciphertext[i] ^ xorKey[i]
  }

  return {
    kA: toHex(plaintext.slice(0, 32).buffer),
    wrapKB: toHex(plaintext.slice(32, 64).buffer),
  }
}

export function deriveKB(wrapKBHex: string, unwrapBKeyHex: string): string {
  const wrapKB = hexToBytes(wrapKBHex)
  const unwrapBKey = hexToBytes(unwrapBKeyHex)
  const kB = new Uint8Array(32)
  for (let i = 0; i < 32; i++) {
    kB[i] = wrapKB[i] ^ unwrapBKey[i]
  }
  return toHex(kB.buffer)
}

export async function fetchScopedKeyData(
  authServerUrl: string,
  sessionTokenHex: string,
  clientId: string,
  scope: string
): Promise<Record<string, ScopedKeyData>> {
  const url = `${authServerUrl}/v1/account/scoped-key-data`
  const authorization = await buildHawkHeaderWithInfo(
    sessionTokenHex,
    "POST",
    url,
    SESSION_TOKEN_INFO
  )
  return authFetch<Record<string, ScopedKeyData>>(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: authorization,
    },
    body: JSON.stringify({ client_id: clientId, scope }),
  })
}

function toBase64url(buffer: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buffer)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "")
}

export async function deriveScopedSyncKey(
  kBHex: string,
  keyRotationTimestamp: number
): Promise<ScopedKeyJWK> {
  const kB = hexToBytes(kBHex)

  // Derive sync key material (legacy oldsync derivation)
  const syncKeyMaterial = await hkdf(kB.buffer, OLDSYNC_INFO, 64)

  // Compute fingerprint: SHA-256(kB)[0:16]
  const kBHash = await crypto.subtle.digest("SHA-256", kB)
  const fingerprint = toBase64url(kBHash.slice(0, 16))

  return {
    kid: `${keyRotationTimestamp}-${fingerprint}`,
    k: toBase64url(syncKeyMaterial),
    kty: "oct",
  }
}

export async function encryptKeysJWE(
  scopedKeysBundle: Record<string, ScopedKeyJWK>,
  keysJwkB64: string
): Promise<string> {
  // Decode the base64url-encoded JWK from Firefox
  const jwkJson = new TextDecoder().decode(
    Uint8Array.from(atob(keysJwkB64.replace(/-/g, "+").replace(/_/g, "/")), (c) =>
      c.charCodeAt(0)
    )
  )
  const jwk = JSON.parse(jwkJson)

  // Import the EC P-256 public key
  const publicKey = await importJWK(jwk, "ECDH-ES")

  // Encrypt the scoped keys bundle as a JWE
  const payload = new TextEncoder().encode(JSON.stringify(scopedKeysBundle))
  const jwe = await new CompactEncrypt(payload)
    .setProtectedHeader({ alg: "ECDH-ES", enc: "A256GCM", kid: jwk.kid })
    .encrypt(publicKey)

  return jwe
}

export async function deriveAndEncryptSyncKeys(
  params: DeriveAndEncryptParams
): Promise<string> {
  const {
    authServerUrl,
    keyFetchTokenHex,
    unwrapBKeyHex,
    sessionTokenHex,
    keysJwkB64,
    scope,
  } = params

  // 1. Fetch the encrypted key bundle from the server
  const bundleHex = await fetchAccountKeys(authServerUrl, keyFetchTokenHex)

  // 2. Decrypt the key bundle
  const { wrapKB } = await decryptKeyBundle(keyFetchTokenHex, bundleHex)

  // 3. Derive kB by XOR-ing wrapKB with unwrapBKey
  const kBHex = deriveKB(wrapKB, unwrapBKeyHex)

  // 4. Fetch scoped key metadata
  const scopedKeyData = await fetchScopedKeyData(
    authServerUrl,
    sessionTokenHex,
    scope.split(" ")[0],
    scope
  )

  // 5. Derive scoped sync key
  const syncScope = "https://identity.mozilla.com/apps/oldsync"
  const metadata = scopedKeyData[syncScope]
  if (!metadata) {
    throw new Error(`No scoped key data returned for ${syncScope}`)
  }

  const scopedKey = await deriveScopedSyncKey(kBHex, metadata.keyRotationTimestamp)

  // 6. Encrypt as JWE for Firefox
  const keysBundle: Record<string, ScopedKeyJWK> = {
    [syncScope]: scopedKey,
  }
  return encryptKeysJWE(keysBundle, keysJwkB64)
}
