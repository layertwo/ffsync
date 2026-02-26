import { useCallback, useEffect, useRef, useState } from "react"
import { Routes, Route, useSearchParams } from "react-router"
import type { AppConfig, AppState, OIDCConfiguration } from "@/lib/types"
import { checkBrowserCompatibility } from "@/lib/browser-check"
import { loadConfig } from "@/lib/config"
import { discoverOIDC } from "@/lib/oidc"
import {
  detectCallback,
  initiateOAuthFlow,
  validateCallback,
} from "@/lib/oauth"
import { exchangeOIDCCode } from "@/lib/auth-client"
import {
  getTokenServerBaseUrl,
  validateWithTokenServer,
} from "@/lib/token-server"
import * as session from "@/lib/session"
import { LandingPage } from "@/components/LandingPage"
import { LoadingPage } from "@/components/LoadingPage"
import { SuccessPage } from "@/components/SuccessPage"
import { ErrorPage } from "@/components/ErrorPage"
import { BrowserWarning } from "@/components/BrowserWarning"
import { SignInPage } from "@/components/SignInPage"

function ManualSetupFlow() {
  const [appState, setAppState] = useState<AppState>({ kind: "initializing" })
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [oidc, setOidc] = useState<OIDCConfiguration | null>(null)
  const initialized = useRef(false)

  const compatibility = checkBrowserCompatibility()

  const showError = useCallback(
    (title: string, message: string, details?: string) => {
      if (import.meta.env.DEV) {
        console.error(`[ffsync] ${title}: ${message}`, details ?? "")
      } else {
        console.error(`[ffsync] ${title}`)
      }
      setAppState({ kind: "error", title, message, details })
    },
    []
  )

  const handleRestart = useCallback(() => {
    session.clearAll()
    window.history.replaceState({}, "", window.location.pathname)
    setAppState({ kind: "landing" })
  }, [])

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true

    async function init() {
      if (!compatibility.allSupported) return

      try {
        setAppState({ kind: "initializing" })

        const cfg = await loadConfig()
        setConfig(cfg)

        setAppState({
          kind: "processing",
          message: "Discovering OIDC endpoints...",
        })
        const oidcConfig = await discoverOIDC(cfg.authServerUrl!)
        setOidc(oidcConfig)

        const callbackParams = detectCallback()
        if (callbackParams) {
          await handleCallback(cfg, oidcConfig, callbackParams)
        } else {
          setAppState({ kind: "landing" })
        }
      } catch (err) {
        showError(
          "Initialization Failed",
          err instanceof Error ? err.message : String(err),
          "Check that config.json exists and is properly configured, and that the OIDC provider is reachable."
        )
      }
    }

    async function handleCallback(
      cfg: AppConfig,
      _oidcConfig: OIDCConfiguration,
      params: URLSearchParams
    ) {
      try {
        window.history.replaceState({}, "", window.location.pathname)

        setAppState({
          kind: "processing",
          message: "Validating authorization response...",
        })
        const code = validateCallback(params)

        const codeVerifier = session.getCodeVerifier()
        if (!codeVerifier) {
          throw new Error("Missing code verifier. The session may have expired. Please try again.")
        }

        setAppState({
          kind: "processing",
          message: "Exchanging authorization code...",
        })
        const result = await exchangeOIDCCode(
          cfg.authServerUrl!,
          code,
          codeVerifier,
          cfg.redirectUri
        )
        session.removeCodeVerifier()

        setAppState({
          kind: "processing",
          message: "Validating with Token Server...",
        })
        const baseUrl = getTokenServerBaseUrl(
          cfg.tokenServerUrl,
          cfg.authServerUrl
        )
        await validateWithTokenServer(baseUrl, result.access_token)

        const tokenServerUri = `${baseUrl}/1.0/sync/1.5`
        session.clearAll()
        setAppState({ kind: "success", tokenServerUri })
      } catch (err) {
        showError(
          "Authentication Failed",
          err instanceof Error ? err.message : String(err),
          "You can try authenticating again. If the problem persists, check your OIDC provider and Token Server configuration."
        )
      }
    }

    init()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleAuthenticate() {
    if (!config || !oidc) return
    initiateOAuthFlow(config, oidc)
  }

  if (!compatibility.allSupported) {
    return <BrowserWarning compatibility={compatibility} />
  }

  return (
    <>
      {appState.kind === "initializing" && (
        <LoadingPage message="Loading configuration..." />
      )}
      {appState.kind === "landing" && (
        <LandingPage onAuthenticate={handleAuthenticate} />
      )}
      {appState.kind === "processing" && (
        <LoadingPage message={appState.message} />
      )}
      {appState.kind === "success" && (
        <SuccessPage
          tokenServerUri={appState.tokenServerUri}
          onRestart={handleRestart}
        />
      )}
      {appState.kind === "error" && (
        <ErrorPage
          title={appState.title}
          message={appState.message}
          details={appState.details}
          onRestart={handleRestart}
        />
      )}
    </>
  )
}

function FxAFlow() {
  const [searchParams] = useSearchParams()
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [error, setError] = useState<string | null>(null)
  const initialized = useRef(false)

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true
    loadConfig().then(setConfig).catch((err) => setError(String(err)))
  }, [])

  if (error) {
    return (
      <ErrorPage
        title="Configuration Error"
        message={error}
        onRestart={() => window.location.reload()}
      />
    )
  }

  if (!config) {
    return <LoadingPage message="Loading configuration..." />
  }

  // After OIDC redirect, original Firefox params are lost from the URL.
  // Restore from session storage (stored before OIDC redirect in SignInPage).
  // All FxA params (state, code_challenge, keys_jwk, etc.) must be restored
  // so Firefox can match the OAuth flow it started in beginOAuthFlow().
  const storedFxAParams = session.getFxAParams()
  const fxaParams = storedFxAParams
    ? new URLSearchParams(storedFxAParams)
    : searchParams

  return (
    <SignInPage
      config={config}
      action={fxaParams.get("action") ?? "signin"}
      service={fxaParams.get("service") ?? undefined}
      state={fxaParams.get("state") ?? undefined}
      codeChallenge={fxaParams.get("code_challenge") ?? undefined}
      clientId={fxaParams.get("client_id") ?? config.clientId}
      scope={
        fxaParams.get("scope") ??
        "https://identity.mozilla.com/apps/oldsync profile"
      }
      keysJwk={fxaParams.get("keys_jwk") ?? undefined}
    />
  )
}

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/manual" element={<ManualSetupFlow />} />
        <Route path="*" element={<FxAFlow />} />
      </Routes>
    </Layout>
  )
}

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-lg px-4 py-8 sm:py-16">
        <header className="mb-8 text-center">
          <h1 className="text-3xl font-bold tracking-tight">Firefox Sync</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Self-hosted sync authentication
          </p>
        </header>
        <main>{children}</main>
      </div>
    </div>
  )
}
