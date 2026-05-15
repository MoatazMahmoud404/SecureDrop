"use client";

import { useRouter } from 'next/navigation';

const palette = {
  primary: '#3D92CB',
  secondary: '#0C4763',
  accent: '#6DBB48',
  surface: '#AECFD5',
  background: '#FDFDFD',
};

export default function HomePage() {
  const router = useRouter();

  function openDashboard() {
    router.push('/dashboard');
  }

  function viewArchitecture() {
    window.open('/README.md', '_blank');
  }

  function openLogin() {
    router.push('/login');
  }

  return (
    <main style={{ background: palette.background, color: palette.secondary }} className="min-h-screen px-6 py-10">
      <section
        className="mx-auto max-w-6xl overflow-hidden rounded-3xl border border-[#D7E6EF] shadow-[0_24px_70px_rgba(12,71,99,0.14)]"
        style={{ background: 'linear-gradient(135deg, #FDFDFD 0%, #F2F8FC 55%, #EAF6EE 100%)' }}
      >
        <div className="grid gap-8 p-8 md:grid-cols-[1.1fr_0.9fr] md:p-10">
          <div className="space-y-6">
            <p className="text-sm font-semibold uppercase tracking-[0.25em]" style={{ color: palette.primary }}>
              SecureDrop Platform
            </p>
            <h1 className="text-4xl font-semibold leading-tight md:text-6xl">
              Secure file sharing for teams with strong access control.
            </h1>
            <p className="max-w-2xl text-lg leading-8 text-slate-600">
              SecureDrop combines a React dashboard, FastAPI control plane, and TLS socket transfer layer to deliver authenticated uploads, controlled sharing, and auditable downloads.
            </p>
            <div className="flex flex-wrap gap-3">
              <button
                className="rounded-full px-6 py-3 font-semibold text-white"
                style={{ background: palette.primary }}
                onClick={openLogin}
              >
                Start Now
              </button>
              <button
                className="rounded-full px-6 py-3 font-semibold"
                style={{ border: `1px solid ${palette.secondary}`, color: palette.secondary }}
                onClick={openDashboard}
              >
                Open Dashboard
              </button>
              <button
                className="rounded-full px-6 py-3 font-semibold"
                style={{ border: `1px solid ${palette.primary}`, color: palette.primary }}
                onClick={viewArchitecture}
              >
                View Architecture
              </button>
            </div>
          </div>

          <div className="rounded-3xl border border-[#D6E4EE] bg-white/85 p-6 backdrop-blur">
            <h2 className="text-xl font-semibold">How This Project Works</h2>
            <ol className="mt-4 space-y-3 text-sm text-slate-700">
              <li>
                <span className="font-semibold text-[#0C4763]">1.</span> User authenticates with JWT and optional 2FA.
              </li>
              <li>
                <span className="font-semibold text-[#0C4763]">2.</span> API issues a short-lived transfer token for upload/download.
              </li>
              <li>
                <span className="font-semibold text-[#0C4763]">3.</span> File bytes move over TLS socket server in chunks.
              </li>
              <li>
                <span className="font-semibold text-[#0C4763]">4.</span> Metadata, permissions, and audit logs are stored centrally.
              </li>
              <li>
                <span className="font-semibold text-[#0C4763]">5.</span> Shared access is enforced through user permissions or password links.
              </li>
            </ol>
          </div>
        </div>

        <div className="grid gap-4 border-t border-[#D7E6EF] bg-[#F7FBFD] p-8 md:grid-cols-2 md:p-10">
          <div className="rounded-2xl border border-[#D7E6EF] bg-white p-5">
            <h3 className="text-lg font-semibold">How Encryption Works</h3>
            <ol className="mt-3 space-y-2 text-sm text-slate-700">
              <li>1. Data in transit is encrypted with TLS during file transfer between backend and socket server.</li>
              <li>2. User passwords are not stored in plain text; they are hashed with SHA256</li>
              <li>3. Share passwords are also stored as salted hashes before saving to the database.</li>
              <li>4. Access tokens are signed with SHA256 so tampering is detected.</li>
            </ol>
          </div>
          <div className="rounded-2xl border border-[#D7E6EF] bg-white p-5">
            <h3 className="text-lg font-semibold">How WebSocket Fits</h3>
            <p className="mt-3 text-sm text-slate-700">
              Current implementation uses HTTPS API + TLS socket transport. A WebSocket (`wss://`) bridge is the next extension point for real-time progress and notifications without polling.
            </p>
            <p className="mt-3 text-sm text-slate-700">
              In that mode, browser events flow through WebSocket while backend still enforces the same transfer tokens and SSL/TLS security boundaries.
            </p>
          </div>
        </div>

        <div className="grid gap-4 border-t border-[#D7E6EF] bg-white/70 p-8 md:grid-cols-3 md:p-10">
          <div className="rounded-2xl border border-[#D7E6EF] bg-white p-5">
            <h3 className="text-lg font-semibold">Security Features</h3>
            <p className="mt-2 text-sm text-slate-700">JWT sessions, refresh token flow, optional TOTP 2FA, TLS file transport, and role-based admin access.</p>
          </div>
          <div className="rounded-2xl border border-[#D7E6EF] bg-white p-5">
            <h3 className="text-lg font-semibold">Sharing Features</h3>
            <p className="mt-2 text-sm text-slate-700">Share to specific users, bulk share, expiring public links, password-protected links, and download limits.</p>
          </div>
          <div className="rounded-2xl border border-[#D7E6EF] bg-white p-5">
            <h3 className="text-lg font-semibold">Operations Features</h3>
            <p className="mt-2 text-sm text-slate-700">Admin user lifecycle controls, searchable audit records, activity history, and health visibility for backend services.</p>
          </div>
        </div>
      </section>
    </main>
  );
}
