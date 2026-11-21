import { ShieldCheck } from "lucide-react";

export function Logo() {
  return (
    <div className="flex items-center gap-2">
      <ShieldCheck className="size-4 text-accent" />
      <span className="text-[13px] font-semibold">AuthScope</span>
    </div>
  );
}
