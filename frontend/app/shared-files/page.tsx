"use client";

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';

import { SharedFileRecord, downloadSharedFile, getToken, listSharedFiles } from '@/lib/api';

export default function SharedFilesPage() {
  const router = useRouter();
  const [files, setFiles] = useState<SharedFileRecord[]>([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);

  const formattedFiles = useMemo(
    () =>
      files.map((file) => ({
        ...file,
        sharedAtLabel: new Date(file.shared_at).toLocaleString(),
        sizeLabel: `${(file.file_size / (1024 * 1024)).toFixed(2)} MB`,
      })),
    [files],
  );

  const refreshSharedFiles = useCallback(async () => {
    const token = getToken();
    if (!token) {
      router.replace('/login');
      return;
    }

    try {
      const response = await listSharedFiles(token);
      setFiles(response);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not load shared files');
    }
  }, [router]);

  useEffect(() => {
    void refreshSharedFiles();
  }, [refreshSharedFiles]);

  async function onDownload(fileId: string, fileName: string) {
    const token = getToken();
    if (!token) {
      router.replace('/login');
      return;
    }

    setBusy(true);
    setError('');
    setMessage('');
    setProgress(0);
    try {
      const blob = await downloadSharedFile(token, fileId, (percent) => setProgress(percent));
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = fileName;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setProgress(100);
      setMessage(`Downloaded ${fileName}`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Download failed');
      setProgress(0);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="h-full bg-[#FDFDFD] px-6 py-6 text-[#0C4763]">
      <div className="mx-auto max-w-6xl space-y-8">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-[#3D92CB]">SecureDrop</p>
            <h1 className="mt-3 text-4xl font-semibold">Shared With Me</h1>
            <p className="mt-2 text-slate-600">Files other users shared with your account.</p>
          </div>
          <button
            className="rounded-full border border-[#0C4763] px-4 py-2 text-sm font-semibold"
            onClick={() => router.push('/dashboard')}
          >
            Back to dashboard
          </button>
        </div>

        {error ? <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}
        {message ? <p className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</p> : null}

        <section className="rounded-3xl bg-white p-6 shadow-[0_18px_50px_rgba(12,71,99,0.12)]">
          <div className="overflow-hidden rounded-2xl border border-slate-200">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Owner</th>
                  <th className="px-4 py-3">Permission</th>
                  <th className="px-4 py-3">Size</th>
                  <th className="px-4 py-3">Shared At</th>
                  <th className="px-4 py-3">Action</th>
                </tr>
              </thead>
              <tbody>
                {formattedFiles.map((file) => (
                  <tr key={`${file.file_id}:${file.owner_username}`} className="border-t border-slate-200">
                    <td className="px-4 py-3 font-medium">{file.file_name}</td>
                    <td className="px-4 py-3">{file.owner_username}</td>
                    <td className="px-4 py-3">
                      <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700">
                        {file.permission}
                      </span>
                    </td>
                    <td className="px-4 py-3">{file.sizeLabel}</td>
                    <td className="px-4 py-3">{file.sharedAtLabel}</td>
                    <td className="px-4 py-3">
                      <button
                        className="rounded-full border border-[#0C4763] px-3 py-1 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50"
                        onClick={() => onDownload(file.file_id, file.file_name)}
                        disabled={busy || file.permission !== 'download'}
                        title={file.permission !== 'download' ? 'Only view permission granted' : 'Download file'}
                      >
                        Download
                      </button>
                    </td>
                  </tr>
                ))}
                {formattedFiles.length === 0 ? (
                  <tr>
                    <td className="px-4 py-6 text-slate-500" colSpan={6}>
                      No files have been shared with you yet.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div className="mt-4 text-sm text-slate-600">
            Transfer progress: {progress}%
            <div className="mt-2 h-2 rounded-full bg-slate-100">
              <div className="h-2 rounded-full bg-[#6DBB48] transition-all" style={{ width: `${progress}%` }} />
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
