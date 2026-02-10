import { AlertTriangle } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import type { BrowserCompatibility } from "@/lib/types"
import { getMissingFeatures } from "@/lib/browser-check"

interface BrowserWarningProps {
  compatibility: BrowserCompatibility
}

export function BrowserWarning({ compatibility }: BrowserWarningProps) {
  const missing = getMissingFeatures(compatibility)

  return (
    <Alert variant="destructive">
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>Browser Compatibility Warning</AlertTitle>
      <AlertDescription className="space-y-2">
        <p>Your browser does not support required features:</p>
        <ul className="list-disc list-inside space-y-1">
          {missing.map((feature) => (
            <li key={feature}>{feature}</li>
          ))}
        </ul>
        <p>
          Please use a modern browser such as Firefox 34+, Chrome 37+, Safari
          11+, or Edge 79+.
        </p>
      </AlertDescription>
    </Alert>
  )
}
