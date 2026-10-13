// Key material held only in memory for the document's lifetime, never persisted.
let custody: { keyFetchToken: string; unwrapBKey: string } | null = null

export function setPairingCustody(c: {
  keyFetchToken: string
  unwrapBKey: string
}): void {
  custody = c
}

export function getPairingCustody(): {
  keyFetchToken: string
  unwrapBKey: string
} | null {
  return custody
}

export function clearPairingCustody(): void {
  custody = null
}
