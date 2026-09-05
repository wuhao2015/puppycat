import AppShell from "../components/AppShell";
import TripWorkspace from "../components/TripWorkspace";

export default function HomePage() {
  return (
    <AppShell activePage="workspace">
      <TripWorkspace />
    </AppShell>
  );
}
