"use client";

import {
  CircleAlert,
  ExternalLink,
  FileCheck2,
  LoaderCircle,
  RefreshCw,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuth } from "../lib/auth";
import { useTrips } from "../lib/trips";
import type {
  Trip,
  VisaChecklist,
  VisaChecklistResponse,
  VisaMaterial,
} from "../lib/types";

const MATERIAL_GROUPS = [
  { category: "required", label: "Required" },
  { category: "optional", label: "Optional" },
  { category: "conditional", label: "If applicable" },
] as const;

export default function VisaChecklistPanel({ trip }: { trip: Trip }) {
  const { user } = useAuth();
  const { getVisa } = useTrips();
  const [visa, setVisa] = useState<VisaChecklistResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const passportKey = user?.passport_countries.join(",") ?? "";
  const tripReady = Boolean(trip.destination && trip.start_date && trip.end_date);

  useEffect(() => {
    if (!passportKey || !tripReady) {
      setVisa(null);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    getVisa(trip.id)
      .then((checklist) => {
        if (!cancelled) {
          setVisa(checklist);
        }
      })
      .catch((requestError: unknown) => {
        if (!cancelled) {
          setVisa(null);
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Unable to load visa information",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    getVisa,
    passportKey,
    trip.destination,
    trip.end_date,
    trip.id,
    trip.start_date,
    tripReady,
  ]);

  return (
    <section aria-labelledby="visa-heading" className="mt-6 space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h3 id="visa-heading" className="text-sm font-semibold text-ink">
            Visa checklist
          </h3>
          <p className="mt-1 text-xs leading-5 text-gray-500">
            Grounded in current official sources for your saved passport.
          </p>
        </div>
        {visa && (
          <span className="text-xs text-gray-500">
            {visa.destination_country} · {visa.stay_days} days
          </span>
        )}
      </div>

      {!passportKey ? (
        <div className="panel p-4">
          <p className="text-sm font-semibold text-ink">Add your passport first</p>
          <p className="mt-1 text-sm leading-6 text-gray-600">
            Visa requirements depend on the passport you travel with.
          </p>
          <Link className="button-secondary mt-3 inline-flex" href="/settings">
            Open Settings
          </Link>
        </div>
      ) : !tripReady ? (
        <div className="panel p-4 text-sm leading-6 text-gray-500">
          Create a plan with a destination and travel dates to see visa information.
        </div>
      ) : loading ? (
        <div
          className="panel flex items-center gap-2 p-4 text-sm text-gray-500"
          role="status"
        >
          <LoaderCircle aria-hidden="true" className="animate-spin" size={15} />
          Checking official visa sources…
        </div>
      ) : error ? (
        <div className="notice-error">{error}</div>
      ) : visa ? (
        visa.checklists.map((checklist) => (
          <ChecklistCard key={checklist.passport_country} checklist={checklist} />
        ))
      ) : null}
    </section>
  );
}

function ChecklistCard({ checklist }: { checklist: VisaChecklist }) {
  return (
    <article className="panel overflow-hidden">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-brand">
            Passport {checklist.passport_country}
          </p>
          <h4 className="mt-1 text-base font-semibold text-ink">
            {checklist.destination_country}
          </h4>
        </div>
        <VisaRequirement value={checklist.visa_required} />
      </header>

      <div className="space-y-5 p-4">
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <Fact label="Visa type" value={checklist.visa_type} />
          <Fact label="Allowed stay" value={checklist.allowed_stay} />
          <Fact label="Processing time" value={checklist.processing_time} />
          <Fact label="Fees" value={checklist.fees} />
        </dl>

        {checklist.notes && (
          <p className="rounded-lg bg-brand/5 p-3 text-sm leading-6 text-gray-700">
            {checklist.notes}
          </p>
        )}

        <div>
          <h5 className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink">
            <FileCheck2 aria-hidden="true" size={15} />
            Application materials
          </h5>
          {checklist.materials.length > 0 ? (
            <div className="mt-3 space-y-4">
              {MATERIAL_GROUPS.map(({ category, label }) => {
                const materials = checklist.materials.filter(
                  (material) => material.category === category,
                );
                return materials.length > 0 ? (
                  <MaterialGroup key={category} label={label} materials={materials} />
                ) : null;
              })}
            </div>
          ) : (
            <UnknownMessage />
          )}
        </div>

        <div>
          <h5 className="text-sm font-semibold text-ink">Application steps</h5>
          {checklist.steps.length > 0 ? (
            <ol className="mt-3 space-y-3">
              {checklist.steps.map((step) => (
                <li
                  key={`${step.order}-${step.title}`}
                  className="flex gap-3 text-sm"
                >
                  <span className="grid size-6 shrink-0 place-items-center rounded-full bg-brand/10 text-xs font-semibold text-brand">
                    {step.order}
                  </span>
                  <div>
                    <p className="font-medium text-ink">{step.title}</p>
                    <p className="mt-0.5 leading-6 text-gray-600">
                      {step.description}
                    </p>
                    <SourceLink href={step.source_url} label="Official source" />
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <UnknownMessage />
          )}
        </div>

        <LinkList title="Official links" links={checklist.official_links} />

        <div>
          <h5 className="text-sm font-semibold text-ink">Sources</h5>
          {checklist.sources.length > 0 ? (
            <ul className="mt-2 space-y-2 text-sm">
              {checklist.sources.map((source) => (
                <li key={source.url}>
                  <SourceLink href={source.url} label={source.title} />
                  {source.published_date && (
                    <span className="ml-2 text-xs text-gray-400">
                      {source.published_date}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <UnknownMessage />
          )}
        </div>

        <p className="flex items-start gap-2 border-t border-line pt-4 text-xs leading-5 text-gray-500">
          <CircleAlert aria-hidden="true" className="mt-0.5 shrink-0" size={14} />
          {checklist.disclaimer}
        </p>
      </div>
    </article>
  );
}

function Fact({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-gray-400">
        {label}
      </dt>
      <dd className={`mt-1 ${value ? "text-ink" : "italic text-gray-400"}`}>
        {value ?? "unknown"}
      </dd>
    </div>
  );
}

function VisaRequirement({ value }: { value: boolean | null }) {
  const label =
    value === null
      ? "Visa requirement unknown"
      : value
        ? "Visa required"
        : "Visa not required";
  const tone =
    value === null
      ? "bg-gray-100 text-gray-600"
      : value
        ? "bg-amber-50 text-amber-700"
        : "bg-emerald-50 text-emerald-700";
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${tone}`}>
      {label}
    </span>
  );
}

function MaterialGroup({
  label,
  materials,
}: {
  label: string;
  materials: VisaMaterial[];
}) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
        {label}
      </p>
      <ul className="mt-2 space-y-2">
        {materials.map((material, index) => (
          <li
            key={`${material.name}-${index}`}
            className="rounded-lg bg-gray-50 p-3 text-sm"
          >
            <p className="font-medium text-ink">{material.name}</p>
            {material.details && (
              <p className="mt-1 leading-6 text-gray-600">{material.details}</p>
            )}
            <SourceLink href={material.source_url} label="Official source" />
          </li>
        ))}
      </ul>
    </div>
  );
}

function LinkList({
  title,
  links,
}: {
  title: string;
  links: { label: string; url: string }[];
}) {
  return (
    <div>
      <h5 className="text-sm font-semibold text-ink">{title}</h5>
      {links.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-3">
          {links.map((link) => (
            <SourceLink key={link.url} href={link.url} label={link.label} />
          ))}
        </div>
      ) : (
        <UnknownMessage />
      )}
    </div>
  );
}

function SourceLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline"
      href={href}
      target="_blank"
      rel="noreferrer"
    >
      {label}
      <ExternalLink aria-hidden="true" size={11} />
    </a>
  );
}

function UnknownMessage() {
  return (
    <p className="mt-2 inline-flex items-center gap-1.5 text-sm italic text-gray-400">
      <RefreshCw aria-hidden="true" size={12} />
      unknown
    </p>
  );
}
