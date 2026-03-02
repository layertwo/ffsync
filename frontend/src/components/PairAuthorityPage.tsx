import { useCallback, useEffect, useRef, useState } from "react"
import { QRCodeSVG } from "qrcode.react"
import { Loader2, CheckCircle2, XCircle, Smartphone } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import type { AppConfig } from "@/lib/types"
import { PairingChannel } from "@/lib/pairing-channel"
import { buildPairUrl } from "@/lib/pairing"
import { requestOAuthCode } from "@/lib/auth-client"
import { generatePKCE } from "@/lib/pkce"
import {
  listenFromFirefox,
  sendPairComplete,
  sendPairDecline,
} from "@/lib/webchannel"
import * as session from "@/lib/session"

type PairAuthorityState =
  | { step: "creating-channel" }
  | { step: "showing-qr"; pairUrl: string; channel: PairingChannel }
  | {
      step: "confirming"
      channel: PairingChannel
      suppRequest: SuppRequest
    }
  | { step: "authorizing" }
  | { step: "complete" }
  | { step: "error"; message: string }

interface SuppRequest {
  client_id: string
  state: string
  scope: string
  code_challenge: string
  code_challenge_method: string
  keys_jwk?: string
}

interface PairAuthorityPageProps {
  config: AppConfig
}

export function PairAuthorityPage({ config }: PairAuthorityPageProps) {
  const [state, setState] = useState<PairAuthorityState>({
    step: "creating-channel",
  })
  const initialized = useRef(false)
  const channelRef = useRef<PairingChannel | null>(null)

  const handleError = useCallback((msg: string) => {
    console.error(`[ffsync:pair] Authority error: ${msg}`)
    setState({ step: "error", message: msg })
  }, [])

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true

    const cleanup = listenFromFirefox((command, _data, messageId) => {
      if (command === "fxaccounts:pair_decline") {
        sendPairDecline(messageId)
        if (channelRef.current && !channelRef.current.closed) {
          channelRef.current.close().catch(() => {})
        }
        setState({ step: "error", message: "Pairing was declined." })
      } else if (command === "fxaccounts:pair_complete") {
        sendPairComplete(messageId)
      }
    })

    initChannel()

    return () => {
      cleanup()
      if (channelRef.current && !channelRef.current.closed) {
        channelRef.current.close().catch(() => {})
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function initChannel() {
    if (!config.pairingServerUrl) {
      handleError(
        "pairingServerUrl is not configured. Add it to config.json."
      )
      return
    }

    try {
      const channel = await PairingChannel.create(config.pairingServerUrl)
      channelRef.current = channel

      const contentUrl = config.redirectUri.replace(/\/+$/, "")
      const pairUrl = buildPairUrl(
        contentUrl,
        channel.channelId,
        channel.channelKey
      )

      setState({ step: "showing-qr", pairUrl, channel })

      // Listen for supplicant request
      channel.addEventListener("message", (event: Event) => {
        const detail = (event as CustomEvent).detail
        const data = detail.data
        if (data.message === "pair:supp:request") {
          setState({
            step: "confirming",
            channel,
            suppRequest: data.data as SuppRequest,
          })
          // Send authority metadata back
          const auth = session.getAuth()
          channel.send({
            message: "pair:auth:metadata",
            data: {
              email: auth?.email ?? "unknown",
              uid: auth?.uid ?? "unknown",
            },
          })
        }
      })

      channel.addEventListener("error", () => {
        handleError("Pairing channel connection error.")
      })

      channel.addEventListener("close", () => {
        // Peer closed the channel
      })
    } catch (err) {
      handleError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleApprove() {
    if (state.step !== "confirming") return
    const { channel, suppRequest } = state

    setState({ step: "authorizing" })

    try {
      const auth = session.getAuth()
      if (!auth || !config.authServerUrl) {
        handleError(
          "You must be signed in to approve pairing. Please sign in first."
        )
        return
      }

      const redirectUri =
        "urn:ietf:wg:oauth:2.0:oob:pair-auth-webchannel"

      // Generate our own PKCE if needed, or use the supplicant's
      let codeChallenge = suppRequest.code_challenge
      if (!codeChallenge) {
        const pkce = await generatePKCE()
        codeChallenge = pkce.codeChallenge
      }

      const oauthResult = await requestOAuthCode(
        config.authServerUrl,
        auth.sessionToken,
        suppRequest.client_id || config.clientId,
        suppRequest.scope ||
          "https://identity.mozilla.com/apps/oldsync profile",
        suppRequest.state || crypto.randomUUID(),
        codeChallenge,
        undefined,
        redirectUri
      )

      // Send the OAuth code through the pairing channel
      await channel.send({
        message: "pair:auth:authorize",
        data: {
          code: oauthResult.code,
          state: oauthResult.state,
          redirect: oauthResult.redirect,
        },
      })

      setState({ step: "complete" })
    } catch (err) {
      handleError(err instanceof Error ? err.message : String(err))
    }
  }

  function handleDecline() {
    if (state.step !== "confirming") return
    const { channel } = state
    channel.send({ message: "pair:auth:decline", data: {} }).catch(() => {})
    channel.close().catch(() => {})
    setState({ step: "error", message: "Pairing declined." })
  }

  if (state.step === "creating-channel") {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-16 space-y-4">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">
            Creating pairing channel...
          </p>
        </CardContent>
      </Card>
    )
  }

  if (state.step === "showing-qr") {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Pair a Device</CardTitle>
          <CardDescription>
            Scan this QR code with the device you want to pair.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col items-center space-y-6">
          <div className="rounded-lg border bg-white p-4">
            <QRCodeSVG value={state.pairUrl} size={200} />
          </div>
          <p className="text-xs text-muted-foreground text-center max-w-xs">
            Waiting for the other device to connect...
          </p>
        </CardContent>
      </Card>
    )
  }

  if (state.step === "confirming") {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Smartphone className="h-5 w-5 text-primary" />
            <CardTitle className="text-2xl">Confirm Pairing</CardTitle>
          </div>
          <CardDescription>
            A device wants to connect to your account.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-lg border p-4 space-y-2">
            <p className="text-sm font-medium">Requesting access to:</p>
            <p className="text-sm text-muted-foreground">
              {state.suppRequest.scope || "Sync data"}
            </p>
          </div>
          <div className="flex gap-3">
            <Button onClick={handleApprove} className="flex-1">
              Approve
            </Button>
            <Button
              onClick={handleDecline}
              variant="outline"
              className="flex-1"
            >
              Decline
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (state.step === "authorizing") {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-16 space-y-4">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">
            Authorizing device...
          </p>
        </CardContent>
      </Card>
    )
  }

  if (state.step === "complete") {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-green-500" />
            <CardTitle className="text-2xl">Device Paired</CardTitle>
          </div>
          <CardDescription>
            The device has been successfully paired. You can close this page.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  if (state.step === "error") {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <XCircle className="h-5 w-5 text-destructive" />
            <CardTitle className="text-2xl">Pairing Error</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert variant="destructive">
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{state.message}</AlertDescription>
          </Alert>
          <Button
            onClick={() => window.location.reload()}
            className="w-full"
          >
            Try again
          </Button>
        </CardContent>
      </Card>
    )
  }

  return null
}
