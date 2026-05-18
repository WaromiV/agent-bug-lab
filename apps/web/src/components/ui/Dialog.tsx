import clsx from "clsx";
import { ReactNode } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  className?: string;
}

export function Dialog({ open, onClose, title, children, className }: Props) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className={clsx(
          "w-full max-w-lg rounded-lg border border-border bg-bg-panel shadow-2xl",
          className,
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {title ? (
          <div className="border-b border-border px-4 py-3 text-sm font-semibold">
            {title}
          </div>
        ) : null}
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}
