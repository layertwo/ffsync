import { useEffect, useRef, useState } from "react"
import { CheckCircle2, XCircle } from "lucide-react"
import { LoadingPage } from "@/components/LoadingPage"
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
import { parsePairFragment } from "@/lib/pairing"
import { generatePKCE } from "@/lib/pkce"
import { getPairingOAuthParams, sendOAuthLogin } from "@/lib/pairing-bridge"

type PairSupplicantState =
  | { step: "connecting" }
  | { step: "waiting" }
  | {
      step: "confirming"
      email: string
      uid: string
    }
  | { step: "complete"; code: string; state: string }
  | { step: "error"; message: string }

interface PairSupplicantPageProps {
  config: AppConfig
}

export function PairSupplicantPage({ config }: PairSupplicantPageProps) {
  const [state, setState] = useState<PairSupplicantState>({
    step: "connecting",
  })
  const initialized = useRef(false)
  const channelRef = useRef<PairingChannel | null>(null)

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true

    initConnection()

    return () => {
      if (channelRef.current && !channelRef.current.closed) {
        channelRef.current.close().catch(() => {})
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function initConnection() {
    if (!config.pairingServerUrl) {
      setState({
        step: "error",
        message:
          "pairingServerUrl is not configured. Add it to config.json.",
      })
      return
    }

    const fragment = window.location.hash
    const parsed = parsePairFragment(fragment)
    if (!parsed) {
      setState({
        step: "error",
        message:
          "Invalid pairing link. Missing channel_id or channel_key in URL fragment.",
      })
      return
    }

    const { channelId, channelKey } = parsed

    try {
      const channel = await PairingChannel.connect(
        config.pairingServerUrl,
        channelId,
        channelKey
      )
      channelRef.current = channel

      // Prefer the browser-minted OAuth params; fall back to our own PKCE (v1).
      const bridgeParams = await getPairingOAuthParams()
      const requestData = bridgeParams
        ? { client_id: config.clientId, ...bridgeParams }
        : {
            client_id: config.clientId,
            state: crypto.randomUUID(),
            scope:
              "https://identity.mozilla.com/apps/oldsync profile",
            code_challenge: (await generatePKCE()).codeChallenge,
            code_challenge_method: "S256",
          }

      await channel.send({ message: "pair:supp:request", data: requestData })

      setState({ step: "waiting" })

      // Listen for authority messages
      channel.addEventListener("message", (event: Event) => {
        const detail = (event as CustomEvent).detail
        const data = detail.data

        if (data.message === "pair:auth:metadata") {
          setState({
            step: "confirming",
            email: data.data.email,
            uid: data.data.uid,
          })
        } else if (data.message === "pair:auth:authorize") {
          const { code, state } = data.data
          channel.send({ message: "pair:supp:authorize", data: {} }).catch(() => {})
          sendOAuthLogin({ code, state })
          setState({ step: "complete", code, state })
          channel.close().catch(() => {})
        } else if (
          data.message === "pair:auth:cancel" ||
          data.message === "pair:auth:decline"
        ) {
          setState({
            step: "error",
            message: "Pairing was declined by the other device.",
          })
          channel.close().catch(() => {})
        }
      })

      channel.addEventListener("error", () => {
        setState({
          step: "error",
          message: "Pairing channel connection error.",
        })
      })

      channel.addEventListener("close", () => {
        // Peer closed the channel
      })
    } catch (err) {
      setState({
        step: "error",
        message: err instanceof Error ? err.message : String(err),
      })
    }
  }

  if (state.step === "connecting") {
    return (
      <LoadingPage message="Connecting to pairing channel..." />
    )
  }

  if (state.step === "waiting") {
    return (
      <LoadingPage message="Waiting for the other device to approve..." />
    )
  }

  if (state.step === "confirming") {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Pairing in Progress</CardTitle>
          <CardDescription>
            Connecting to the account below. Please confirm on the other
            device.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-lg border p-4 space-y-1">
            <p className="text-sm font-medium">Account</p>
            <p className="text-sm text-muted-foreground">{state.email}</p>
          </div>
          <p className="text-xs text-muted-foreground text-center">
            Waiting for approval on the other device...
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
            <CardTitle className="text-2xl">Pairing Complete</CardTitle>
          </div>
          <CardDescription>
            This device has been successfully paired. You can close this page.
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
