import { useState } from "react"
import { CheckCircle2, Copy, Check, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"

interface SuccessPageProps {
  tokenServerUri: string
  onRestart: () => void
}

export function SuccessPage({ tokenServerUri, onRestart }: SuccessPageProps) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(tokenServerUri)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback: select the text for manual copy
      const el = document.getElementById("token-server-uri")
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
            <CardTitle className="text-2xl">Authentication Successful</CardTitle>
          </div>
          <CardDescription>
            Your identity has been verified with the Token Server. Use the URI
            below to configure Firefox Sync.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <label className="text-sm font-medium">Token Server URI</label>
            <div className="flex items-center gap-2">
              <code
                id="token-server-uri"
                className="flex-1 rounded-md border bg-muted px-3 py-2 font-mono text-sm break-all"
              >
                {tokenServerUri}
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
              <p className="text-xs text-green-600">Copied to clipboard</p>
            )}
          </div>

          <div className="space-y-3">
            <h3 className="text-sm font-medium">
              Configure Firefox Sync
            </h3>
            <Alert>
              <AlertDescription className="text-xs">
                You must set the Token Server URI <strong>before</strong>{" "}
                signing into Firefox Sync.
              </AlertDescription>
            </Alert>
            <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
              <li>
                Open Firefox and type{" "}
                <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
                  about:config
                </code>{" "}
                in the address bar
              </li>
              <li>Accept the risk warning if prompted</li>
              <li>
                Search for{" "}
                <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
                  identity.sync.tokenserver.uri
                </code>
              </li>
              <li>
                Set the value to the Token Server URI shown above
              </li>
              <li>
                Sign into Firefox Sync normally using your identity provider
                credentials
              </li>
            </ol>
            <p className="text-xs text-muted-foreground">
              Once configured, Firefox will automatically obtain and refresh
              credentials from the Token Server. The Token Server validates all
              requests to ensure security.
            </p>
          </div>
        </CardContent>
        <CardFooter className="flex flex-col gap-3">
          <Button variant="outline" onClick={onRestart} className="w-full">
            <RefreshCw className="mr-2 h-4 w-4" />
            Authenticate again
          </Button>
          <p className="text-xs text-center text-muted-foreground">
            Re-authentication is only needed for testing. Firefox handles
            authentication automatically once configured.
          </p>
        </CardFooter>
      </Card>
    </div>
  )
}
