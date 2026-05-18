import clsx from "clsx";
import { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes, forwardRef } from "react";

const fieldClasses =
  "block w-full rounded-md border border-border bg-bg-subtle px-2.5 py-1.5 text-sm text-text placeholder:text-text-subtle focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-50";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...rest }, ref) => (
    <input ref={ref} {...rest} className={clsx(fieldClasses, className)} />
  ),
);
Input.displayName = "Input";

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, rows = 4, ...rest }, ref) => (
  <textarea
    ref={ref}
    rows={rows}
    {...rest}
    className={clsx(fieldClasses, "font-mono", className)}
  />
));
Textarea.displayName = "Textarea";

export function Label({
  children,
  className,
  htmlFor,
}: {
  children: ReactNode;
  className?: string;
  htmlFor?: string;
}) {
  return (
    <label
      htmlFor={htmlFor}
      className={clsx(
        "mb-1 block text-xs font-medium uppercase tracking-wide text-text-muted",
        className,
      )}
    >
      {children}
    </label>
  );
}
