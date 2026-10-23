import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const variants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:pointer-events-none disabled:opacity-50 cursor-pointer",
  {
    variants: {
      variant: {
        default: "bg-accent text-[#04201c] hover:bg-accent/85",
        secondary: "bg-panel2 text-ink border border-line hover:bg-[#1b2735]",
        ghost: "text-mute hover:text-ink hover:bg-panel2",
        danger: "bg-bad/15 text-bad border border-bad/30 hover:bg-bad/25",
      },
      size: { default: "h-9 px-4", sm: "h-7 px-2.5 text-xs", icon: "h-8 w-8" },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof variants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(variants({ variant, size }), className)} {...props} />;
}
