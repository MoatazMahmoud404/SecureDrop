"use client";

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { ActivityLogRecord, getToken, getUserActivity } from '@/lib/api';

export default function ActivityPage() {
  const router = useRouter();
  const [records, setRecords] = useState<ActivityLogRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const authToken = getToken();
    if (!authToken) {
      router.replace('/login');
      return;
    }

    async function load(token: string) {
      setLoading(true);
      setError('');
      try {
        const response = await getUserActivity(token, 100);
        setRecords(response);
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : 'Could not load activity logs');
      } finally {
        setLoading(false);
      }
    }

    void load(authToken);
  }, [router]);

  return (
    <main className="h-full bg-[#FDFDFD] px-6 py-6 text-[#0C4763]">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-[#3D92CB]">SecureDrop</p>
            <h1 className="mt-3 text-3xl font-semibold">My Activity</h1>
            <p className="mt-2 text-sm text-slate-600">Recent security and file operations from your account.</p>
          </div>
          <button
            className="rounded-full border border-[#0C4763] px-4 py-2 text-sm font-semibold"
            onClick={() => router.push('/dashboard')}
          >
            Back to dashboard
          </button>
        </div>

        {error ? <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_18px_50px_rgba(12,71,99,0.08)]">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-4 py-3">Time</th>
                <th className="px-4 py-3">Action</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Resource</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td className="px-4 py-6 text-slate-500" colSpan={4}>
                    Loading activity logs...
                  </td>
                </tr>
              ) : records.length === 0 ? (
                <tr>
                  <td className="px-4 py-6 text-slate-500" colSpan={4}>
                    No activity records yet.
                  </td>
                </tr>
              ) : (
                records.map((record) => (
                  <tr key={record.id} className="border-t border-slate-200">
                    <td className="px-4 py-3">{new Date(record.timestamp).toLocaleString()}</td>
                    <td className="px-4 py-3 font-medium">{record.action}</td>
                    <td className="px-4 py-3">
                      <span
                        className={
                          record.status === 'success'
                            ? 'rounded-full bg-emerald-100 px-2 py-1 text-xs font-semibold text-emerald-700'
                            : 'rounded-full bg-red-100 px-2 py-1 text-xs font-semibold text-red-700'
                        }
                      >
                        {record.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {record.resource_type ?? '-'}
                      {record.resource_id ? `:${record.resource_id}` : ''}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
