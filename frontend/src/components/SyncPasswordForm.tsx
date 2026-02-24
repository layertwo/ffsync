import { useState } from "react"
import { KeyRound, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

interface SyncPasswordFormProps {
  email: string
  accountExists: boolean
  loading: boolean
  onSubmit: (password: string) => void
}

export function SyncPasswordForm({
  email,
  accountExists,
  loading,
  onSubmit,
}: SyncPasswordFormProps) {
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [error, setError] = useState<string | null>(null)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (!password) {
      setError("Please enter a sync password.")
      return
    }

    if (!accountExists && password.length < 8) {
      setError("Password must be at least 8 characters.")
      return
    }

    if (!accountExists && password !== confirmPassword) {
      setError("Passwords do not match.")
      return
    }

    onSubmit(password)
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-primary" />
          <CardTitle className="text-2xl">
            {accountExists ? "Enter Sync Password" : "Create Sync Password"}
          </CardTitle>
        </div>
        <CardDescription>
          {accountExists
            ? "Enter the sync password for your account to unlock your encryption keys."
            : "Choose a sync password to protect your encrypted data. This password is separate from your identity provider password."}
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit}>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label
              htmlFor="email"
              className="text-sm font-medium"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              disabled
              className="flex h-9 w-full rounded-md border border-input bg-muted px-3 py-1 text-sm text-muted-foreground"
            />
          </div>

          <div className="space-y-2">
            <label
              htmlFor="sync-password"
              className="text-sm font-medium"
            >
              Sync password
            </label>
            <input
              id="sync-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              autoFocus
              placeholder={
                accountExists ? "Enter your sync password" : "Choose a sync password"
              }
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
            />
          </div>

          {!accountExists && (
            <div className="space-y-2">
              <label
                htmlFor="confirm-password"
                className="text-sm font-medium"
              >
                Confirm password
              </label>
              <input
                id="confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                disabled={loading}
                placeholder="Confirm your sync password"
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
              />
            </div>
          )}

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}
        </CardContent>
        <CardFooter>
          <Button
            type="submit"
            size="lg"
            className="w-full"
            disabled={loading}
          >
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {accountExists ? "Signing in..." : "Creating account..."}
              </>
            ) : (
              <>
                <KeyRound className="mr-2 h-4 w-4" />
                {accountExists ? "Sign in" : "Create account"}
              </>
            )}
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
