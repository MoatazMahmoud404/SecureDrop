"use client";

import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useDropzone } from 'react-dropzone';

import {
  ApiFileRecord,
  createShareLink,
  deleteFile,
  downloadCommit,
  getToken,
  listFiles,
  listUsers,
  renameFile,
  requestDownloadToken,
  requestUploadToken,
  shareFileWithUsers,
  uploadCommit,
} from '@/lib/api';

type SharePermission = 'view' | 'download';

type ShareLinkModalState = {
  open: boolean;
  fileId: string;
  fileName: string;
  expiresInMinutes: string;
  password: string;
};

type ShareUsersModalState = {
  open: boolean;
  fileId: string;
  fileName: string;
  permission: SharePermission;
  shareWithAllUsers: boolean;
  recipientUsernames: string[];
};

type UploadShareModalState = {
  open: boolean;
  fileId: string;
  fileName: string;
  permission: SharePermission;
  shareWithAllUsers: boolean;
  recipientUsernames: string[];
  createShareLink: boolean;
  expiresInMinutes: string;
  password: string;
};

type RenameModalState = {
  open: boolean;
  fileId: string;
  currentName: string;
  newName: string;
};

const CLOSED_SHARE_LINK_MODAL: ShareLinkModalState = {
  open: false,
  fileId: '',
  fileName: '',
  expiresInMinutes: '60',
  password: '',
};

const CLOSED_SHARE_USERS_MODAL: ShareUsersModalState = {
  open: false,
  fileId: '',
  fileName: '',
  permission: 'download',
  shareWithAllUsers: false,
  recipientUsernames: [],
};

const CLOSED_UPLOAD_SHARE_MODAL: UploadShareModalState = {
  open: false,
  fileId: '',
  fileName: '',
  permission: 'download',
  shareWithAllUsers: false,
  recipientUsernames: [],
  createShareLink: true,
  expiresInMinutes: '60',
  password: '',
};

const CLOSED_RENAME_MODAL: RenameModalState = {
  open: false,
  fileId: '',
  currentName: '',
  newName: '',
};

function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const kb = bytes / 1024;
  if (kb < 1024) {
    return `${kb.toFixed(2)} KB`;
  }
  const mb = kb / 1024;
  if (mb < 1024) {
    return `${mb.toFixed(2)} MB`;
  }
  const gb = mb / 1024;
  return `${gb.toFixed(2)} GB`;
}

export default function DashboardPage() {
  const router = useRouter();
  const [files, setFiles] = useState<ApiFileRecord[]>([]);
  const [availableUsers, setAvailableUsers] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [shareLinkModal, setShareLinkModal] = useState<ShareLinkModalState>(CLOSED_SHARE_LINK_MODAL);
  const [shareUsersModal, setShareUsersModal] = useState<ShareUsersModalState>(CLOSED_SHARE_USERS_MODAL);
  const [uploadShareModal, setUploadShareModal] = useState<UploadShareModalState>(CLOSED_UPLOAD_SHARE_MODAL);
  const [renameModal, setRenameModal] = useState<RenameModalState>(CLOSED_RENAME_MODAL);

  const formattedFiles = useMemo(
    () =>
      files.map((file) => ({
        ...file,
        uploadedLabel: new Date(file.uploaded_at).toLocaleString(),
        sizeLabel: formatFileSize(file.size),
      })),
    [files],
  );

  const refreshFiles = useCallback(async (): Promise<ApiFileRecord[]> => {
    const token = getToken();
    if (!token) {
      router.push('/login');
      return [];
    }

    try {
      const data = await listFiles(token);
      setFiles(data);
      return data;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not load files');
      return [];
    }
  }, [router]);

  useEffect(() => {
    void refreshFiles();
  }, [refreshFiles]);

  async function fetchAvailableUsers(token: string): Promise<string[]> {
    const users = await listUsers(token);
    const usernames = users.map((user) => user.username);
    setAvailableUsers(usernames);
    return usernames;
  }

  async function uploadSingleFile(selectedFile: File) {
    const token = getToken();
    if (!token) {
      router.push('/login');
      return;
    }

    setBusy(true);
    setError('');
    setMessage('');
    setProgress(0);
    try {
      const transfer = await requestUploadToken(token, selectedFile.name, selectedFile.size);
      const uploadResult = await uploadCommit(token, selectedFile, transfer.token, (percent) => setProgress(percent));
      setProgress(100);

      const refreshedFiles = await refreshFiles();
      const uploadedFileId =
        uploadResult.file_id ?? refreshedFiles.find((item) => item.name === selectedFile.name)?.id ?? '';

      const usernames = await fetchAvailableUsers(token);
      if (uploadedFileId) {
        setUploadShareModal({
          open: true,
          fileId: uploadedFileId,
          fileName: selectedFile.name,
          permission: 'download',
          shareWithAllUsers: false,
          recipientUsernames: usernames.length > 0 ? [usernames[0]] : [],
          createShareLink: true,
          expiresInMinutes: '60',
          password: '',
        });
      } else {
        setMessage('Upload completed. You can use Share actions from the file list.');
      }
    } catch (requestError) {
      setProgress(0);
      setError(requestError instanceof Error ? requestError.message : 'Upload failed');
    } finally {
      setBusy(false);
    }
  }

  async function onUpload(event: ChangeEvent<HTMLInputElement>) {
    const selectedFile = event.target.files?.[0];
    if (!selectedFile) {
      return;
    }

    await uploadSingleFile(selectedFile);
    event.target.value = '';
  }

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      const selectedFile = acceptedFiles[0];
      if (!selectedFile) {
        return;
      }
      await uploadSingleFile(selectedFile);
    },
    [router],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    maxFiles: 1,
    disabled: busy,
    accept: {
      'text/plain': ['.txt'],
      'application/pdf': ['.pdf'],
      'application/msword': ['.doc'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg'],
      'application/zip': ['.zip'],
    },
  });

  async function onDownload(fileId: string, fileName: string) {
    const token = getToken();
    if (!token) {
      router.push('/login');
      return;
    }

    setBusy(true);
    setError('');
    setMessage('');
    setProgress(0);
    try {
      const transfer = await requestDownloadToken(token, fileId);
      const blob = await downloadCommit(token, fileId, transfer.token, (percent) => setProgress(percent));
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
    } finally {
      setBusy(false);
    }
  }

  function openShareLinkModal(file: ApiFileRecord) {
    setShareLinkModal({
      open: true,
      fileId: file.id,
      fileName: file.name,
      expiresInMinutes: '60',
      password: '',
    });
  }

  async function submitShareLink(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const token = getToken();
    if (!token) {
      router.push('/login');
      return;
    }

    const parsedExpires = Number.parseInt(shareLinkModal.expiresInMinutes.trim(), 10);
    if (!Number.isFinite(parsedExpires) || parsedExpires <= 0) {
      setError('Expiry must be a positive number of minutes.');
      return;
    }

    const trimmedPassword = shareLinkModal.password.trim();
    if (trimmedPassword.length > 0 && trimmedPassword.length < 4) {
      setError('Password must be at least 4 characters or left empty.');
      return;
    }

    setBusy(true);
    setError('');
    setMessage('');
    try {
      const share = await createShareLink(token, shareLinkModal.fileId, {
        expiresInMinutes: parsedExpires,
        password: trimmedPassword || undefined,
      });

      const shareUrl = `${window.location.origin}/share/${share.token}`;
      try {
        await navigator.clipboard.writeText(shareUrl);
        setMessage(`Share link copied to clipboard: ${shareUrl}`);
      } catch {
        setMessage(`Share link created: ${shareUrl}`);
      }
      setShareLinkModal(CLOSED_SHARE_LINK_MODAL);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Share link creation failed');
    } finally {
      setBusy(false);
    }
  }

  async function openShareUsersModal(file: ApiFileRecord) {
    const token = getToken();
    if (!token) {
      router.push('/login');
      return;
    }

    setBusy(true);
    setError('');
    setMessage('');
    try {
      const usernames = await fetchAvailableUsers(token);
      setShareUsersModal({
        open: true,
        fileId: file.id,
        fileName: file.name,
        permission: 'download',
        shareWithAllUsers: false,
        recipientUsernames: usernames.length > 0 ? [usernames[0]] : [],
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not load users');
    } finally {
      setBusy(false);
    }
  }

  async function submitShareUsers(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const token = getToken();
    if (!token) {
      router.push('/login');
      return;
    }

    if (!shareUsersModal.shareWithAllUsers && shareUsersModal.recipientUsernames.length === 0) {
      setError('Select at least one user or enable share with all users.');
      return;
    }

    setBusy(true);
    setError('');
    setMessage('');
    try {
      const result = await shareFileWithUsers(
        token,
        shareUsersModal.fileId,
        shareUsersModal.recipientUsernames,
        shareUsersModal.permission,
        shareUsersModal.shareWithAllUsers,
      );

      const missingText = result.missing_usernames.length > 0
        ? ` Missing users: ${result.missing_usernames.join(', ')}.`
        : '';

      setMessage(
        `Shared with ${result.created_count} new users and updated ${result.updated_count} existing permissions.${missingText}`,
      );
      setShareUsersModal(CLOSED_SHARE_USERS_MODAL);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'User sharing failed');
    } finally {
      setBusy(false);
    }
  }

  async function submitUploadShareOptions(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const token = getToken();
    if (!token) {
      router.push('/login');
      return;
    }

    const shouldShareWithUsers = uploadShareModal.shareWithAllUsers || uploadShareModal.recipientUsernames.length > 0;
    if (!shouldShareWithUsers && !uploadShareModal.createShareLink) {
      setUploadShareModal(CLOSED_UPLOAD_SHARE_MODAL);
      setMessage('Upload completed. Sharing skipped.');
      return;
    }

    if (!uploadShareModal.shareWithAllUsers && uploadShareModal.recipientUsernames.length === 0 && uploadShareModal.createShareLink) {
      // Link-only share is allowed.
    }

    if (uploadShareModal.createShareLink) {
      const parsedExpires = Number.parseInt(uploadShareModal.expiresInMinutes.trim(), 10);
      if (!Number.isFinite(parsedExpires) || parsedExpires <= 0) {
        setError('Share link expiry must be a positive number of minutes.');
        return;
      }

      const trimmedPassword = uploadShareModal.password.trim();
      if (trimmedPassword.length > 0 && trimmedPassword.length < 4) {
        setError('Share link password must be at least 4 characters or left empty.');
        return;
      }
    }

    setBusy(true);
    setError('');
    setMessage('');

    try {
      const resultMessages: string[] = ['Upload completed'];

      if (shouldShareWithUsers) {
        const usersResult = await shareFileWithUsers(
          token,
          uploadShareModal.fileId,
          uploadShareModal.recipientUsernames,
          uploadShareModal.permission,
          uploadShareModal.shareWithAllUsers,
        );

        const missingText = usersResult.missing_usernames.length > 0
          ? ` (missing: ${usersResult.missing_usernames.join(', ')})`
          : '';

        resultMessages.push(
          `shared with users: ${usersResult.created_count} created, ${usersResult.updated_count} updated${missingText}`,
        );
      }

      if (uploadShareModal.createShareLink) {
        const parsedExpires = Number.parseInt(uploadShareModal.expiresInMinutes.trim(), 10);
        const linkResult = await createShareLink(token, uploadShareModal.fileId, {
          expiresInMinutes: parsedExpires,
          password: uploadShareModal.password.trim() || undefined,
        });
        const shareUrl = `${window.location.origin}/share/${linkResult.token}`;
        try {
          await navigator.clipboard.writeText(shareUrl);
          resultMessages.push('share link created and copied');
        } catch {
          resultMessages.push(`share link: ${shareUrl}`);
        }
      }

      setMessage(resultMessages.join(' | '));
      setUploadShareModal(CLOSED_UPLOAD_SHARE_MODAL);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Post-upload sharing failed');
    } finally {
      setBusy(false);
    }
  }

  function openRenameModal(file: ApiFileRecord) {
    setRenameModal({
      open: true,
      fileId: file.id,
      currentName: file.name,
      newName: file.name,
    });
  }

  async function submitRename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const token = getToken();
    if (!token) {
      router.push('/login');
      return;
    }

    const trimmedName = renameModal.newName.trim();
    if (!trimmedName) {
      setError('File name is required.');
      return;
    }

    setBusy(true);
    setError('');
    setMessage('');
    try {
      await renameFile(token, renameModal.fileId, trimmedName);
      setMessage('File updated');
      setRenameModal(CLOSED_RENAME_MODAL);
      await refreshFiles();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Rename failed');
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(fileId: string) {
    const token = getToken();
    if (!token) {
      router.push('/login');
      return;
    }

    setBusy(true);
    setError('');
    setMessage('');
    try {
      await deleteFile(token, fileId);
      setMessage('File deleted');
      await refreshFiles();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Delete failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="h-full px-6 py-6 text-[#0C4763]">
      <div className="mx-auto h-full w-full space-y-6">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-[#3D92CB]">SecureDrop</p>
            <h1 className="mt-3 text-4xl font-semibold">Your files</h1>
            <p className="mt-2 text-slate-600">Manage uploads, downloads, sharing, and updates from one workspace.</p>
          </div>
        </div>

        {error ? <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}
        {message ? <p className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</p> : null}

        <section className="grid gap-6 lg:grid-cols-[1.3fr_0.7fr]">
          <div className="rounded-3xl bg-white p-6 shadow-[0_18px_50px_rgba(12,71,99,0.12)]">
            <div className="flex items-center justify-between gap-4">
              <h2 className="text-xl font-semibold">File list</h2>
              <label className="cursor-pointer rounded-full bg-[#3D92CB] px-4 py-2 text-sm font-semibold text-white">
                Upload file
                <input className="hidden" type="file" onChange={onUpload} disabled={busy} />
              </label>
            </div>

            <div className="mt-6 overflow-hidden rounded-2xl border border-slate-200">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-slate-500">
                  <tr>
                    <th className="px-4 py-3">Name</th>
                    <th className="px-4 py-3">Size</th>
                    <th className="px-4 py-3">Uploaded</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {formattedFiles.map((file) => (
                    <tr key={file.id} className="border-t border-slate-200">
                      <td className="px-4 py-3 font-medium">{file.name}</td>
                      <td className="px-4 py-3">{file.sizeLabel}</td>
                      <td className="px-4 py-3">{file.uploadedLabel}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-2">
                          <button
                            className="rounded-full border border-[#0C4763] px-3 py-1 text-xs font-semibold"
                            onClick={() => onDownload(file.id, file.name)}
                            disabled={busy}
                          >
                            Download
                          </button>
                          <button
                            className="rounded-full border border-[#3D92CB] px-3 py-1 text-xs font-semibold text-[#3D92CB]"
                            onClick={() => openShareLinkModal(file)}
                            disabled={busy}
                          >
                            Share link
                          </button>
                          <button
                            className="rounded-full border border-[#6DBB48] px-3 py-1 text-xs font-semibold text-[#2E7D32]"
                            onClick={() => void openShareUsersModal(file)}
                            disabled={busy}
                          >
                            Share users
                          </button>
                          <button
                            className="rounded-full border border-amber-500 px-3 py-1 text-xs font-semibold text-amber-700"
                            onClick={() => openRenameModal(file)}
                            disabled={busy}
                          >
                            Rename
                          </button>
                          <button
                            className="rounded-full border border-red-500 px-3 py-1 text-xs font-semibold text-red-600"
                            onClick={() => onDelete(file.id)}
                            disabled={busy}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {formattedFiles.length === 0 ? (
                    <tr>
                      <td className="px-4 py-6 text-slate-500" colSpan={4}>
                        No files yet. Upload your first file.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>

          <div className="space-y-6">
            <div className="rounded-3xl bg-[#AECFD5] p-6">
              <h2 className="text-xl font-semibold text-[#0C4763]">Upload zone</h2>
              <p className="mt-2 text-sm text-slate-700">Drag and drop files here or browse from your device.</p>
              <div
                {...getRootProps()}
                className="mt-5 rounded-2xl border-2 border-dashed border-[#3D92CB] bg-white/70 p-8 text-center text-sm font-medium text-slate-600"
              >
                <input {...getInputProps()} />
                {isDragActive ? 'Drop the file to upload' : 'Drop files here or click to browse'}
              </div>
            </div>

            <div className="rounded-3xl bg-white p-6 shadow-[0_18px_50px_rgba(12,71,99,0.12)]">
              <h2 className="text-xl font-semibold">Transfer progress</h2>
              <div className="mt-4 space-y-3 text-sm">
                <div>
                  <div className="mb-1 flex justify-between">
                    <span>Last transfer</span>
                    <span>{progress}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-slate-100">
                    <div className="h-2 rounded-full bg-[#6DBB48] transition-all" style={{ width: `${progress}%` }} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      {shareLinkModal.open ? (
        <div className="fixed inset-0 z-40 grid place-items-center bg-slate-900/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
            <h3 className="text-lg font-semibold">Create share link</h3>
            <p className="mt-1 text-sm text-slate-600">{shareLinkModal.fileName}</p>
            <form className="mt-4 space-y-4" onSubmit={submitShareLink}>
              <label className="block text-sm font-medium text-slate-700">
                Expiry (minutes)
                <input
                  className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2"
                  type="number"
                  min={1}
                  value={shareLinkModal.expiresInMinutes}
                  onChange={(event) =>
                    setShareLinkModal((current) => ({
                      ...current,
                      expiresInMinutes: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="block text-sm font-medium text-slate-700">
                Password (optional)
                <input
                  className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2"
                  type="text"
                  minLength={4}
                  value={shareLinkModal.password}
                  onChange={(event) =>
                    setShareLinkModal((current) => ({
                      ...current,
                      password: event.target.value,
                    }))
                  }
                />
              </label>
              <div className="flex justify-end gap-2">
                <button
                  className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold"
                  type="button"
                  onClick={() => setShareLinkModal(CLOSED_SHARE_LINK_MODAL)}
                >
                  Cancel
                </button>
                <button
                  className="rounded-full bg-[#0C4763] px-4 py-2 text-sm font-semibold text-white"
                  type="submit"
                  disabled={busy}
                >
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {shareUsersModal.open ? (
        <div className="fixed inset-0 z-40 grid place-items-center bg-slate-900/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
            <h3 className="text-lg font-semibold">Share with users</h3>
            <p className="mt-1 text-sm text-slate-600">{shareUsersModal.fileName}</p>
            <form className="mt-4 space-y-4" onSubmit={submitShareUsers}>
              <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
                <input
                  type="checkbox"
                  checked={shareUsersModal.shareWithAllUsers}
                  onChange={(event) =>
                    setShareUsersModal((current) => ({
                      ...current,
                      shareWithAllUsers: event.target.checked,
                    }))
                  }
                />
                Share with all users
              </label>
              <label className="block text-sm font-medium text-slate-700">
                Recipients
                <select
                  className="mt-1 h-32 w-full rounded-xl border border-slate-300 px-3 py-2"
                  multiple
                  disabled={shareUsersModal.shareWithAllUsers || availableUsers.length === 0}
                  value={shareUsersModal.recipientUsernames}
                  onChange={(event) =>
                    setShareUsersModal((current) => ({
                      ...current,
                      recipientUsernames: Array.from(event.target.selectedOptions, (option) => option.value),
                    }))
                  }
                >
                  {availableUsers.map((username) => (
                    <option key={username} value={username}>
                      {username}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm font-medium text-slate-700">
                Permission
                <select
                  className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2"
                  value={shareUsersModal.permission}
                  onChange={(event) =>
                    setShareUsersModal((current) => ({
                      ...current,
                      permission: event.target.value as SharePermission,
                    }))
                  }
                >
                  <option value="view">view</option>
                  <option value="download">download</option>
                </select>
              </label>
              <div className="flex justify-end gap-2">
                <button
                  className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold"
                  type="button"
                  onClick={() => setShareUsersModal(CLOSED_SHARE_USERS_MODAL)}
                >
                  Cancel
                </button>
                <button
                  className="rounded-full bg-[#0C4763] px-4 py-2 text-sm font-semibold text-white"
                  type="submit"
                  disabled={busy}
                >
                  Share
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {uploadShareModal.open ? (
        <div className="fixed inset-0 z-40 grid place-items-center bg-slate-900/40 p-4">
          <div className="w-full max-w-xl rounded-2xl bg-white p-6 shadow-xl">
            <h3 className="text-lg font-semibold">Upload complete: share now</h3>
            <p className="mt-1 text-sm text-slate-600">Choose sharing options for {uploadShareModal.fileName}</p>
            <form className="mt-4 space-y-5" onSubmit={submitUploadShareOptions}>
              <section className="rounded-xl border border-slate-200 p-4">
                <h4 className="text-sm font-semibold text-slate-800">Share with users</h4>
                <label className="mt-3 flex items-center gap-2 text-sm font-medium text-slate-700">
                  <input
                    type="checkbox"
                    checked={uploadShareModal.shareWithAllUsers}
                    onChange={(event) =>
                      setUploadShareModal((current) => ({
                        ...current,
                        shareWithAllUsers: event.target.checked,
                      }))
                    }
                  />
                  Share with all users
                </label>
                <label className="mt-3 block text-sm font-medium text-slate-700">
                  Recipients
                  <select
                    className="mt-1 h-32 w-full rounded-xl border border-slate-300 px-3 py-2"
                    multiple
                    disabled={uploadShareModal.shareWithAllUsers || availableUsers.length === 0}
                    value={uploadShareModal.recipientUsernames}
                    onChange={(event) =>
                      setUploadShareModal((current) => ({
                        ...current,
                        recipientUsernames: Array.from(event.target.selectedOptions, (option) => option.value),
                      }))
                    }
                  >
                    {availableUsers.map((username) => (
                      <option key={username} value={username}>
                        {username}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="mt-3 block text-sm font-medium text-slate-700">
                  Permission
                  <select
                    className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2"
                    value={uploadShareModal.permission}
                    onChange={(event) =>
                      setUploadShareModal((current) => ({
                        ...current,
                        permission: event.target.value as SharePermission,
                      }))
                    }
                  >
                    <option value="view">view</option>
                    <option value="download">download</option>
                  </select>
                </label>
              </section>

              <section className="rounded-xl border border-slate-200 p-4">
                <label className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                  <input
                    type="checkbox"
                    checked={uploadShareModal.createShareLink}
                    onChange={(event) =>
                      setUploadShareModal((current) => ({
                        ...current,
                        createShareLink: event.target.checked,
                      }))
                    }
                  />
                  Create share link
                </label>
                <label className="mt-3 block text-sm font-medium text-slate-700">
                  Expiry (minutes)
                  <input
                    className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2"
                    type="number"
                    min={1}
                    disabled={!uploadShareModal.createShareLink}
                    value={uploadShareModal.expiresInMinutes}
                    onChange={(event) =>
                      setUploadShareModal((current) => ({
                        ...current,
                        expiresInMinutes: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="mt-3 block text-sm font-medium text-slate-700">
                  Password (optional)
                  <input
                    className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2"
                    type="text"
                    minLength={4}
                    disabled={!uploadShareModal.createShareLink}
                    value={uploadShareModal.password}
                    onChange={(event) =>
                      setUploadShareModal((current) => ({
                        ...current,
                        password: event.target.value,
                      }))
                    }
                  />
                </label>
              </section>

              <div className="flex justify-end gap-2">
                <button
                  className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold"
                  type="button"
                  onClick={() => {
                    setUploadShareModal(CLOSED_UPLOAD_SHARE_MODAL);
                    setMessage('Upload completed. Sharing skipped.');
                  }}
                >
                  Skip
                </button>
                <button
                  className="rounded-full bg-[#0C4763] px-4 py-2 text-sm font-semibold text-white"
                  type="submit"
                  disabled={busy}
                >
                  Apply sharing
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {renameModal.open ? (
        <div className="fixed inset-0 z-40 grid place-items-center bg-slate-900/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
            <h3 className="text-lg font-semibold">Rename file</h3>
            <p className="mt-1 text-sm text-slate-600">Current: {renameModal.currentName}</p>
            <form className="mt-4 space-y-4" onSubmit={submitRename}>
              <label className="block text-sm font-medium text-slate-700">
                New file name
                <input
                  className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2"
                  type="text"
                  value={renameModal.newName}
                  onChange={(event) =>
                    setRenameModal((current) => ({
                      ...current,
                      newName: event.target.value,
                    }))
                  }
                />
              </label>
              <div className="flex justify-end gap-2">
                <button
                  className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold"
                  type="button"
                  onClick={() => setRenameModal(CLOSED_RENAME_MODAL)}
                >
                  Cancel
                </button>
                <button
                  className="rounded-full bg-[#0C4763] px-4 py-2 text-sm font-semibold text-white"
                  type="submit"
                  disabled={busy}
                >
                  Update
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </main>
  );
}
