"use client";

import { useRef, useState } from "react";
import { Send } from "lucide-react";
import { streamChat } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

const GREETING: ChatMessage = {
  role: "assistant",
  content:
    "Hi! I'm Puppycat. Ask me about a destination and I'll ground my answer in current " +
    "venue data and recent web findings — including whether places are open or disrupted.",
};

export default function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  function scrollToBottom() {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    });
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;

    const next: ChatMessage[] = [...messages, { role: "user", content: text }];
    setMessages([...next, { role: "assistant", content: "" }]);
    setInput("");
    setBusy(true);
    scrollToBottom();

    try {
      await streamChat(
        next.map((m) => ({ role: m.role, content: m.content })),
        (chunk) => {
          setMessages((prev) => {
            const copy = [...prev];
            copy[copy.length - 1] = {
              role: "assistant",
              content: copy[copy.length - 1].content + chunk,
            };
            return copy;
          });
          scrollToBottom();
        },
      );
    } catch (err) {
      setMessages((prev) => {
        const copy = [...prev];
        copy[copy.length - 1] = {
          role: "assistant",
          content: `Sorry, something went wrong: ${(err as Error).message}`,
        };
        return copy;
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-[70vh] flex-col rounded-xl border border-gray-200 bg-white">
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.map((m, i) => (
          <div
            key={i}
            className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}
          >
            <div
              className={cn(
                "max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm",
                m.role === "user"
                  ? "bg-brand text-brand-fg"
                  : "bg-gray-100 text-gray-800",
              )}
            >
              {m.content || (busy && i === messages.length - 1 ? "…" : "")}
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2 border-t border-gray-200 p-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask about a place, e.g. 'Is the Louvre worth it next Monday?'"
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-brand"
          disabled={busy}
        />
        <button
          onClick={send}
          disabled={busy}
          className="flex items-center gap-1 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-fg disabled:opacity-50"
        >
          <Send size={16} /> Send
        </button>
      </div>
    </div>
  );
}
