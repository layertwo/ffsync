import { useCallback, useEffect, useRef, useState } from "react"
import { Link } from "react-router"
import { LogIn, CheckCircle2, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import type { AppConfig, OIDCConfiguration } from "@/lib/types"
import { discoverOIDC } from "@/lib/oidc"
import {
  detectCallback,
  exchangeCodeForToken,
  initiateOAuthFlow,
  validateCallback,
} from "@/lib/oauth"
import * as session from "@/lib/session"
import { stretchPassword } from "@/lib/fxa-crypto"
import {
  checkAccountStatus,
  createAccount,
  login,
  requestOAuthCode,
} from "@/lib/auth-client"
import {
  listenFromFirefox,
  sendFxAStatus,
  sendOAuthLogin,
} from "@/lib/webchannel"
import { generatePKCE } from "@/lib/pkce"
import { SyncPasswordForm } from "@/components/SyncPasswordForm"

type SignInState =
  | { step: "oidc-login" }
  | { step: "processing"; message: string }
  | { step: "sync-password"; email: string; oidcToken: string; accountExists: boolean }
  | { step: "complete" }
  | { step: "error"; message: string }

interface SignInPageProps {
  config: AppConfig
  action: string
  service?: string
  state?: string
  codeChallenge?: string
  clientId: string
  scope: string
}

export function SignInPage({
  config,
  action,
  service,
  state: fxaState,
  codeChallenge: fxaCodeChallenge,
  clientId: fxaClientId,
  scope: fxaScope,
}: SignInPageProps) {
  const [signInState, setSignInState] = useState<SignInState>({
    step: "oidc-login",
  })
  const [passwordLoading, setPasswordLoading] = useState(false)
  const initialized = useRef(false)

  const handleError = useCallback((msg: string) => {
    console.error(`[ffsync] FxA sign-in error: ${msg}`)
    setSignInState({ step: "error", message: msg })
  }, [])

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true

    const cleanup = listenFromFirefox((command, _data, messageId) => {
      if (command === "fxaccounts:fxa_status") {
        sendFxAStatus(
          {
            choose_what_to_sync: true,
            engines: [
              "bookmarks",
              "history",
              "passwords",
              "tabs",
              "prefs",
              "addons",
            ],
          },
          messageId
        )
      }
    })

    const callbackParams = detectCallback()
    if (callbackParams) {
      handleOIDCCallback(callbackParams)
    }

    return cleanup
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleOIDCCallback(params: URLSearchParams) {
    try {
      window.history.replaceState(
        {},
        "",
        `${window.location.pathname}${window.location.search.replace(/[?&]?(code|state|error|error_description)=[^&]*/g, "").replace(/^\?$/, "")}`
      )

      setSignInState({
        step: "processing",
        message: "Processing identity verification...",
      })

      const code = validateCallback(params)

      const oidcConfig = await discoverOIDC(config.authServerUrl!)
      const tokens = await exchangeCodeForToken(config, oidcConfig, code)
      const accessToken = tokens.access_token

      const email = await extractEmailFromToken(
        oidcConfig.userinfoEndpoint,
        accessToken
      )

      if (!config.authServerUrl) {
        handleError("authServerUrl is not configured.")
        return
      }

      setSignInState({
        step: "processing",
        message: "Checking account status...",
      })
      const status = await checkAccountStatus(config.authServerUrl, email)

      setSignInState({
        step: "sync-password",
        email,
        oidcToken: accessToken,
        accountExists: status.exists,
      })
    } catch (err) {
      handleError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handlePasswordSubmit(password: string) {
    if (signInState.step !== "sync-password") return
    const { email, oidcToken, accountExists } = signInState

    if (!config.authServerUrl) {
      handleError("authServerUrl is not configured.")
      return
    }

    setPasswordLoading(true)
    try {
      setSignInState({
        step: "processing",
        message: "Deriving encryption keys...",
      })
      const { authPW, unwrapBKey } = await stretchPassword(email, password)

      let sessionToken: string
      let keyFetchToken: string
      let uid: string

      if (accountExists) {
        setSignInState({
          step: "processing",
          message: "Signing in...",
        })
        const result = await login(config.authServerUrl, email, authPW)
        sessionToken = result.sessionToken
        keyFetchToken = result.keyFetchToken
        uid = result.uid
      } else {
        setSignInState({
          step: "processing",
          message: "Creating account...",
        })
        const result = await createAccount(
          config.authServerUrl,
          email,
          authPW,
          oidcToken
        )
        sessionToken = result.sessionToken
        keyFetchToken = result.keyFetchToken
        uid = result.uid
      }

      setSignInState({
        step: "processing",
        message: "Requesting authorization code...",
      })

      const oauthState = fxaState ?? crypto.randomUUID()
      let codeChallenge = fxaCodeChallenge ?? ""
      let codeVerifier: string | undefined
      if (!fxaCodeChallenge) {
        const pkce = await generatePKCE()
        codeChallenge = pkce.codeChallenge
        codeVerifier = pkce.codeVerifier
      }

      const oauthResult = await requestOAuthCode(
        config.authServerUrl,
        sessionToken,
        fxaClientId,
        fxaScope,
        oauthState,
        codeChallenge
      )

      setSignInState({
        step: "processing",
        message: "Completing sign-in...",
      })

      sendOAuthLogin(oauthResult.code, oauthResult.state)

      void uid
      void keyFetchToken
      void unwrapBKey
      void codeVerifier
      void service
      void action

      setSignInState({ step: "complete" })
    } catch (err) {
      handleError(err instanceof Error ? err.message : String(err))
      setPasswordLoading(false)
    }
  }

  function handleStartOIDC() {
    discoverOIDC(config.authServerUrl!).then((oidcConfig: OIDCConfiguration) => {
      const currentUrl = new URL(window.location.href)
      const redirectConfig = {
        ...config,
        redirectUri: `${currentUrl.origin}${currentUrl.pathname}${currentUrl.search}`,
      }
      initiateOAuthFlow(redirectConfig, oidcConfig)
    }).catch((err: unknown) => {
      handleError(err instanceof Error ? err.message : String(err))
    })
  }

  if (signInState.step === "oidc-login") {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Sign in to Firefox Sync</CardTitle>
          <CardDescription>
            First, verify your identity with your identity provider, then set
            your sync encryption password.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-3">
            <h3 className="text-sm font-medium">How it works</h3>
            <ol className="list-decimal list-inside space-y-1.5 text-sm text-muted-foreground">
              <li>Verify your identity with your identity provider</li>
              <li>Set a sync password for encryption</li>
              <li>Firefox Sync will be configured automatically</li>
            </ol>
          </div>
          <Button onClick={handleStartOIDC} size="lg" className="w-full">
            <LogIn className="mr-2 h-4 w-4" />
            Continue with identity provider
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            <Link to="/manual" className="underline hover:text-foreground">
              Manual setup
            </Link>{" "}
            — configure Firefox Sync via about:config instead
          </p>
        </CardContent>
      </Card>
    )
  }

  if (signInState.step === "processing") {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-16 space-y-4">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">
            {signInState.message}
          </p>
        </CardContent>
      </Card>
    )
  }

  if (signInState.step === "sync-password") {
    return (
      <SyncPasswordForm
        email={signInState.email}
        accountExists={signInState.accountExists}
        loading={passwordLoading}
        onSubmit={handlePasswordSubmit}
      />
    )
  }

  if (signInState.step === "complete") {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-green-500" />
            <CardTitle className="text-2xl">Sync Setup Complete</CardTitle>
          </div>
          <CardDescription>
            Firefox Sync has been configured. You can close this tab. Firefox
            will now sync your data automatically.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  if (signInState.step === "error") {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Sign-in Error</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert variant="destructive">
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{signInState.message}</AlertDescription>
          </Alert>
          <Button
            onClick={() => {
              session.clearAll()
              setSignInState({ step: "oidc-login" })
            }}
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

async function extractEmailFromToken(
  userinfoEndpoint: string,
  accessToken: string
): Promise<string> {
  let response: Response
  try {
    response = await fetch(userinfoEndpoint, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  } catch {
    throw new Error("Failed to fetch user info from identity provider.")
  }

  if (!response.ok) {
    throw new Error(
      `Identity provider userinfo failed (${response.status}).`
    )
  }

  const data = await response.json()
  if (!data.email) {
    throw new Error(
      "Identity provider did not return an email address. Ensure the 'email' scope is granted."
    )
  }

  return data.email as string
}
