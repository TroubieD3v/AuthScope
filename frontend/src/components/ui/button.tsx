import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

// Square controls, as in the design palette: Primary, Secondary, Inverted, Outlined (+ accent, danger, ghost).
const variants = cva(
  "inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-[3px] text-sm font-semibold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        default: "bg-primary text-on-primary hover:opacity-85",
        accent: "bg-accent-solid text-white hover:brightness-110 shadow-[0_10px_24px_-12px_rgb(0_133_66/0.7)]",
        secondary: "bg-panel2 text-ink hover:bg-high",
        inverted: "bg-inverse text-on-inverse hover:brightness-110",
        outline: "border border-mute/60 text-ink hover:border-ink",
        ghost: "text-mute hover:bg-panel2 hover:text-ink",
        danger: "bg-bad-solid text-white hover:brightness-110",
      },
      size: { default: "h-10 px-5", sm: "h-8 px-3 text-xs", icon: "size-9" },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof variants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(variants({ variant, size }), className)} {...props} />;
}
