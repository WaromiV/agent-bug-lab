import clsx from "clsx";
import { ButtonHTMLAttributes, forwardRef } from "react";

type Variant = "primary" | "ghost" | "danger" | "outline";
type Size = "sm" | "md";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const variantClasses: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-accent-hover disabled:bg-accent/40",
  ghost: "text-text-muted hover:text-text hover:bg-bg-hover",
  outline:
    "border border-border bg-bg-panel hover:bg-bg-hover text-text disabled:opacity-50",
  danger: "bg-red-600 text-white hover:bg-red-500 disabled:bg-red-600/40",
};

const sizeClasses: Record<Size, string> = {
  sm: "h-7 px-2 text-xs",
  md: "h-9 px-3 text-sm",
};

export const Button = forwardRef<HTMLButtonElement, Props>(
  ({ variant = "outline", size = "md", className, ...rest }, ref) => (
    <button
      ref={ref}
      {...rest}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition",
        "focus:outline-none focus:ring-2 focus:ring-accent/50",
        "disabled:cursor-not-allowed",
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
    />
  ),
);
Button.displayName = "Button";
