import {
  AlertTriangle,
  BookOpenText,
  Bot,
  CheckCircle2,
  CircleDot,
  Clock3,
  FileCheck2,
  Gauge,
  MessageCircle,
  RefreshCcw,
  Save,
  Send,
  ServerCog,
  LogOut,
  ShieldCheck,
  Sparkles,
  Workflow,
  X,
  XCircle,
} from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api";
import type {
  ChatMessage,
  KnowledgeSyncResult,
  SyncResult,
  Ticket,
  TicketDetail,
  TicketRun,
  AppUser,
} from "../types/api";

export function TicketDashboard({
  onLogout,
  user,
}: {
  onLogout: () => void;
  user: AppUser;
}) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [activeRuntimeRunId, setActiveRuntimeRunId] = useState<number | null>(null);
  const [draftText, setDraftText] = useState("");
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [knowledgeResult, setKnowledgeResult] = useState<KnowledgeSyncResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selectedTicket = useMemo(
    () => tickets.find((ticket) => ticket.id === selectedId) ?? null,
    [selectedId, tickets],
  );
  const selectedRun = useMemo(() => {
    if (!detail?.runs.length || !selectedRunId) return null;
    return detail.runs.find((run) => run.id === selectedRunId) ?? null;
  }, [detail, selectedRunId]);
  const activeRun =
    selectedRun && selectedRun.id === activeRuntimeRunId ? selectedRun : null;
  const selectedDraft = activeRun?.drafts[0] ?? null;

  async function loadAll(preferredTicketId?: string, preferredRunId?: number | null) {
    const rows = await api.tickets();
    setTickets(rows);
    const nextId =
      preferredTicketId && rows.some((ticket) => ticket.id === preferredTicketId)
        ? preferredTicketId
        : rows[0]?.id ?? "";
    setSelectedId(nextId);
    if (nextId) await loadDetail(nextId, preferredRunId);
  }

  async function loadDetail(id: string, preferredRunId?: number | null) {
    const nextDetail = await api.ticket(id);
    setDetail(nextDetail);
    const nextRun =
      preferredRunId != null
        ? nextDetail.runs.find((run) => run.id === preferredRunId) ?? null
        : null;
    setSelectedRunId(nextRun?.id ?? null);
    setDraftText(nextRun?.drafts[0]?.content ?? "");
  }

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  function selectTicket(id: string) {
    setSelectedId(id);
    setSelectedRunId(null);
    setActiveRuntimeRunId(null);
    setDraftText("");
  }

  useEffect(() => {
    act(() => loadAll());
  }, []);

  useEffect(() => {
    if (selectedId) {
      act(() => loadDetail(selectedId, activeRuntimeRunId));
    }
  }, [selectedId]);

  useEffect(() => {
    setDraftText(selectedDraft?.content ?? "");
  }, [selectedDraft?.id]);

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brandMark">
          <Sparkles size={21} />
        </div>
        <div>
          <strong>AgenticAI SupportOps</strong>
          <span>Human-reviewed incident resolution console</span>
        </div>
        <div className="userMenu">
          <span>{user.email}</span>
          <button className="secondaryButton" onClick={onLogout}>
            <LogOut size={16} /> Sign out
          </button>
        </div>
      </header>

      <section className="heroBand">
        <div className="heroCopy">
          <p className="eyebrow">Runtime agent processing</p>
          <h1>Resolve selected incidents only when you run the agents.</h1>
          <p>
            Sync incidents and source documents, run the workflow on demand, review the
            generated draft, then approve before any customer email is sent.
          </p>
        </div>
        <div className="heroActions">
          <button className="secondaryButton" onClick={() => act(() => loadAll(selectedId, activeRuntimeRunId))} disabled={busy}>
            <RefreshCcw size={16} /> Refresh
          </button>
          <button
            onClick={() =>
              act(async () => {
                const result = await api.syncKnowledge();
                setKnowledgeResult(result);
                await loadAll(selectedId, activeRuntimeRunId);
              })
            }
            disabled={busy}
          >
            <BookOpenText size={16} /> Sync Knowledge
          </button>
          <button
            onClick={() =>
              act(async () => {
                const result = await api.sync();
                setSyncResult(result);
                await loadAll(selectedId, activeRuntimeRunId);
              })
            }
            disabled={busy}
          >
            <ServerCog size={16} /> Sync ServiceNow
          </button>
        </div>
      </section>

      {error && (
        <div className="alert error">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </div>
      )}
      {syncResult && !error && (
        <div className="alert success">
          <CheckCircle2 size={18} />
          <span>
            ServiceNow sync completed: {syncResult.total} total from {syncResult.source} in {syncResult.mode} mode.
          </span>
        </div>
      )}
      {knowledgeResult && !error && (
        <div className="alert success">
          <CheckCircle2 size={18} />
          <span>
            Knowledge sync completed: {knowledgeResult.documents} docs, {knowledgeResult.upserted} upserted, {knowledgeResult.mode} mode.
          </span>
        </div>
      )}

      <section className="workbench">
        <aside className="panel ticketPanel">
          <PanelHeader icon={<ServerCog size={18} />} title="Incidents" subtitle="Runtime selection" />
          <div className="ticketList">
            {tickets.map((ticket) => (
              <button
                className={`ticketRow ${ticket.id === selectedId ? "active" : ""}`}
                key={ticket.id}
                onClick={() => selectTicket(ticket.id)}
              >
                <div className="ticketRowTop">
                  <span>{ticket.short_description || ticket.id}</span>
                  <small>p{ticket.priority ?? "n/a"}</small>
                </div>
                <p>{ticket.customer_query || ticket.description || "No customer summary available."}</p>
                <div className="ticketMetaLine">
                  <StatusDot status={ticket.status} />
                  <small>{ticket.category ?? "General"} / {ticket.source_system}</small>
                </div>
              </button>
            ))}
            {!tickets.length && <EmptyState text="Sync ServiceNow incidents to begin." />}
          </div>
        </aside>

        <section className="panel detailPanel">
          {selectedTicket && detail ? (
            <>
              <div className="detailHeader">
                <div>
                  <p className="eyebrow">{selectedTicket.id}</p>
                  <h2>{selectedTicket.short_description || selectedTicket.customer_query}</h2>
                  <p>{selectedTicket.description || selectedTicket.customer_query}</p>
                </div>
                <button
                  onClick={() =>
                    act(async () => {
                      const result = await api.run(selectedTicket.id);
                      setActiveRuntimeRunId(result.run.id);
                      await loadAll(selectedTicket.id, result.run.id);
                    })
                  }
                  disabled={busy}
                >
                  <Workflow size={16} /> Run Agents
                </button>
              </div>

              <div className="metadataGrid">
                <Metric label="Category" value={selectedTicket.category ?? "n/a"} />
                <Metric label="Assignment" value={selectedTicket.assignment_group ?? "n/a"} />
                <Metric label="Caller" value={selectedTicket.caller ?? "n/a"} />
                <Metric label="Email" value={selectedTicket.caller_email ?? "missing"} />
                <Metric label="State" value={selectedTicket.state} />
                <Metric label="Runs" value={String(detail.runs.length)} />
                <Metric label="Status" value={selectedTicket.status} />
              </div>

              {detail.runs.length > 0 && (
                <div className="runStrip">
                  {detail.runs.map((run) => (
                    <button
                      className={`runChip ${run.id === activeRun?.id ? "active" : ""}`}
                      key={run.id}
                      onClick={() => {
                        setSelectedRunId(run.id);
                        if (run.id === activeRuntimeRunId) {
                          setDraftText(run.drafts[0]?.content ?? "");
                        }
                      }}
                      title={run.id === activeRuntimeRunId ? "Current runtime run" : "Historical run"}
                    >
                      <Clock3 size={14} />
                      Run #{run.id}
                      <span>{run.id === activeRuntimeRunId ? "current" : "history"}</span>
                    </button>
                  ))}
                </div>
              )}

              {activeRun ? (
                <RunWorkspace
                  busy={busy}
                  draftText={draftText}
                  onDraftChange={setDraftText}
                  onSaveDraft={() =>
                    act(async () => {
                      if (!selectedDraft) return;
                      await api.updateDraft(selectedDraft.id, draftText);
                      await loadAll(selectedTicket.id, activeRun.id);
                    })
                  }
                  onApprove={(statusValue) =>
                    act(async () => {
                      await api.approve(activeRun.id, selectedDraft?.id ?? null, statusValue);
                      await loadAll(selectedTicket.id, activeRun.id);
                    })
                  }
                  run={activeRun}
                />
              ) : (
                <EmptyState text="Run agents to generate the editable draft for this runtime session." />
              )}
            </>
          ) : (
            <EmptyState text="Select or sync an incident to open the workspace." />
          )}
        </section>
      </section>

      <IncidentChat selectedRunId={activeRun?.id ?? null} selectedTicket={selectedTicket} />
    </main>
  );
}

function IncidentChat({
  selectedRunId,
  selectedTicket,
}: {
  selectedRunId: number | null;
  selectedTicket: Ticket | null;
}) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setMessages([]);
    setQuestion("");
  }, [selectedTicket?.id]);

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = question.trim();
    if (!selectedTicket || !text || busy) return;
    const userMessage: ChatMessage = { role: "user", content: text };
    setMessages((items) => [...items, userMessage]);
    setQuestion("");
    setBusy(true);
    try {
      const result = await api.chat(selectedTicket.id, text, selectedRunId);
      const sourceLine = result.sources.length
        ? `\n\nSources: ${result.sources.slice(0, 3).map((source) => source.title).join(", ")}`
        : "";
      setMessages((items) => [
        ...items,
        {
          role: "assistant",
          content: `${result.answer}${sourceLine}`,
        },
      ]);
    } catch (err) {
      setMessages((items) => [
        ...items,
        { role: "assistant", content: formatError(err) },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chatDock">
      {open && (
        <section className="chatPanel" aria-label="Incident chatbot">
          <div className="chatHeader">
            <div>
              <strong>Incident Chat</strong>
              <span>{selectedTicket ? selectedTicket.id : "Select an incident"}</span>
            </div>
            <button className="iconButton" onClick={() => setOpen(false)} aria-label="Close chat">
              <X size={16} />
            </button>
          </div>
          <div className="chatMessages">
            {!messages.length && (
              <div className="chatHint">
                <Bot size={18} />
                <span>Ask about the incident, resolution, incident id, source evidence, or follow-up actions.</span>
              </div>
            )}
            {messages.map((message, index) => (
              <article className={`chatBubble ${message.role}`} key={`${message.role}-${index}`}>
                {message.content}
              </article>
            ))}
          </div>
          <form className="chatComposer" onSubmit={ask}>
            <input
              disabled={!selectedTicket || busy}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder={selectedTicket ? "Ask about this incident..." : "Select an incident first"}
              value={question}
            />
            <button disabled={!selectedTicket || busy || !question.trim()} aria-label="Send chat message">
              <Send size={16} />
            </button>
          </form>
        </section>
      )}
      <button className="chatToggle" onClick={() => setOpen((value) => !value)} aria-label="Toggle incident chat">
        <MessageCircle size={22} />
      </button>
    </div>
  );
}

function PanelHeader({
  icon,
  subtitle,
  title,
}: {
  icon: ReactNode;
  subtitle: string;
  title: string;
}) {
  return (
    <div className="panelHeader">
      <div className="panelIcon">{icon}</div>
      <div>
        <h3>{title}</h3>
        <span>{subtitle}</span>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <strong>{label}</strong>
      <span>{value}</span>
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  return <i className={`statusDot ${status.toLowerCase().replace(/\s+/g, "-")}`} aria-hidden="true" />;
}

function EmptyState({ compact = false, text }: { compact?: boolean; text: string }) {
  return (
    <div className={`empty ${compact ? "compact" : ""}`}>
      <CircleDot size={18} />
      <span>{text}</span>
    </div>
  );
}

function RunWorkspace({
  busy,
  draftText,
  onApprove,
  onDraftChange,
  onSaveDraft,
  run,
}: {
  busy: boolean;
  draftText: string;
  onApprove: (status: string) => void;
  onDraftChange: (value: string) => void;
  onSaveDraft: () => void;
  run: TicketRun;
}) {
  const [overlay, setOverlay] = useState<"citations" | "trace" | null>(null);

  return (
    <div className="workspace">
      <section className="summaryBand">
        <RunMetric icon={<ShieldCheck size={18} />} label="Guardrails" value={run.guardrail_status} />
        <RunMetric icon={<Workflow size={18} />} label="Next Step" value={run.next_step} />
        <RunMetric icon={<Gauge size={18} />} label="Confidence" value={`${Math.round(run.confidence_score * 100)}%`} />
        <RunMetric icon={<BookOpenText size={18} />} label="Evidence" value={`${run.citations.length} citations`} />
      </section>

      <section className="evidenceToolbar" aria-label="Evidence and trace controls">
        <button className="secondaryButton" onClick={() => setOverlay("citations")} disabled={!run.citations.length}>
          <BookOpenText size={16} /> Citations
        </button>
        <button className="secondaryButton" onClick={() => setOverlay("trace")} disabled={!run.traces.length}>
          <Workflow size={16} /> Agent Trace
        </button>
      </section>

      <section className="draftPanel">
        <div className="sectionTitle">
          <div>
            <h3>Editable AI Draft</h3>
            <span>Email is sent only after approval</span>
          </div>
          <div className="inlineActions">
            <button className="secondaryButton" onClick={onSaveDraft} disabled={busy || !run.drafts.length}>
              <Save size={16} /> Save
            </button>
            <button onClick={() => onApprove("approved")} disabled={busy || !run.drafts.length}>
              <CheckCircle2 size={16} /> Approve
            </button>
            <button className="dangerButton" onClick={() => onApprove("changes_requested")} disabled={busy}>
              <XCircle size={16} /> Changes
            </button>
          </div>
        </div>
        <textarea value={draftText} onChange={(event) => onDraftChange(event.target.value)} />
      </section>

      <section>
        <SectionHeading icon={<FileCheck2 size={17} />} title="Approval History" />
        <div className="approvalGrid">
          {run.approvals.map((approval) => (
            <article className="approval" key={approval.id}>
              <strong>{approval.status}</strong>
              <span>{approval.reviewer ?? "pending reviewer"}</span>
              <p>{approval.notes || "No notes."}</p>
            </article>
          ))}
        </div>
      </section>

      {overlay && (
        <InsightOverlay
          onClose={() => setOverlay(null)}
          run={run}
          type={overlay}
        />
      )}
    </div>
  );
}

function InsightOverlay({
  onClose,
  run,
  type,
}: {
  onClose: () => void;
  run: TicketRun;
  type: "citations" | "trace";
}) {
  const title = type === "citations" ? "Citations" : "Agent Trace";
  const icon = type === "citations" ? <BookOpenText size={18} /> : <Workflow size={18} />;

  return (
    <div className="overlayBackdrop" role="dialog" aria-modal="true" aria-label={title}>
      <section className="overlayCard">
        <div className="overlayHeader">
          <SectionHeading icon={icon} title={title} />
          <button className="iconButton" onClick={onClose} aria-label={`Close ${title}`}>
            <X size={16} />
          </button>
        </div>
        <div className="overlayList">
          {type === "citations" ? (
            run.citations.length ? (
              run.citations.map((citation) => (
                <article className="citation" key={citation.id}>
                  <div>
                    <strong>{citation.title}</strong>
                    <span>{Math.round(citation.score * 100)}%</span>
                  </div>
                  <small>{citation.source}</small>
                  <p>{citation.snippet}</p>
                </article>
              ))
            ) : (
              <p className="muted">No citations found.</p>
            )
          ) : run.traces.length ? (
            run.traces.map((trace) => (
              <article className="trace" key={trace.id}>
                <div>
                  <strong>{trace.agent_name}</strong>
                  <span>{Math.round(trace.confidence_score * 100)}%</span>
                </div>
                <p>{trace.thought_process}</p>
              </article>
            ))
          ) : (
            <p className="muted">No agent trace found.</p>
          )}
        </div>
      </section>
    </div>
  );
}

function RunMetric({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <article>
      <div className="summaryIcon">{icon}</div>
      <div>
        <strong>{label}</strong>
        <span>{value}</span>
      </div>
    </article>
  );
}

function SectionHeading({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="smallHeading">
      {icon}
      <h3>{title}</h3>
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
