import { useCallback, useEffect, useRef, useState } from "react"
import { useSearchParams } from "react-router"
import type { AppConfig } from "@/lib/types"
import { checkBrowserCompatibility } from "@/lib/browser-check"
import { loadConfig } from "@/lib/config"
import { checkSessionStatus } from "@/lib/auth-client"
import * as session from "@/lib/session"
import { LoadingPage } from "@/components/LoadingPage"
import { ErrorPage } from "@/components/ErrorPage"
import { BrowserWarning } from "@/components/BrowserWarning"
import { SignInPage } from "@/components/SignInPage"
import { DashboardPage } from "@/components/DashboardPage"

type MainState =
  | { kind: "initializing" }
  | { kind: "sign-in" }
  | { kind: "dashboard"; email: string }
  | { kind: "error"; message: string }

function MainFlow() {
  const [searchParams] = useSearchParams()
  const [state, setState] = useState<MainState>({ kind: "initializing" })
  const [config, setConfig] = useState<AppConfig | null>(null)
  const initialized = useRef(false)

  const compatibility = checkBrowserCompatibility()

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true

    async function init() {
      if (!compatibility.allSupported) return

      try {
        const cfg = await loadConfig()
        setConfig(cfg)

        // If Firefox is driving (WebChannel params present), go straight to sign-in
        const hasFxAParams = searchParams.has("action") ||
          searchParams.has("code_challenge") ||
          searchParams.has("service")
        if (hasFxAParams) {
          setState({ kind: "sign-in" })
          return
        }

        // Check for existing session in localStorage
        const auth = session.getAuth()
        if (auth && cfg.authServerUrl) {
          try {
            await checkSessionStatus(cfg.authServerUrl, auth.sessionToken)
            setState({ kind: "dashboard", email: auth.email })
            return
          } catch {
            // Session invalid or expired — clear and fall through to sign-in
            session.clearAuth()
          }
        }

        setState({ kind: "sign-in" })
      } catch (err) {
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : String(err),
        })
      }
    }

    init()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleLoginComplete = useCallback(
    (email: string) => {
      setState({ kind: "dashboard", email })
    },
    []
  )

  const handleSignOut = useCallback(() => {
    session.clearAuth()
    setState({ kind: "sign-in" })
  }, [])

  if (!compatibility.allSupported) {
    return <BrowserWarning compatibility={compatibility} />
  }

  if (state.kind === "initializing" || !config) {
    return <LoadingPage message="Loading..." />
  }

  if (state.kind === "error") {
    return (
      <ErrorPage
        title="Configuration Error"
        message={state.message}
        onRestart={() => window.location.reload()}
      />
    )
  }

  if (state.kind === "dashboard") {
    // Derive autoconfig URI from redirectUri (the frontend domain)
    const autoconfigUri = config.redirectUri.replace(/\/+$/, "")
    return (
      <DashboardPage
        email={state.email}
        autoconfigUri={autoconfigUri}
        onSignOut={handleSignOut}
      />
    )
  }

  // state.kind === "sign-in"
  // Restore FxA params from session storage (survives OIDC redirect)
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
      onLoginComplete={handleLoginComplete}
    />
  )
}

export default function App() {
  return (
    <Layout>
      <MainFlow />
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
