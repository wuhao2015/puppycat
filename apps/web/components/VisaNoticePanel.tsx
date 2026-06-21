"use client";

import { ShieldCheck } from "lucide-react";
import type { VisaNotice } from "@/lib/types";

export default function VisaNoticePanel({ notices }: { notices: VisaNotice[] }) {
  if (!notices.length) return null;

  return (
    <div className="space-y-3 rounded-xl border border-brand/30 bg-brand/5 p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-brand">
        <ShieldCheck size={16} /> Visa reminders
      </div>
      {notices.map((n, i) => (
        <div key={i} className="rounded-lg border border-gray-200 bg-white p-3 text-sm">
          <div className="font-medium">
            {n.passport_country} → {n.destination_country}
          </div>
          <div className="mt-1 text-gray-700">
            {n.visa_required == null
              ? "Visa requirement unclear — confirm with official sources."
              : n.visa_required
                ? "Visa likely required."
                : "Likely visa-free for short stays."}
            {n.allowed_stay ? ` ${n.allowed_stay}.` : ""}
          </div>
          {n.summary && <p className="mt-1 text-gray-600">{n.summary}</p>}
          {n.key_documents.length > 0 && (
            <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-gray-600">
              {n.key_documents.map((d, j) => (
                <li key={j}>{d}</li>
              ))}
            </ul>
          )}
          {n.official_link && (
            <a
              href={n.official_link}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-block text-xs text-brand underline"
            >
              Official source
            </a>
          )}
        </div>
      ))}
      <p className="text-[11px] text-gray-400">
        Basic reminders only — always verify with the official embassy/consulate before you
        travel.
      </p>
    </div>
  );
}
