import { Moon, Sun, Monitor } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useTheme } from "@/components/theme-provider"

const CYCLE: Array<"system" | "light" | "dark"> = ["system", "light", "dark"]
const LABELS = { system: "System", light: "Light", dark: "Dark" }

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()

  function cycle() {
    const i = CYCLE.indexOf(theme)
    setTheme(CYCLE[(i + 1) % CYCLE.length])
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={cycle}
      aria-label={`Theme: ${LABELS[theme]}. Click to change.`}
      title={LABELS[theme]}
    >
      {theme === "light" && <Sun className="h-4 w-4" />}
      {theme === "dark" && <Moon className="h-4 w-4" />}
      {theme === "system" && <Monitor className="h-4 w-4" />}
    </Button>
  )
}
