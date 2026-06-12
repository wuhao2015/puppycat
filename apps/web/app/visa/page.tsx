"use client";

import { useState } from "react";
import { Download, FileText, ShieldCheck } from "lucide-react";
import { downloadPdf, getVisaChecklist } from "@/lib/api";
import type { VisaChecklist, VisaRequest } from "@/lib/types";

export default function VisaPage() {
  const [passport, setPassport] = useState("");
  const [destination, setDestination] = useState("");
  const [purpose, setPurpose] = useState("tourism");
  const [duration, setDuration] = useState(14);
  const [applicant, setApplicant] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const [checklist, setChecklist] = useState<VisaChecklist | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const req: VisaRequest = {
      passport_country: passport,
      destination_country: destination,
      purpose,
      duration_days: duration,
    };
    try {
      setChecklist(await getVisaChecklist(req));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const field =
    "rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-brand";

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr]">
      <div className="space-y-3">
        <div>
          <h1 className="text-2xl font-semibold">Visa assistant</h1>
          <p className="text-sm text-gray-600">
            Requirements, fees, and a document checklist grounded in current sources.
          </p>
        </div>
        <form onSubmit={submit} className="space-y-3 rounded-xl border border-gray-200 bg-white p-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-gray-600">Passport country (name or ISO code)</span>
            <input required value={passport} onChange={(e) => setPassport(e.target.value)} placeholder="US" className={field} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-gray-600">Destination country</span>
            <input required value={destination} onChange={(e) => setDestination(e.target.value)} placeholder="JP" className={field} />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-gray-600">Purpose</span>
              <input value={purpose} onChange={(e) => setPurpose(e.target.value)} className={field} />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-gray-600">Stay (days)</span>
              <input type="number" min={1} value={duration} onChange={(e) => setDuration(Number(e.target.value))} className={field} />
            </label>
          </div>

          <div className="border-t border-gray-100 pt-3">
            <p className="mb-2 text-xs font-medium text-gray-500">For the cover letter (optional)</p>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-gray-600">Applicant full name</span>
              <input value={applicant} onChange={(e) => setApplicant(e.target.value)} className={field} />
            </label>
            <div className="mt-2 grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-gray-600">Travel start</span>
                <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className={field} />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-gray-600">Travel end</span>
                <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className={field} />
              </label>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2.5 text-sm font-medium text-brand-fg disabled:opacity-50"
          >
            <ShieldCheck size={16} />
            {loading ? "Checking…" : "Check visa requirements"}
          </button>
        </form>
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
        )}
      </div>

      <div>
        {checklist ? (
          <VisaResult
            checklist={checklist}
            applicant={applicant}
            startDate={startDate}
            endDate={endDate}
            purpose={purpose}
          />
        ) : (
          <div className="flex h-full min-h-64 items-center justify-center rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500">
            Your visa checklist will appear here.
          </div>
        )}
      </div>
    </div>
  );
}

function VisaResult({
  checklist,
  applicant,
  startDate,
  endDate,
  purpose,
}: {
  checklist: VisaChecklist;
  applicant: string;
  startDate: string;
  endDate: string;
  purpose: string;
}) {
  async function downloadChecklist() {
    await downloadPdf("visa", checklist, "visa-checklist.pdf");
  }

  async function downloadCoverLetter() {
    await downloadPdf(
      "cover-letter",
      {
        applicant_name: applicant || "Applicant",
        passport_country: checklist.passport_country,
        destination_country: checklist.destination_country,
        purpose,
        start_date: startDate,
        end_date: endDate,
      },
      "visa-cover-letter.pdf",
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-semibold">
          {checklist.passport_country} → {checklist.destination_country}
        </h2>
        <div className="flex gap-2">
          <button onClick={downloadChecklist} className="flex items-center gap-1 rounded-lg bg-brand px-3 py-2 text-sm font-medium text-brand-fg">
            <Download size={15} /> Checklist PDF
          </button>
          <button onClick={downloadCoverLetter} className="flex items-center gap-1 rounded-lg border border-brand/40 px-3 py-2 text-sm font-medium text-brand">
            <FileText size={15} /> Cover letter
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 rounded-xl border border-gray-200 bg-white p-4 text-sm sm:grid-cols-3">
        <Fact label="Visa required" value={checklist.visa_required == null ? "Unknown" : checklist.visa_required ? "Yes" : "No"} />
        {checklist.visa_type && <Fact label="Type" value={checklist.visa_type} />}
        {checklist.allowed_stay && <Fact label="Allowed stay" value={checklist.allowed_stay} />}
        {checklist.processing_time && <Fact label="Processing" value={checklist.processing_time} />}
        {checklist.fees && <Fact label="Fees" value={checklist.fees} />}
      </div>

      {checklist.documents.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <h3 className="mb-2 font-semibold">Documents</h3>
          <ul className="space-y-1 text-sm">
            {checklist.documents.map((d, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className={d.required ? "text-brand" : "text-gray-400"}>•</span>
                <span>
                  {d.name}
                  {!d.required && <span className="text-xs text-gray-400"> (optional)</span>}
                  {d.detail && <span className="block text-xs text-gray-500">{d.detail}</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {checklist.steps.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <h3 className="mb-2 font-semibold">Steps</h3>
          <ol className="list-decimal space-y-1 pl-5 text-sm">
            {checklist.steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </div>
      )}

      {checklist.official_links.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <h3 className="mb-2 font-semibold">Official links</h3>
          <ul className="space-y-1 text-sm">
            {checklist.official_links.map((l, i) => (
              <li key={i}>
                <a href={l} target="_blank" rel="noreferrer" className="text-brand underline">
                  {l}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-xs text-gray-400">{checklist.disclaimer}</p>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-gray-400">{label}</p>
      <p className="font-medium">{value}</p>
    </div>
  );
}
