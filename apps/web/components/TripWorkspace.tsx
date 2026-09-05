import { Compass, MapPinned, RefreshCw, Send } from "lucide-react";

export default function TripWorkspace() {
  return (
    <div className="grid h-full min-h-0 min-w-0 grid-cols-1 lg:grid-cols-2">
      <section
        aria-labelledby="chat-heading"
        className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden border-r border-line bg-white"
      >
        <header className="border-b border-line px-5 py-4">
          <h1 id="chat-heading" className="text-sm font-semibold text-ink">
            Trip chat
          </h1>
          <p className="mt-0.5 text-xs text-gray-500">
            Tell Puppycat what kind of journey you have in mind.
          </p>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          <div className="flex justify-start">
            <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-gray-100 px-4 py-2.5 text-sm leading-6 text-gray-800">
              Hi! I&apos;m Puppycat. Tell me where you&apos;d like to go and when,
              plus anything about your style of travel.
            </div>
          </div>

          <div className="flex justify-end">
            <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-brand px-4 py-2.5 text-sm leading-6 text-brand-fg">
              I&apos;d love a relaxed week in Kyoto with gardens, local food, and
              time to wander.
            </div>
          </div>

          <div className="flex justify-start">
            <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-gray-100 px-4 py-2.5 text-sm leading-6 text-gray-800">
              That sounds lovely. Add your dates and any must-see places, then
              Puppycat can turn the conversation into a Guide.
            </div>
          </div>
        </div>

        <div className="space-y-2 border-t border-line p-3">
          <div className="flex items-end gap-2">
            <textarea
              aria-label="Trip message"
              rows={1}
              placeholder="Tell Puppycat about your trip…"
              className="form-input max-h-32 flex-1 resize-none"
            />
            <button type="button" disabled className="button-primary px-3">
              <Send aria-hidden="true" size={15} />
              <span className="sr-only">Send message</span>
            </button>
          </div>
          <button type="button" disabled className="button-secondary w-full">
            <RefreshCw aria-hidden="true" size={15} />
            Create plan
          </button>
        </div>
      </section>

      <section
        aria-labelledby="guide-heading"
        className="h-full min-h-0 min-w-0 overflow-y-auto bg-page p-5"
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 id="guide-heading" className="text-xl font-semibold text-ink">
              Guide
            </h2>
            <p className="mt-0.5 text-sm text-gray-500">
              Your verified itinerary will appear here.
            </p>
          </div>
          <span className="rounded-full border border-brand/20 bg-brand/10 px-2.5 py-1 text-xs font-medium text-brand">
            Not created
          </span>
        </div>

        <div className="panel flex min-h-[calc(100%_-_4.5rem)] items-center justify-center border-dashed p-8 text-center">
          <div className="max-w-sm">
            <span className="mx-auto grid size-12 place-items-center rounded-xl bg-brand/10 text-brand">
              <MapPinned aria-hidden="true" size={22} />
            </span>
            <h3 className="mt-4 text-sm font-semibold text-ink">
              Your trip starts with a conversation
            </h3>
            <p className="mt-1.5 text-sm leading-6 text-gray-500">
              Share your destination, dates, and preferences in chat. Your daily
              itinerary, map, and travel notes will live in this Guide.
            </p>
            <div className="mt-4 inline-flex items-center gap-1.5 text-xs font-medium text-brand">
              <Compass aria-hidden="true" size={14} />
              Ready when you are
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
