import { TicketDashboard } from "./components/TicketDashboard";
import { AuthGate } from "./components/AuthGate";

export default function App() {
  return (
    <AuthGate>
      {({ onLogout, user }) => <TicketDashboard onLogout={onLogout} user={user} />}
    </AuthGate>
  );
}
