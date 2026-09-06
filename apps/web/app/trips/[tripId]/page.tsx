import AppShell from "../../../components/AppShell";
import TripWorkspace from "../../../components/TripWorkspace";

type TripPageProps = {
  params: Promise<{ tripId: string }>;
};

export default async function TripPage({ params }: TripPageProps) {
  const { tripId } = await params;

  return (
    <AppShell activePage="workspace">
      <TripWorkspace tripId={tripId} />
    </AppShell>
  );
}
