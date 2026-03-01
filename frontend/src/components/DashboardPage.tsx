import { useState } from "react"
import { CheckCircle2, Copy, Check, LogOut, ChevronDown, ChevronRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

interface DashboardPageProps {
  email: string
  autoconfigUri: string
  onSignOut: () => void
}

export function DashboardPage({ email, autoconfigUri, onSignOut }: DashboardPageProps) {
  const [copied, setCopied] = useState(false)
  const [expanded, setExpanded] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(autoconfigUri)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      const el = document.getElementById("autoconfig-uri")
      if (el) {
        const range = document.createRange()
        range.selectNodeContents(el)
        const selection = window.getSelection()
        selection?.removeAllRanges()
        selection?.addRange(range)
      }
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-green-500" />
            <CardTitle className="text-2xl">Welcome</CardTitle>
          </div>
          <CardDescription>
            Signed in as <span className="font-medium text-foreground">{email}</span>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Your ffsync server is configured and ready. Firefox will
            sync your data automatically.
          </p>

          <div className="rounded-md border">
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex w-full items-center gap-2 p-3 text-left text-sm font-medium hover:bg-muted/50 transition-colors"
            >
              {expanded ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
              Manual Firefox configuration
            </button>
            {expanded && (
              <div className="border-t px-3 pb-3 pt-2 space-y-3">
                <p className="text-xs text-muted-foreground">
                  If Firefox didn't configure automatically, set this
                  in{" "}
                  <code className="rounded bg-muted px-1 py-0.5 font-mono">
                    about:config
                  </code>
                  :
                </p>
                <div className="space-y-1">
                  <label className="text-xs font-medium">
                    identity.fxaccounts.autoconfig.uri
                  </label>
                  <div className="flex items-center gap-2">
                    <code
                      id="autoconfig-uri"
                      className="flex-1 rounded-md border bg-muted px-3 py-2 font-mono text-xs break-all"
                    >
                      {autoconfigUri}
                    </code>
                    <Button
                      variant="outline"
                      size="icon"
                      onClick={handleCopy}
                      aria-label="Copy URI"
                    >
                      {copied ? (
                        <Check className="h-4 w-4 text-green-500" />
                      ) : (
                        <Copy className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                  {copied && (
                    <p className="text-xs text-green-600">
                      Copied to clipboard
                    </p>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  Firefox will auto-discover the auth, token, and profile
                  server URLs from{" "}
                  <code className="rounded bg-muted px-1 py-0.5 font-mono">
                    /.well-known/fxa-client-configuration
                  </code>
                  .
                </p>
              </div>
            )}
          </div>
        </CardContent>
        <CardFooter>
          <Button variant="outline" onClick={onSignOut} className="w-full">
            <LogOut className="mr-2 h-4 w-4" />
            Sign out
          </Button>
        </CardFooter>
      </Card>
    </div>
  )
}
