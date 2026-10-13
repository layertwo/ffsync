import { afterEach, describe, expect, it, vi } from "vitest"

import { sendToFirefox } from "@/lib/webchannel"

function captureDispatched(): { details: unknown[]; stop: () => void } {
  const details: unknown[] = []
  const handler = (event: Event) => details.push((event as CustomEvent).detail)
  window.addEventListener("WebChannelMessageToChrome", handler)
  return { details, stop: () => window.removeEventListener("WebChannelMessageToChrome", handler) }
}

function setUserAgent(ua: string): void {
  Object.defineProperty(window.navigator, "userAgent", { value: ua, configurable: true })
}

describe("sendToFirefox", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("sends the detail as an object on Firefox iOS (fxios)", () => {
    setUserAgent("Mozilla/5.0 (iPhone) FxiOS/143.0 Mobile/15E148 Safari/605.1.15")
    const { details, stop } = captureDispatched()

    sendToFirefox("fxaccounts:oauth_login", { code: "c", state: "s" })
    stop()

    const detail = details[0] as { id: string; message: { command: string; data: unknown } }
    expect(typeof detail).toBe("object")
    expect(detail.id).toBe("account_updates")
    expect(detail.message.command).toBe("fxaccounts:oauth_login")
    expect(detail.message.data).toEqual({ code: "c", state: "s" })
  })

  it("sends the detail as a JSON string elsewhere (desktop, Fennec)", () => {
    setUserAgent("Mozilla/5.0 (Macintosh) Firefox/143.0")
    const { details, stop } = captureDispatched()

    sendToFirefox("fxaccounts:oauth_login", { code: "c", state: "s" })
    stop()

    expect(typeof details[0]).toBe("string")
    const parsed = JSON.parse(details[0] as string)
    expect(parsed.id).toBe("account_updates")
    expect(parsed.message.command).toBe("fxaccounts:oauth_login")
  })
})
