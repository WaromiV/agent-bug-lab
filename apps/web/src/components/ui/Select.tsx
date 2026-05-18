import clsx from "clsx";
import { SelectHTMLAttributes, forwardRef } from "react";

interface Props extends SelectHTMLAttributes<HTMLSelectElement> {
  options: { label: string; value: string }[];
}

export const Select = forwardRef<HTMLSelectElement, Props>(
  ({ className, options, ...rest }, ref) => (
    <select
      ref={ref}
      {...rest}
      className={clsx(
        "block w-full rounded-md border border-border bg-bg-subtle px-2.5 py-1.5 text-sm text-text focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent",
        className,
      )}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
);
Select.displayName = "Select";
