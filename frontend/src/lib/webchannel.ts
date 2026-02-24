const FXA_WEBCHANNEL_ID = "account_updates"

interface WebChannelMessage {
  id: string
  message: {
    command: string
    data: Record<string, unknown>
    messageId?: string
  }
}

export function sendToFirefox(
  command: string,
  data: Record<string, unknown>,
  messageId?: string
): void {
  const detail: WebChannelMessage = {
    id: FXA_WEBCHANNEL_ID,
    message: { command, data, messageId },
  }
  window.dispatchEvent(
    new CustomEvent("WebChannelMessageToChrome", {
      detail: JSON.stringify(detail),
    })
  )
}

export function listenFromFirefox(
  callback: (
    command: string,
    data: Record<string, unknown>,
    messageId?: string
  ) => void
): () => void {
  const handler = (event: Event) => {
    const detail = (event as CustomEvent).detail
    const parsed =
      typeof detail === "string" ? JSON.parse(detail) : detail
    const { command, data, messageId } = parsed.message
    callback(command, data ?? {}, messageId)
  }
  window.addEventListener("WebChannelMessageToContent", handler)
  return () => window.removeEventListener("WebChannelMessageToContent", handler)
}

export function sendOAuthLogin(
  code: string,
  state: string,
  declinedSyncEngines: string[] = []
): void {
  sendToFirefox("fxaccounts:oauth_login", {
    code,
    state,
    redirect: "urn:ietf:wg:oauth:2.0:oob",
    declinedSyncEngines,
  })
}

export function sendFxAStatus(
  capabilities: Record<string, unknown>,
  messageId?: string
): void {
  sendToFirefox(
    "fxaccounts:fxa_status",
    {
      capabilities,
      signedInUser: null,
    },
    messageId
  )
}
