export function channelKeyToBase64url(key: Uint8Array): string {
  let binary = ""
  for (const byte of key) {
    binary += String.fromCharCode(byte)
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
}

export function base64urlToChannelKey(b64: string): Uint8Array {
  const str = atob(b64.replace(/-/g, "+").replace(/_/g, "/"))
  const bytes = new Uint8Array(str.length)
  for (let i = 0; i < str.length; i++) {
    bytes[i] = str.charCodeAt(i)
  }
  return bytes
}

export function buildPairUrl(
  contentUrl: string,
  channelId: string,
  channelKey: Uint8Array
): string {
  const keyB64 = channelKeyToBase64url(channelKey)
  return `${contentUrl}/pair/supp#channel_id=${channelId}&channel_key=${keyB64}`
}

export function parsePairFragment(
  hash: string
): { channelId: string; channelKey: Uint8Array } | null {
  const fragment = hash.startsWith("#") ? hash.slice(1) : hash
  const params = new URLSearchParams(fragment)
  const channelId = params.get("channel_id")
  const channelKeyB64 = params.get("channel_key")
  if (!channelId || !channelKeyB64) {
    return null
  }
  try {
    const channelKey = base64urlToChannelKey(channelKeyB64)
    return { channelId, channelKey }
  } catch {
    return null
  }
}
