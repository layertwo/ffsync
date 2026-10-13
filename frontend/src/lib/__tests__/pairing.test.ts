import { describe, expect, it } from "vitest"

import { buildPairUrl } from "@/lib/pairing"

const KEY = new Uint8Array([1, 2, 3])

describe("buildPairUrl", () => {
  it("builds the v2 URL iOS accepts", () => {
    expect(buildPairUrl("https://prod.example.com", "chan", KEY)).toBe(
      "https://prod.example.com/pair/#channel_id=chan&channel_key=AQID&v=2"
    )
  })
})
