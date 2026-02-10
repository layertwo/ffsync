import { LogIn, Shield, Clock, Info } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

interface LandingPageProps {
  onAuthenticate: () => void
}

const SCOPES = [
  { name: "openid", description: "Basic identity verification" },
  { name: "profile", description: "Your name and profile information" },
  { name: "email", description: "Your email address" },
]

export function LandingPage({ onAuthenticate }: LandingPageProps) {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Firefox Sync Setup</CardTitle>
          <CardDescription>
            Authenticate with your identity provider to configure Firefox Sync
            with your self-hosted server.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            This tool will guide you through authenticating with your OIDC
            provider and obtaining the Token Server URI needed to configure
            Firefox Sync.
          </p>

          <div className="space-y-3">
            <h3 className="text-sm font-medium">How it works</h3>
            <ol className="list-decimal list-inside space-y-1.5 text-sm text-muted-foreground">
              <li>You sign in with your identity provider</li>
              <li>We verify your credentials with the Token Server</li>
              <li>
                You get the Token Server URI to paste into Firefox's{" "}
                <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
                  about:config
                </code>
              </li>
            </ol>
          </div>

          <div className="flex items-start gap-2 rounded-md border p-3">
            <Shield className="mt-0.5 h-4 w-4 text-muted-foreground shrink-0" />
            <div className="space-y-1">
              <p className="text-sm font-medium">Security</p>
              <p className="text-xs text-muted-foreground">
                Authentication happens directly with your OIDC provider using
                PKCE to prevent code interception. No credentials are stored by
                this application — all session data is cleared when the tab
                closes.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-2 rounded-md border p-3">
            <Clock className="mt-0.5 h-4 w-4 text-muted-foreground shrink-0" />
            <div className="space-y-1">
              <p className="text-sm font-medium">Credential lifetime</p>
              <p className="text-xs text-muted-foreground">
                HAWK credentials expire after 300 seconds. Firefox will
                automatically refresh them once configured.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-2 rounded-md border p-3">
            <Info className="mt-0.5 h-4 w-4 text-muted-foreground shrink-0" />
            <div className="space-y-1">
              <p className="text-sm font-medium">Requested permissions</p>
              <ul className="space-y-1">
                {SCOPES.map((scope) => (
                  <li
                    key={scope.name}
                    className="text-xs text-muted-foreground"
                  >
                    <code className="rounded bg-muted px-1 py-0.5 font-mono">
                      {scope.name}
                    </code>{" "}
                    — {scope.description}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </CardContent>
        <CardFooter>
          <Button onClick={onAuthenticate} size="lg" className="w-full">
            <LogIn className="mr-2 h-4 w-4" />
            Sign in with your identity provider
          </Button>
        </CardFooter>
      </Card>
    </div>
  )
}
