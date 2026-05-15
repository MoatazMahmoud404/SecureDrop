"use client";

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';

import {
  AdminActivityLogRecord,
  AdminUserSummary,
  createAdminUser,
  deleteAdminUser,
  getAdminAuditLogs,
  getCurrentUserRole,
  getHealth,
  getToken,
  listAdminUsers,
  updateAdminUser,
} from '@/lib/api';

type SortDirection = 'asc' | 'desc';
type UserSortKey = 'username' | 'role' | 'is_active' | 'created_at';
type AuditSortKey = 'timestamp' | 'username' | 'action' | 'status' | 'resource';

export default function AdminAuditPage() {
  const router = useRouter();
  const [records, setRecords] = useState<AdminActivityLogRecord[]>([]);
  const [users, setUsers] = useState<AdminUserSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [healthStatus, setHealthStatus] = useState<'unknown' | 'ok' | 'down'>('unknown');

  const [auditSearch, setAuditSearch] = useState('');
  const [userSearch, setUserSearch] = useState('');
  const [auditSortKey, setAuditSortKey] = useState<AuditSortKey>('timestamp');
  const [auditSortDirection, setAuditSortDirection] = useState<SortDirection>('desc');
  const [userSortKey, setUserSortKey] = useState<UserSortKey>('username');
  const [userSortDirection, setUserSortDirection] = useState<SortDirection>('asc');
  const [userPage, setUserPage] = useState(1);
  const [userPageSize, setUserPageSize] = useState(10);
  const [auditPage, setAuditPage] = useState(1);
  const [auditPageSize, setAuditPageSize] = useState(25);

  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState<'user' | 'admin'>('user');
  const [creatingUser, setCreatingUser] = useState(false);
  const [mutatingUserId, setMutatingUserId] = useState<string | null>(null);

  useEffect(() => {
    const authToken = getToken();
    if (!authToken) {
      router.replace('/login');
      return;
    }

    if (getCurrentUserRole() !== 'admin') {
      router.replace('/dashboard');
      return;
    }

    async function load(token: string) {
      setLoading(true);
      setError('');
      try {
        const [auditResponse, usersResponse, healthResponse] = await Promise.all([
          getAdminAuditLogs(token, 400),
          listAdminUsers(token),
          getHealth(),
        ]);
        setRecords(auditResponse);
        setUsers(usersResponse);
        setHealthStatus(healthResponse.status === 'ok' ? 'ok' : 'down');
      } catch (requestError) {
        const msg = requestError instanceof Error ? requestError.message : 'Could not load admin data';
        setError(msg);
        setHealthStatus('down');
      } finally {
        setLoading(false);
      }
    }

    void load(authToken);
  }, [router]);

  function onToggleSort<T extends string>(
    key: T,
    currentKey: T,
    currentDirection: SortDirection,
    setKey: (value: T) => void,
    setDirection: (value: SortDirection) => void,
  ) {
    if (key === currentKey) {
      setDirection(currentDirection === 'asc' ? 'desc' : 'asc');
      return;
    }
    setKey(key);
    setDirection('asc');
  }

  const filteredSortedUsers = useMemo(() => {
    const q = userSearch.trim().toLowerCase();
    const filtered = users.filter((user) => {
      if (!q) {
        return true;
      }
      return (
        user.username.toLowerCase().includes(q)
        || user.role.toLowerCase().includes(q)
        || (user.is_active ? 'active' : 'inactive').includes(q)
      );
    });

    return filtered.sort((a, b) => {
      let left: string | number = '';
      let right: string | number = '';

      if (userSortKey === 'username') {
        left = a.username.toLowerCase();
        right = b.username.toLowerCase();
      } else if (userSortKey === 'role') {
        left = a.role;
        right = b.role;
      } else if (userSortKey === 'is_active') {
        left = a.is_active ? 1 : 0;
        right = b.is_active ? 1 : 0;
      } else {
        left = new Date(a.created_at).getTime();
        right = new Date(b.created_at).getTime();
      }

      if (left === right) {
        return 0;
      }
      if (userSortDirection === 'asc') {
        return left > right ? 1 : -1;
      }
      return left < right ? 1 : -1;
    });
  }, [users, userSearch, userSortKey, userSortDirection]);

  const filteredSortedRecords = useMemo(() => {
    const q = auditSearch.trim().toLowerCase();
    const filtered = records.filter((record) => {
      const resource = `${record.resource_type ?? ''}:${record.resource_id ?? ''}`.toLowerCase();
      const user = (record.username ?? record.user_id ?? '').toLowerCase();
      if (!q) {
        return true;
      }
      return (
        record.action.toLowerCase().includes(q)
        || record.status.toLowerCase().includes(q)
        || user.includes(q)
        || resource.includes(q)
        || new Date(record.timestamp).toLocaleString().toLowerCase().includes(q)
      );
    });

    return filtered.sort((a, b) => {
      let left: string | number = '';
      let right: string | number = '';

      if (auditSortKey === 'timestamp') {
        left = new Date(a.timestamp).getTime();
        right = new Date(b.timestamp).getTime();
      } else if (auditSortKey === 'username') {
        left = (a.username ?? a.user_id ?? '').toLowerCase();
        right = (b.username ?? b.user_id ?? '').toLowerCase();
      } else if (auditSortKey === 'action') {
        left = a.action.toLowerCase();
        right = b.action.toLowerCase();
      } else if (auditSortKey === 'status') {
        left = a.status.toLowerCase();
        right = b.status.toLowerCase();
      } else {
        left = `${a.resource_type ?? ''}:${a.resource_id ?? ''}`.toLowerCase();
        right = `${b.resource_type ?? ''}:${b.resource_id ?? ''}`.toLowerCase();
      }

      if (left === right) {
        return 0;
      }
      if (auditSortDirection === 'asc') {
        return left > right ? 1 : -1;
      }
      return left < right ? 1 : -1;
    });
  }, [records, auditSearch, auditSortKey, auditSortDirection]);

  useEffect(() => {
    setUserPage(1);
  }, [userSearch, userSortKey, userSortDirection]);

  useEffect(() => {
    setAuditPage(1);
  }, [auditSearch, auditSortKey, auditSortDirection]);

  const userTotalPages = Math.max(1, Math.ceil(filteredSortedUsers.length / userPageSize));
  const userCurrentPage = Math.min(userPage, userTotalPages);
  const pagedUsers = useMemo(() => {
    const start = (userCurrentPage - 1) * userPageSize;
    return filteredSortedUsers.slice(start, start + userPageSize);
  }, [filteredSortedUsers, userCurrentPage, userPageSize]);

  const auditTotalPages = Math.max(1, Math.ceil(filteredSortedRecords.length / auditPageSize));
  const auditCurrentPage = Math.min(auditPage, auditTotalPages);
  const pagedRecords = useMemo(() => {
    const start = (auditCurrentPage - 1) * auditPageSize;
    return filteredSortedRecords.slice(start, start + auditPageSize);
  }, [filteredSortedRecords, auditCurrentPage, auditPageSize]);

  async function refreshUsers() {
    const token = getToken();
    if (!token) {
      return;
    }
    const response = await listAdminUsers(token);
    setUsers(response);
  }

  async function onCreateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const token = getToken();
    if (!token) {
      router.replace('/login');
      return;
    }

    setError('');
    setMessage('');
    setCreatingUser(true);
    try {
      await createAdminUser(token, {
        username: newUsername.trim(),
        password: newPassword,
        role: newRole,
      });
      setNewUsername('');
      setNewPassword('');
      setNewRole('user');
      await refreshUsers();
      setMessage('User created successfully.');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not create user');
    } finally {
      setCreatingUser(false);
    }
  }

  async function onToggleUserActive(user: AdminUserSummary) {
    const token = getToken();
    if (!token) {
      router.replace('/login');
      return;
    }

    setError('');
    setMessage('');
    setMutatingUserId(user.id);
    try {
      await updateAdminUser(token, user.id, { is_active: !user.is_active });
      await refreshUsers();
      setMessage(`${user.username} is now ${user.is_active ? 'inactive' : 'active'}.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not update user state');
    } finally {
      setMutatingUserId(null);
    }
  }

  async function onDeleteUser(user: AdminUserSummary) {
    const token = getToken();
    if (!token) {
      router.replace('/login');
      return;
    }

    setError('');
    setMessage('');
    setMutatingUserId(user.id);
    try {
      await deleteAdminUser(token, user.id);
      await refreshUsers();
      setMessage(`${user.username} deleted successfully.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not delete user');
    } finally {
      setMutatingUserId(null);
    }
  }

  return (
    <main className="h-full bg-[#FDFDFD] px-6 py-6 text-[#0C4763]">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-[#3D92CB]">SecureDrop</p>
            <h1 className="mt-3 text-3xl font-semibold">Admin Audit</h1>
            <p className="mt-2 text-sm text-slate-600">Review logs and manage users from dedicated sections.</p>
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

        <section id="logs-section" className="scroll-mt-24 space-y-5 rounded-2xl border border-slate-200 bg-[#F8FCFF] p-5">
          <div>
            <h2 className="text-xl font-semibold">Logs Section</h2>
            <p className="mt-1 text-sm text-slate-600">System health and audit event history.</p>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_10px_30px_rgba(12,71,99,0.08)]">
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-500">Backend Health</p>
              <p className="mt-2 text-2xl font-semibold">
                {healthStatus === 'ok' ? 'Healthy' : healthStatus === 'down' ? 'Unavailable' : 'Checking...'}
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_10px_30px_rgba(12,71,99,0.08)]">
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-500">Users</p>
              <p className="mt-2 text-2xl font-semibold">{loading ? '...' : users.length}</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_10px_30px_rgba(12,71,99,0.08)]">
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-500">Audit Records</p>
              <p className="mt-2 text-2xl font-semibold">{loading ? '...' : records.length}</p>
            </div>
          </div>

          <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_14px_40px_rgba(12,71,99,0.08)]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-xl font-semibold">Audit Explorer</h3>
              <input
                className="w-full max-w-sm rounded-xl border border-slate-300 px-3 py-2 text-sm"
                placeholder="Search by user, action, status, resource"
                value={auditSearch}
                onChange={(event) => setAuditSearch(event.target.value)}
              />
            </div>

            <div className="overflow-hidden rounded-2xl border border-slate-200">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-slate-500">
                  <tr>
                    <th className="cursor-pointer px-4 py-3" onClick={() => onToggleSort('timestamp', auditSortKey, auditSortDirection, setAuditSortKey, setAuditSortDirection)}>Time</th>
                    <th className="cursor-pointer px-4 py-3" onClick={() => onToggleSort('username', auditSortKey, auditSortDirection, setAuditSortKey, setAuditSortDirection)}>User</th>
                    <th className="cursor-pointer px-4 py-3" onClick={() => onToggleSort('action', auditSortKey, auditSortDirection, setAuditSortKey, setAuditSortDirection)}>Action</th>
                    <th className="cursor-pointer px-4 py-3" onClick={() => onToggleSort('status', auditSortKey, auditSortDirection, setAuditSortKey, setAuditSortDirection)}>Status</th>
                    <th className="cursor-pointer px-4 py-3" onClick={() => onToggleSort('resource', auditSortKey, auditSortDirection, setAuditSortKey, setAuditSortDirection)}>Resource</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td className="px-4 py-6 text-slate-500" colSpan={5}>Loading admin logs...</td></tr>
                  ) : filteredSortedRecords.length === 0 ? (
                    <tr><td className="px-4 py-6 text-slate-500" colSpan={5}>No admin logs found.</td></tr>
                  ) : (
                    pagedRecords.map((record) => (
                      <tr key={record.id} className="border-t border-slate-200">
                        <td className="px-4 py-3">{new Date(record.timestamp).toLocaleString()}</td>
                        <td className="px-4 py-3 text-slate-700">{record.username ?? '-'}</td>
                        <td className="px-4 py-3 font-medium">{record.action}</td>
                        <td className="px-4 py-3">
                          <span className={record.status === 'success' ? 'rounded-full bg-emerald-100 px-2 py-1 text-xs font-semibold text-emerald-700' : 'rounded-full bg-red-100 px-2 py-1 text-xs font-semibold text-red-700'}>
                            {record.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-slate-600">{record.resource_type ?? '-'}{record.resource_id ? `:${record.resource_id}` : ''}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
              <p className="text-slate-600">
                Showing {filteredSortedRecords.length === 0 ? 0 : (auditCurrentPage - 1) * auditPageSize + 1}
                {' '}to {Math.min(auditCurrentPage * auditPageSize, filteredSortedRecords.length)} of {filteredSortedRecords.length} records
              </p>
              <div className="flex items-center gap-2">
                <select
                  className="rounded-lg border border-slate-300 px-2 py-1"
                  value={auditPageSize}
                  onChange={(event) => {
                    setAuditPageSize(Number(event.target.value));
                    setAuditPage(1);
                  }}
                >
                  <option value={25}>25 / page</option>
                  <option value={50}>50 / page</option>
                  <option value={100}>100 / page</option>
                </select>
                <button
                  className="rounded-lg border border-slate-300 px-3 py-1 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => setAuditPage((current) => Math.max(1, current - 1))}
                  disabled={auditCurrentPage <= 1}
                >
                  Prev
                </button>
                <span className="text-slate-700">Page {auditCurrentPage} / {auditTotalPages}</span>
                <button
                  className="rounded-lg border border-slate-300 px-3 py-1 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => setAuditPage((current) => Math.min(auditTotalPages, current + 1))}
                  disabled={auditCurrentPage >= auditTotalPages}
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        </section>

        <section id="user-management-section" className="scroll-mt-24 space-y-5 rounded-2xl border border-slate-200 bg-[#FCFFFA] p-5">
          <div>
            <h2 className="text-xl font-semibold">User Management Section</h2>
            <p className="mt-1 text-sm text-slate-600">Create, search, activate, and delete users.</p>
          </div>

          <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_14px_40px_rgba(12,71,99,0.08)]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-xl font-semibold">User Management</h3>
              <input
                className="w-full max-w-sm rounded-xl border border-slate-300 px-3 py-2 text-sm"
                placeholder="Search users by name, role, or status"
                value={userSearch}
                onChange={(event) => setUserSearch(event.target.value)}
              />
            </div>

            <form className="grid gap-3 rounded-xl border border-slate-200 p-4 md:grid-cols-[1fr_1fr_160px_140px]" onSubmit={onCreateUser}>
              <input
                className="rounded-xl border border-slate-300 px-3 py-2 text-sm"
                placeholder="Username"
                value={newUsername}
                onChange={(event) => setNewUsername(event.target.value)}
                required
              />
              <input
                className="rounded-xl border border-slate-300 px-3 py-2 text-sm"
                placeholder="Password"
                type="password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                minLength={8}
                required
              />
              <select
                className="rounded-xl border border-slate-300 px-3 py-2 text-sm"
                value={newRole}
                onChange={(event) => setNewRole(event.target.value as 'user' | 'admin')}
              >
                <option value="user">user</option>
                <option value="admin">admin</option>
              </select>
              <button className="rounded-xl bg-[#0C4763] px-4 py-2 text-sm font-semibold text-white" disabled={creatingUser}>
                {creatingUser ? 'Creating...' : 'Create User'}
              </button>
            </form>

            <div className="overflow-hidden rounded-2xl border border-slate-200">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-slate-500">
                  <tr>
                    <th className="cursor-pointer px-4 py-3" onClick={() => onToggleSort('username', userSortKey, userSortDirection, setUserSortKey, setUserSortDirection)}>Username</th>
                    <th className="cursor-pointer px-4 py-3" onClick={() => onToggleSort('role', userSortKey, userSortDirection, setUserSortKey, setUserSortDirection)}>Role</th>
                    <th className="cursor-pointer px-4 py-3" onClick={() => onToggleSort('is_active', userSortKey, userSortDirection, setUserSortKey, setUserSortDirection)}>Status</th>
                    <th className="cursor-pointer px-4 py-3" onClick={() => onToggleSort('created_at', userSortKey, userSortDirection, setUserSortKey, setUserSortDirection)}>Created</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td className="px-4 py-6 text-slate-500" colSpan={5}>Loading users...</td></tr>
                  ) : filteredSortedUsers.length === 0 ? (
                    <tr><td className="px-4 py-6 text-slate-500" colSpan={5}>No users found.</td></tr>
                  ) : (
                    pagedUsers.map((user) => (
                      <tr key={user.id} className="border-t border-slate-200">
                        <td className="px-4 py-3 font-medium">{user.username}</td>
                        <td className="px-4 py-3 text-slate-600">{user.role}</td>
                        <td className="px-4 py-3">
                          <span className={user.is_active ? 'rounded-full bg-emerald-100 px-2 py-1 text-xs font-semibold text-emerald-700' : 'rounded-full bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-700'}>
                            {user.is_active ? 'active' : 'inactive'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-slate-600">{new Date(user.created_at).toLocaleString()}</td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-2">
                            <button
                              className="rounded-full border border-slate-400 px-3 py-1 text-xs font-semibold"
                              onClick={() => void onToggleUserActive(user)}
                              disabled={mutatingUserId === user.id}
                            >
                              {user.is_active ? 'Deactivate' : 'Activate'}
                            </button>
                            <button
                              className="rounded-full border border-red-500 px-3 py-1 text-xs font-semibold text-red-700"
                              onClick={() => void onDeleteUser(user)}
                              disabled={mutatingUserId === user.id}
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
              <p className="text-slate-600">
                Showing {filteredSortedUsers.length === 0 ? 0 : (userCurrentPage - 1) * userPageSize + 1}
                {' '}to {Math.min(userCurrentPage * userPageSize, filteredSortedUsers.length)} of {filteredSortedUsers.length} users
              </p>
              <div className="flex items-center gap-2">
                <select
                  className="rounded-lg border border-slate-300 px-2 py-1"
                  value={userPageSize}
                  onChange={(event) => {
                    setUserPageSize(Number(event.target.value));
                    setUserPage(1);
                  }}
                >
                  <option value={10}>10 / page</option>
                  <option value={25}>25 / page</option>
                  <option value={50}>50 / page</option>
                </select>
                <button
                  className="rounded-lg border border-slate-300 px-3 py-1 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => setUserPage((current) => Math.max(1, current - 1))}
                  disabled={userCurrentPage <= 1}
                >
                  Prev
                </button>
                <span className="text-slate-700">Page {userCurrentPage} / {userTotalPages}</span>
                <button
                  className="rounded-lg border border-slate-300 px-3 py-1 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => setUserPage((current) => Math.min(userTotalPages, current + 1))}
                  disabled={userCurrentPage >= userTotalPages}
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
