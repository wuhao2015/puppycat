import { AlertTriangle, Info, Ban } from "lucide-react";
import type { Warning } from "@/lib/types";
import { cn } from "@/lib/utils";

const STYLES: Record<Warning["severity"], string> = {
  info: "bg-blue-50 text-blue-700 border-blue-200",
  caution: "bg-amber-50 text-amber-800 border-amber-200",
  blocker: "bg-red-50 text-red-700 border-red-200",
};

const ICONS = {
  info: Info,
  caution: AlertTriangle,
  blocker: Ban,
};

export default function WarningBadge({ warning }: { warning: Warning }) {
  const Icon = ICONS[warning.severity];
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-md border px-2.5 py-1.5 text-xs",
        STYLES[warning.severity],
      )}
    >
      <Icon size={14} className="mt-0.5 shrink-0" />
      <span>
        {warning.message}
        {warning.source ? (
          <a
            href={warning.source}
            target="_blank"
            rel="noreferrer"
            className="ml-1 underline opacity-70 hover:opacity-100"
          >
            source
          </a>
        ) : null}
      </span>
    </div>
  );
}
