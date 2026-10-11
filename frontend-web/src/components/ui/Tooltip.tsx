// Jednoduchý vlastní tooltip (bez knihoven): zobrazí content při hoveru
// nad obaleným prvkem (např. čtvereček kroku v dispečinku).
import { useState } from "react";
import type { ReactNode } from "react";

interface TooltipProps {
  content: ReactNode;
  testId?: string;
  children: ReactNode;
}

export function Tooltip({ content, testId, children }: TooltipProps) {
  const [open, setOpen] = useState(false);
  return (
    <span
      data-testid={testId}
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      {children}
      {open && (
        <span
          role="tooltip"
          className="absolute bottom-full left-1/2 z-20 mb-1 -translate-x-1/2 whitespace-nowrap rounded bg-slate-900 px-2 py-1 text-xs text-white shadow-lg"
        >
          {content}
        </span>
      )}
    </span>
  );
}
