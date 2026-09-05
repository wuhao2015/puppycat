import type { ReactNode } from "react";

import Sidebar from "./Sidebar";

type AppShellProps = {
  activePage: "workspace" | "settings";
  children: ReactNode;
};

export default function AppShell({ activePage, children }: AppShellProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-page">
      <Sidebar activePage={activePage} />
      <main className="min-h-0 min-w-0 flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
