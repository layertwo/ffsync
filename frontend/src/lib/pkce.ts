export async function generatePKCE(): Promise<{
  codeVerifier: string
  codeChallenge: string
}> {
  const array = new Uint8Array(32)
  crypto.getRandomValues(array)
  const codeVerifier = base64UrlEncode(array)

  const encoder = new TextEncoder()
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(codeVerifier))
  const codeChallenge = base64UrlEncode(new Uint8Array(digest))

  return { codeVerifier, codeChallenge }
}

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = ""
  for (const byte of bytes) {
    binary += String.fromCharCode(byte)
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
}
