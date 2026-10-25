import { ShieldCheck } from "lucide-react";

export function Logo() {
  return (
    <div className="flex items-center gap-3">
      <div className="grid size-10 place-items-center rounded-[3px] bg-primary text-on-primary">
        <ShieldCheck className="size-5" />
      </div>
      <span className="font-display text-xl font-bold tracking-tight">AuthScope</span>
    </div>
  );
}
