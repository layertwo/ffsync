import type { BrowserCompatibility } from "./types"

export function checkBrowserCompatibility(): BrowserCompatibility {
  const hasCrypto =
    typeof crypto !== "undefined" &&
    typeof crypto.subtle !== "undefined" &&
    typeof crypto.getRandomValues === "function"

  const hasFetch = typeof fetch === "function"

  let hasSessionStorage = false
  try {
    const testKey = "__ffsync_test__"
    sessionStorage.setItem(testKey, "1")
    sessionStorage.removeItem(testKey)
    hasSessionStorage = true
  } catch {
    hasSessionStorage = false
  }

  return {
    crypto: hasCrypto,
    fetch: hasFetch,
    sessionStorage: hasSessionStorage,
    allSupported: hasCrypto && hasFetch && hasSessionStorage,
  }
}

export function getMissingFeatures(
  compat: BrowserCompatibility
): string[] {
  const missing: string[] = []
  if (!compat.crypto) missing.push("Web Crypto API (required for secure PKCE authentication)")
  if (!compat.fetch) missing.push("Fetch API (required for network requests)")
  if (!compat.sessionStorage) missing.push("sessionStorage (required for session management)")
  return missing
}
