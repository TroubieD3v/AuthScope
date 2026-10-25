import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const tones = {
  bad: "bg-bad/14 text-bad",
  warn: "bg-warn/15 text-warn",
  ok: "bg-accent/14 text-accent",
  info: "bg-info/14 text-info",
  mute: "bg-panel2 text-mute",
  accent: "bg-accent/14 text-accent",
  ink: "bg-primary text-on-primary",
};

/** Rounded pill with an uppercase label ("OPTIMIZED", "WEEKLY INSIGHT"). */
export function Badge({ tone = "mute", className, ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof tones }) {
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[10.5px] font-bold uppercase tracking-[0.08em]", tones[tone], className)}
      {...props}
    />
  );
}

const methodColors: Record<string, string> = {
  GET: "text-info", POST: "text-accent", PUT: "text-warn", PATCH: "text-warn", DELETE: "text-bad",
};
export const Method = ({ m }: { m: string }) => (
  <span className={cn("inline-block w-14 font-mono text-xs font-bold", methodColors[m] ?? "text-mute")}>{m}</span>
);
