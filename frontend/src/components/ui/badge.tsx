import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const tones = {
  bad: "border-bad/40 bg-bad/12 text-bad",
  warn: "border-warn/40 bg-warn/12 text-warn",
  ok: "border-ok/40 bg-ok/10 text-ok",
  info: "border-line text-info",
  mute: "border-line text-mute",
  accent: "border-accent/40 text-accent",
  ink: "border-line text-ink",
};

/** Small flat label. */
export function Badge({ tone = "mute", className, ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof tones }) {
  return (
    <span
      className={cn("inline-flex items-center gap-1 whitespace-nowrap border px-1.5 text-[11px] font-medium leading-[18px]", tones[tone], className)}
      {...props}
    />
  );
}

export const Method = ({ m }: { m: string }) => (
  <span className={cn("inline-block w-14 font-mono text-[11.5px]", m === "DELETE" ? "text-bad" : "text-mute")}>{m}</span>
);
