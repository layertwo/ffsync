import { useCallback, useEffect, useRef, useState } from "react"
import type { AppConfig, AppState, OIDCConfiguration } from "@/lib/types"
import { checkBrowserCompatibility } from "@/lib/browser-check"
import { loadConfig } from "@/lib/config"
import { discoverOIDC } from "@/lib/oidc"
import {
  detectCallback,
  exchangeCodeForToken,
  initiateOAuthFlow,
  validateCallback,
} from "@/lib/oauth"
import { validateWithTokenServer } from "@/lib/token-server"
import * as session from "@/lib/session"
import { LandingPage } from "@/components/LandingPage"
import { LoadingPage } from "@/components/LoadingPage"
import { SuccessPage } from "@/components/SuccessPage"
import { ErrorPage } from "@/components/ErrorPage"
import { BrowserWarning } from "@/components/BrowserWarning"

export default function App() {
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
        const oidcConfig = await discoverOIDC(cfg.oidcProviderUrl)
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
      oidcConfig: OIDCConfiguration,
      params: URLSearchParams
    ) {
      try {
        window.history.replaceState({}, "", window.location.pathname)

        setAppState({
          kind: "processing",
          message: "Validating authorization response...",
        })
        const code = validateCallback(params)

        setAppState({
          kind: "processing",
          message: "Exchanging authorization code for token...",
        })
        const tokens = await exchangeCodeForToken(cfg, oidcConfig, code)

        setAppState({
          kind: "processing",
          message: "Validating with Token Server...",
        })
        await validateWithTokenServer(cfg.tokenServerUrl, tokens.access_token)

        const tokenServerUri = `${cfg.tokenServerUrl}/1.0/sync/1.5`
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
    return (
      <Layout>
        <BrowserWarning compatibility={compatibility} />
      </Layout>
    )
  }

  return (
    <Layout>
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
