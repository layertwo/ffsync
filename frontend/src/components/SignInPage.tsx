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
  initiateOAuthFlow,
  validateCallback,
} from "@/lib/oauth"
import * as session from "@/lib/session"
import { stretchPassword } from "@/lib/fxa-crypto"
import {
  createAccount,
  exchangeOIDCCode,
  login,
  requestOAuthCode,
} from "@/lib/auth-client"
import {
  listenFromFirefox,
  sendCanLinkAccount,
  sendFxAStatus,
  sendLogin,
  sendOAuthLogin,
} from "@/lib/webchannel"
import { generatePKCE } from "@/lib/pkce"
import { deriveAndEncryptSyncKeys } from "@/lib/sync-keys"
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
  keysJwk?: string
}

export function SignInPage({
  config,
  action,
  service,
  state: fxaState,
  codeChallenge: fxaCodeChallenge,
  clientId: fxaClientId,
  scope: fxaScope,
  keysJwk,
}: SignInPageProps) {
  const [signInState, setSignInState] = useState<SignInState>({
    step: "oidc-login",
  })
  const [passwordLoading, setPasswordLoading] = useState(false)
  const initialized = useRef(false)

  const syncEngines = [
    "bookmarks",
    "history",
    "passwords",
    "tabs",
    "prefs",
    "addons",
  ]

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
            engines: syncEngines,
          },
          messageId
        )
      } else if (command === "fxaccounts:can_link_account") {
        sendCanLinkAccount(true, messageId)
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

      if (!config.authServerUrl) {
        handleError("authServerUrl is not configured.")
        return
      }

      const codeVerifier = session.getCodeVerifier()
      if (!codeVerifier) {
        handleError("Missing code verifier. The session may have expired. Please try again.")
        return
      }

      setSignInState({
        step: "processing",
        message: "Exchanging authorization code...",
      })
      const result = await exchangeOIDCCode(
        config.authServerUrl,
        code,
        codeVerifier,
        config.redirectUri
      )
      session.removeCodeVerifier()

      setSignInState({
        step: "sync-password",
        email: result.email,
        oidcToken: result.access_token,
        accountExists: result.account_exists,
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
      console.log("[ffsync] OAuth params:", {
        hasState: !!fxaState,
        hasCodeChallenge: !!fxaCodeChallenge,
        hasKeysJwk: !!keysJwk,
        oauthState: oauthState.slice(0, 8) + "...",
      })
      if (!fxaCodeChallenge) {
        const pkce = await generatePKCE()
        codeChallenge = pkce.codeChallenge
        codeVerifier = pkce.codeVerifier
      }

      let keysJwe: string | undefined
      if (keysJwk) {
        setSignInState({
          step: "processing",
          message: "Deriving sync encryption keys...",
        })
        keysJwe = await deriveAndEncryptSyncKeys({
          authServerUrl: config.authServerUrl,
          keyFetchTokenHex: keyFetchToken,
          unwrapBKeyHex: unwrapBKey,
          sessionTokenHex: sessionToken,
          keysJwkB64: keysJwk,
          scope: fxaScope,
        })
      }

      const oauthResult = await requestOAuthCode(
        config.authServerUrl,
        sessionToken,
        fxaClientId,
        fxaScope,
        oauthState,
        codeChallenge,
        keysJwe
      )

      setSignInState({
        step: "processing",
        message: "Completing sign-in...",
      })

      console.log("[ffsync] OAuth code obtained, sending webchannel messages")
      // Send fxaccounts:login first so Firefox stores the account data
      // (uid, sessionToken, etc.) that oauthLogin reads back.
      sendLogin({
        email,
        uid,
        sessionToken,
        keyFetchToken,
        unwrapBKey,
        verified: true,
        declinedSyncEngines: [],
        offeredSyncEngines: syncEngines,
        verifiedCanLinkAccount: true,
      })

      // Then send fxaccounts:oauth_login so Firefox exchanges the code
      // at /v1/oauth/token and receives keys_jwe with the scoped sync keys.
      sendOAuthLogin(oauthResult.code, oauthResult.state, [], syncEngines)

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
    if (!config.authServerUrl) {
      handleError("authServerUrl is not configured.")
      return
    }
    discoverOIDC(config.authServerUrl).then((oidcConfig: OIDCConfiguration) => {
      // Stash Firefox's query params so they survive the OIDC redirect round-trip
      if (window.location.search) {
        session.storeFxAParams(window.location.search)
      }
      initiateOAuthFlow(config, oidcConfig)
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

