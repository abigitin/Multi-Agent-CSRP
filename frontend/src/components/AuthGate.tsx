import { CheckCircle2, LogIn, ShieldCheck, Trash2, UserCheck } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { api, getAccessToken, setAccessToken } from "../api";
import type { AppUser } from "../types/api";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: { credential: string }) => void;
          }) => void;
          renderButton: (element: HTMLElement, options: Record<string, string | number>) => void;
        };
      };
    };
  }
}

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
const DEV_ADMIN_EMAIL = "abir27534@gmail.com";

export function AuthGate({
  children,
}: {
  children: (props: { user: AppUser; onLogout: () => void }) => ReactNode;
}) {
  const [user, setUser] = useState<AppUser | null>(null);
  const [users, setUsers] = useState<AppUser[]>([]);
  const [loading, setLoading] = useState(Boolean(getAccessToken()));
  const [error, setError] = useState("");
  const [devEmail, setDevEmail] = useState(DEV_ADMIN_EMAIL);

  useEffect(() => {
    if (!getAccessToken()) return;
    api
      .me()
      .then(setUser)
      .catch(() => setAccessToken(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || !window.google || user) return;
    const target = document.getElementById("googleSignIn");
    if (!target) return;
    window.google.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
      callback: (response) => signIn(response.credential),
    });
    target.innerHTML = "";
    window.google.accounts.id.renderButton(target, {
      theme: "outline",
      size: "large",
      width: 280,
    });
  }, [user]);

  useEffect(() => {
    if (user?.role !== "admin" || user.status !== "approved") return;
    loadUsers();
  }, [user?.id, user?.role, user?.status]);

  async function signIn(credential: string) {
    setError("");
    setLoading(true);
    try {
      const result = await api.googleAuth(credential);
      setAccessToken(result.access_token);
      setUser(result.user);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoading(false);
    }
  }

  async function devSignIn() {
    const email = devEmail.trim().toLowerCase();
    if (!email) return;
    await signIn(
      JSON.stringify({
        sub: `dev:${email}`,
        email,
        name: email === DEV_ADMIN_EMAIL ? "Admin" : email.split("@")[0],
      }),
    );
  }

  async function logout() {
    try {
      await api.logout();
    } catch {
      // Token removal is local; logout remains effective even if the network request fails.
    }
    setAccessToken(null);
    setUser(null);
    setUsers([]);
  }

  async function loadUsers() {
    try {
      setUsers(await api.adminUsers());
    } catch (err) {
      setError(formatError(err));
    }
  }

  async function approve(id: number) {
    await api.approveUser(id);
    await loadUsers();
  }

  async function remove(id: number) {
    await api.deleteUser(id);
    await loadUsers();
  }

  if (loading) {
    return <AuthShell title="Checking access" subtitle="Validating your session." />;
  }

  if (!user) {
    return (
      <AuthShell title="Sign in" subtitle="Use Google to request access to the support console.">
        {GOOGLE_CLIENT_ID ? <div id="googleSignIn" /> : (
          <div className="devLogin">
            <input value={devEmail} onChange={(event) => setDevEmail(event.target.value)} />
            <button onClick={devSignIn}>
              <LogIn size={16} /> Dev Sign In
            </button>
          </div>
        )}
        {error && <p className="authError">{error}</p>}
      </AuthShell>
    );
  }

  if (user.status !== "approved") {
    return (
      <AuthShell title="Approval pending" subtitle="An admin must approve your account before API access is enabled.">
        <div className="pendingUser">
          <strong>{user.email}</strong>
          <span>Status: {user.status}</span>
        </div>
        <button className="secondaryButton" onClick={logout}>Sign out</button>
      </AuthShell>
    );
  }

  return (
    <>
      {children({ user, onLogout: logout })}
      {user.role === "admin" && (
        <AdminPanel users={users} onApprove={approve} onDelete={remove} onRefresh={loadUsers} />
      )}
    </>
  );
}

function AuthShell({
  children,
  subtitle,
  title,
}: {
  children?: ReactNode;
  subtitle: string;
  title: string;
}) {
  return (
    <main className="authShell">
      <section className="authCard">
        <div className="brandMark">
          <ShieldCheck size={21} />
        </div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
        {children}
      </section>
    </main>
  );
}

function AdminPanel({
  onApprove,
  onDelete,
  onRefresh,
  users,
}: {
  onApprove: (id: number) => void;
  onDelete: (id: number) => void;
  onRefresh: () => void;
  users: AppUser[];
}) {
  const [open, setOpen] = useState(false);
  const pendingCount = users.filter((item) => item.status === "pending").length;

  return (
    <div className="adminDock">
      {open && (
        <section className="adminPanel">
          <div className="adminHeader">
            <div>
              <strong>User approvals</strong>
              <span>{pendingCount} pending</span>
            </div>
            <button className="secondaryButton" onClick={onRefresh}>Refresh</button>
          </div>
          <div className="adminUserList">
            {users.map((item) => (
              <article className="adminUser" key={item.id}>
                <div>
                  <strong>{item.email}</strong>
                  <span>{item.role} / {item.status}</span>
                </div>
                <div className="adminActions">
                  <button onClick={() => onApprove(item.id)} disabled={item.status === "approved"}>
                    <UserCheck size={15} /> Approve
                  </button>
                  <button className="dangerButton" onClick={() => onDelete(item.id)} disabled={item.role === "admin"}>
                    <Trash2 size={15} /> Delete
                  </button>
                </div>
              </article>
            ))}
            {!users.length && <p className="muted">No users found.</p>}
          </div>
        </section>
      )}
      <button className="adminToggle" onClick={() => setOpen((value) => !value)}>
        <CheckCircle2 size={18} /> Users
      </button>
    </div>
  );
}

function formatError(err: unknown) {
  if (!(err instanceof Error)) return "Request failed";
  try {
    const parsed = JSON.parse(err.message);
    return typeof parsed.detail === "string" ? parsed.detail : err.message;
  } catch {
    return err.message;
  }
}
