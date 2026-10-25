import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "./utils";

export type Theme = "dark" | "light";

/** Dark by default; an explicit choice is remembered. */
export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.classList.contains("dark") ? "dark" : "light");
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try { localStorage.setItem("authscope.theme", theme); } catch { /* private mode */ }
  }, [theme]);
  return [theme, setTheme];
}

export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
      className={cn("grid size-10 cursor-pointer place-items-center rounded-full text-mute transition-colors hover:bg-panel2 hover:text-ink", className)}
    >
      {theme === "dark" ? <Sun className="size-[18px]" /> : <Moon className="size-[18px]" />}
    </button>
  );
}
