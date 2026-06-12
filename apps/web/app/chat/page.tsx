import Chat from "@/components/Chat";

export default function ChatPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Travel chat</h1>
        <p className="text-sm text-gray-600">
          Grounded in live venue data and recent web findings, not just model memory.
        </p>
      </div>
      <Chat />
    </div>
  );
}
