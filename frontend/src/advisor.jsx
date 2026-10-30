import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  ShieldCheck, Mail, LogOut, Users, Eye, LockKeyhole, LoaderCircle,
  CircleAlert, Check, X, ArrowDownLeft, ArrowUpRight,
  ReceiptText, Leaf, KeyRound, UserRound, RefreshCw,
} from 'lucide-react';
import './style.css';

const API = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const money = (v) => new Intl.NumberFormat('en-IN', { style:'currency', currency:'INR', maximumFractionDigits:0 }).format(Number(v||0));
const moneyExact = (v) => new Intl.NumberFormat('en-IN', { style:'currency', currency:'INR', maximumFractionDigits:2 }).format(Number(v||0));
const dateText = (s) => s ? new Date(`${s}T12:00:00`).toLocaleDateString('en-IN', { day:'numeric', month:'short', year:'numeric' }) : '—';

async function api(path, { method='GET', token, body } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(`${API}${path}`, {
    method,
    headers,
    cache: 'no-store',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data;
  try { data = await res.json(); } catch { data = { detail: 'Unexpected response.' }; }
  if (!res.ok) {
    let msg;
    if (typeof data.detail === 'string') msg = data.detail;
    else if (Array.isArray(data.detail)) msg = data.detail.map(d => ((Array.isArray(d.loc) ? d.loc.join('.') : '') + ': ' + (d.msg || JSON.stringify(d)))).join('; ');
    else if (data.detail) msg = JSON.stringify(data.detail);
    else msg = `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

function AdvisorApp() {
  const [token, setToken] = useState(() => localStorage.getItem('finsight_token') || '');
  const [user, setUser] = useState(() => { try { return JSON.parse(localStorage.getItem('finsight_user') || 'null'); } catch { return null; } });
  const [authMode, setAuthMode] = useState('login');
  const [authForm, setAuthForm] = useState({ name:'', email:'', password:'' });
  const [authError, setAuthError] = useState('');
  const [invitations, setInvitations] = useState([]);
  const [clients, setClients] = useState([]);
  const [selectedEmail, setSelectedEmail] = useState('');
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null);

  const notify = (msg, type='success') => { setToast({ msg, type }); setTimeout(() => setToast(null), 3400); };

  async function refresh(t = token) {
    if (!t) return;
    try {
      setLoading(true);
      const [me, inv, cls] = await Promise.all([
        api('/api/auth/me', { token: t }),
        api('/api/advisor/invitations', { token: t }),
        api('/api/advisor/clients', { token: t }),
      ]);
      setUser(me); localStorage.setItem('finsight_user', JSON.stringify(me));
      setInvitations(inv); setClients(cls);
    } catch (e) {
      if (/session|sign in|credentials/i.test(e.message)) logout(); else notify(e.message, 'error');
    } finally { setLoading(false); }
  }

  function logout() {
    localStorage.removeItem('finsight_token'); localStorage.removeItem('finsight_user');
    setToken(''); setUser(null); setInvitations([]); setClients([]); setSummary(null); setSelectedEmail('');
  }

  useEffect(() => { if (token) refresh(token); }, [token]);

  useEffect(() => {
    if (!selectedEmail || !token) return;
    const onFocus = () => { refreshSummary(false); };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [selectedEmail, token]);

  async function submitAuth(e) {
    e.preventDefault(); setAuthError('');
    try {
      const res = await api(`/api/auth/${authMode === 'login' ? 'login' : 'register'}`, { method:'POST', body: authForm });
      localStorage.setItem('finsight_token', res.token);
      localStorage.setItem('finsight_user', JSON.stringify(res.user));
      setUser(res.user); setToken(res.token);
      notify(authMode === 'login' ? 'Welcome back.' : 'Advisor account created.');
    } catch (e) { setAuthError(e.message); }
  }

  async function acceptInvite(id) {
    try { setBusy(true); await api(`/api/advisor/invitations/${id}/accept`, { method:'POST', token }); await refresh(); notify('Invitation accepted.'); }
    catch (e) { notify(e.message, 'error'); } finally { setBusy(false); }
  }
  async function declineInvite(id) {
    try { setBusy(true); await api(`/api/advisor/invitations/${id}/decline`, { method:'POST', token }); await refresh(); notify('Invitation declined.'); }
    catch (e) { notify(e.message, 'error'); } finally { setBusy(false); }
  }
  async function loadSummary(email) {
    try { setBusy(true); setSelectedEmail(email); setSummary(null);
      const s = await api(`/api/advisor?client_email=${encodeURIComponent(email)}`, { token });
      setSummary(s);
    } catch (e) { notify(e.message, 'error'); setSelectedEmail(''); } finally { setBusy(false); }
  }
  async function refreshSummary(showToast = false) {
    if (!selectedEmail) return;
    try {
      setBusy(true);
      const s = await api(`/api/advisor?client_email=${encodeURIComponent(selectedEmail)}`, { token });
      setSummary(s);
      if (showToast) notify('Summary updated');
    } catch (e) {
      notify(e.message, 'error');
    } finally {
      setBusy(false);
    }
  }
  async function refreshAll() {
    try {
      setBusy(true);
      await refresh();
      if (selectedEmail) await refreshSummary(false);
      notify('Portal refreshed');
    } catch (e) {
      notify(e.message, 'error');
    } finally { setBusy(false); }
  }

  if (!token) return <PortalAuth mode={authMode} setMode={(m) => { setAuthMode(m); setAuthError(''); }} form={authForm} setForm={setAuthForm} submit={submitAuth} error={authError} />;

  return (
    <div className="portal-shell">
      <header className="portal-topbar">
        <div className="portal-brand"><div className="brand-mark"><Leaf size={22}/></div><div><div className="portal-brand-name">finsight<span>.</span></div><div className="portal-brand-caption">ADVISOR PORTAL</div></div></div>
        <div className="portal-user">
          <button className="icon-btn" onClick={refreshAll} disabled={busy} title="Refresh"><RefreshCw size={17} className={busy ? 'spin' : ''}/></button>
          <div className="portal-avatar">{(user?.name || 'A').slice(0,1).toUpperCase()}</div>
          <div className="portal-user-copy"><strong>{user?.name || 'Advisor'}</strong><span>{user?.email || ''}</span></div>
          <button className="icon-btn" onClick={logout} title="Sign out"><LogOut size={17}/></button>
        </div>
      </header>

      <main className="portal-main">
        {loading && !user ? <div className="portal-loading"><LoaderCircle className="spin"/><span>Loading…</span></div> : <>
          <section className="portal-hero">
            <div className="portal-hero-mark"><ShieldCheck size={26}/></div>
            <div>
              <span className="eyebrow">READ-ONLY ACCESS</span>
              <h1>Welcome, {(user?.name || 'Advisor').split(/\s+/)[0]}.</h1>
              <p>Review the financial summaries your clients have shared with you. You cannot edit their data.</p>
            </div>
          </section>

          {invitations.length > 0 && (
            <section className="portal-section">
              <h2 className="portal-section-title"><Mail size={18}/> Pending invitations ({invitations.length})</h2>
              <div className="portal-invite-list">
                {invitations.map(inv => (
                  <div key={inv.id} className="portal-invite-card">
                    <div className="portal-invite-info">
                      <div className="portal-invite-icon"><UserRound size={20}/></div>
                      <div><strong>{inv.client_name}</strong><span>{inv.client_email}</span></div>
                    </div>
                    <div className="portal-invite-actions">
                      <button className="btn btn-primary btn-small" onClick={() => acceptInvite(inv.id)} disabled={busy}><Check size={14}/> Accept</button>
                      <button className="btn btn-quiet btn-small" onClick={() => declineInvite(inv.id)} disabled={busy}><X size={14}/> Decline</button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="portal-section">
            <h2 className="portal-section-title"><Users size={18}/> Linked clients ({clients.length})</h2>
            {clients.length === 0 ? (
              <div className="portal-empty">
                <div className="portal-empty-icon"><Users size={26}/></div>
                <h3>No linked clients yet</h3>
                <p>When a client invites your email and you accept, their summary appears here.</p>
              </div>
            ) : (
              <div className="portal-client-grid">
                {clients.map(c => (
                  <button key={c.id} className={`portal-client-card ${selectedEmail === c.email ? 'active' : ''}`} onClick={() => loadSummary(c.email)}>
                    <div className="portal-client-avatar">{(c.name || 'C').slice(0,1).toUpperCase()}</div>
                    <div className="portal-client-copy"><strong>{c.name}</strong><span>{c.email}</span></div>
                    <Eye size={18} className="portal-client-eye"/>
                  </button>
                ))}
              </div>
            )}
          </section>

          {selectedEmail && (
            <section className="portal-section">
              {busy && !summary ? <div className="portal-loading"><LoaderCircle className="spin"/><span>Loading summary…</span></div> : summary && (
                <div className="portal-summary">
                  <div className="portal-summary-head">
                    <div>
                      <span className="eyebrow">READ-ONLY CLIENT REPORT</span>
                      <h2>{summary.client.name}</h2>
                      <p>{summary.client.email}</p>
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <button className="btn btn-quiet btn-small" onClick={() => refreshSummary(true)} disabled={busy} title="Refresh summary">
                        <RefreshCw size={14} className={busy ? 'spin' : ''}/> Refresh
                      </button>
                      <span className="status-tag good"><LockKeyhole size={12}/> Read only</span>
                    </div>
                  </div>
                  <div className="portal-summary-stats">
                    <div><span>Net cash flow</span><strong>{money(summary.summary.balance)}</strong></div>
                    <div><span>Monthly income</span><strong>{money(summary.summary.income)}</strong></div>
                    <div><span>Monthly expenses</span><strong>{money(summary.summary.expenses)}</strong></div>
                  </div>
                  <div className="portal-tx-section">
                    <h3><ReceiptText size={16}/> Recent transactions</h3>
                    {summary.recent_transactions.length === 0 ? <p className="portal-tx-empty">No transactions recorded yet.</p> : (
                      <div className="portal-tx-list">
                        {summary.recent_transactions.map(t => (
                          <div className="portal-tx" key={t.id}>
                            <div className={`portal-tx-icon ${t.kind}`}>{t.kind === 'income' ? <ArrowDownLeft size={16}/> : <ArrowUpRight size={16}/>}</div>
                            <div className="portal-tx-body"><strong>{t.note || t.category}</strong><span>{t.category} · {dateText(t.trans_date)}</span></div>
                            <span className={`portal-tx-amount ${t.kind}`}>{t.kind === 'income' ? '+' : '−'}{moneyExact(t.amount)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <p className="portal-readonly-note"><ShieldCheck size={14}/> This is a read-only view. You cannot edit, delete, or create any data for this client.</p>
                </div>
              )}
            </section>
          )}
        </>}
      </main>

      <footer className="portal-footer">
        <span>FinSight Advisor Portal</span>
        <span>Read-only · No editing · Revocable by client</span>
      </footer>

      {toast && (
        <div className={`toast ${toast.type === 'error' ? 'toast-error' : ''}`}>
          <span className="toast-icon">{toast.type === 'error' ? <CircleAlert size={17}/> : <Check size={17}/>}</span>
          <span>{toast.msg}</span>
          <button onClick={() => setToast(null)}><X size={15}/></button>
        </div>
      )}
    </div>
  );
}

function PortalAuth({ mode, setMode, form, setForm, submit, error }) {
  return (
    <div className="portal-auth-page">
      <div className="portal-auth-card">
        <div className="portal-auth-head">
          <div className="brand-mark" style={{ width:44, height:44, borderRadius:14 }}><Leaf size={24}/></div>
          <div>
            <div className="portal-brand-name">finsight<span>.</span></div>
            <div className="portal-brand-caption">ADVISOR PORTAL</div>
          </div>
        </div>
        <div className="portal-auth-body">
          <span className="eyebrow"><ShieldCheck size={13}/> READ-ONLY FINANCIAL ADVISOR ACCESS</span>
          <h1>{mode === 'login' ? 'Welcome back, advisor.' : 'Create your advisor account.'}</h1>
          <p>Sign in to review client summaries shared with your email. You can only view data — never edit it.</p>
          <form className="auth-form" onSubmit={submit}>
            {mode === 'register' && <label>Your name<div className="field-icon"><UserRound size={17}/><input required minLength={2} maxLength={100} autoComplete="name" placeholder="Your full name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}/></div></label>}
            <label>Email address<div className="field-icon"><Mail size={17}/><input required type="email" autoComplete="email" placeholder="advisor@example.com" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })}/></div></label>
            <label>Password<div className="field-icon"><KeyRound size={17}/><input required minLength={mode === 'register' ? 8 : 1} maxLength={128} type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} placeholder={mode === 'register' ? 'At least 8 characters' : 'Enter your password'} value={form.password} onChange={e => setForm({ ...form, password: e.target.value })}/></div>{mode === 'register' && <small>Use at least 8 characters.</small>}</label>
            {error && <div className="auth-error"><CircleAlert size={16}/>{error}</div>}
            <button className="btn btn-primary auth-submit" type="submit">{mode === 'login' ? 'Sign in to Advisor Portal' : 'Create advisor account'}</button>
          </form>
          <div className="auth-switch">{mode === 'login' ? "Don't have an account yet?" : 'Already have an account?'} <button onClick={() => setMode(mode === 'login' ? 'register' : 'login')}>{mode === 'login' ? 'Create an account' : 'Sign in'}</button></div>
          <p className="portal-auth-note"><ShieldCheck size={14}/> This portal is separate from the client app. Your account is never granted edit access.</p>
        </div>
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<React.StrictMode><AdvisorApp/></React.StrictMode>);