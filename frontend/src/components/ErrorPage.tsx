import { AlertCircle, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

interface ErrorPageProps {
  title: string
  message: string
  details?: string
  onRestart: () => void
}

export function ErrorPage({ title, message, details, onRestart }: ErrorPageProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <CardTitle className="text-2xl">{title}</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{message}</AlertDescription>
        </Alert>

        {details && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium">Troubleshooting</h3>
            <p className="text-sm text-muted-foreground whitespace-pre-line">
              {details}
            </p>
          </div>
        )}
      </CardContent>
      <CardFooter>
        <Button onClick={onRestart} className="w-full">
          <RefreshCw className="mr-2 h-4 w-4" />
          Try again
        </Button>
      </CardFooter>
    </Card>
  )
}
