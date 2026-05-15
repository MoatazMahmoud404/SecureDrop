"use client";

import { useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';

import { downloadFromShareLink, getShareLinkMetadata, ShareLinkMetadata } from '@/lib/api';

export default function ShareDownloadPage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const token = useMemo(() => {
    const value = params?.token;
    return Array.isArray(value) ? value[0] : value ?? '';
  }, [params]);

  const [metadata, setMetadata] = useState<ShareLinkMetadata | null>(null);
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!token) {
      return;
    }

    async function loadMetadata() {
      setLoading(true);
      setError('');
      setMessage('');
      try {
        const response = await getShareLinkMetadata(token);
        setMetadata(response);
      } catch (requestError) {
        setMetadata(null);
        setError(requestError instanceof Error ? requestError.message : 'Could not load share link');
      } finally {
        setLoading(false);
      }
    }

    void loadMetadata();
  }, [token]);

  async function handleDownload() {
    if (!token) {
      return;
    }

    const trimmedPassword = password.trim();
    if (metadata?.requires_password && trimmedPassword.length === 0) {
      setError('This link requires a password.');
      return;
    }
    if (trimmedPassword.length > 0 && trimmedPassword.length < 4) {
      setError('Password must be at least 4 characters.');
      return;
    }

    setDownloading(true);
    setError('');
    setMessage('');
    try {
      const blob = await downloadFromShareLink(token, trimmedPassword || undefined);
      const fileName = metadata?.file_name || 'download.bin';
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = fileName;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setMessage(`Downloaded ${fileName}`);

      const refreshed = await getShareLinkMetadata(token);
      setMetadata(refreshed);
      setPassword('');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Download failed');
    } finally {
      setDownloading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#FDFDFD] px-6 py-10 text-[#0C4763]">
      <div className="mx-auto max-w-2xl space-y-6 rounded-3xl bg-white p-8 shadow-[0_18px_50px_rgba(12,71,99,0.12)]">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.25em] text-[#3D92CB]">SecureDrop</p>
          <h1 className="mt-3 text-3xl font-semibold">Shared File Download</h1>
          <p className="mt-2 text-sm text-slate-600">Open and download a shared file using this link token.</p>
        </div>

        {error ? <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}
        {message ? <p className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</p> : null}

        {loading ? (
          <p className="text-sm text-slate-600">Loading share metadata...</p>
        ) : metadata ? (
          <div className="space-y-4 rounded-2xl border border-slate-200 p-4">
            <div className="grid gap-2 text-sm text-slate-700">
              <p>
                <span className="font-semibold text-[#0C4763]">File:</span> {metadata.file_name}
              </p>
              <p>
                <span className="font-semibold text-[#0C4763]">Size:</span> {(metadata.file_size / (1024 * 1024)).toFixed(2)} MB
              </p>
              <p>
                <span className="font-semibold text-[#0C4763]">Expires:</span> {new Date(metadata.expires_at).toLocaleString()}
              </p>
              <p>
                <span className="font-semibold text-[#0C4763]">Remaining downloads:</span>{' '}
                {metadata.remaining_downloads < 0 ? 'Unlimited' : metadata.remaining_downloads}
              </p>
            </div>

            {metadata.requires_password ? (
              <input
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
                type="password"
                placeholder="Enter share password"
                minLength={4}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            ) : null}

            <div className="flex flex-wrap gap-3">
              <button
                className="rounded-2xl bg-[#3D92CB] px-4 py-3 font-semibold text-white"
                onClick={handleDownload}
                disabled={downloading}
              >
                {downloading ? 'Downloading...' : 'Download file'}
              </button>
              <button
                className="rounded-2xl border border-slate-300 px-4 py-3 font-semibold text-slate-700"
                onClick={() => router.push('/login')}
              >
                Go to login
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </main>
  );
}
