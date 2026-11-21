import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

// Compact desktop controls: one filled primary action, bordered secondary ones.
const variants = cva(
  "inline-flex cursor-pointer items-center justify-center gap-1.5 whitespace-nowrap border text-[12.5px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        default: "border-accent-solid bg-accent-solid text-white hover:brightness-110",
        accent: "border-accent-solid bg-accent-solid text-white hover:brightness-110",
        secondary: "border-line bg-panel text-ink hover:border-dim",
        inverted: "border-line bg-panel text-ink hover:border-dim",
        outline: "border-line text-ink hover:border-dim",
        ghost: "border-transparent text-mute hover:bg-panel2 hover:text-ink",
        danger: "border-bad-solid bg-bad-solid text-white hover:brightness-110",
      },
      size: { default: "h-8 px-3", sm: "h-7 px-2.5 text-xs", icon: "size-7" },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof variants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(variants({ variant, size }), className)} {...props} />;
}
