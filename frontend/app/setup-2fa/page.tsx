"use client";

import { FormEvent, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { disable2FA, get2FAStatus, getToken, setup2FA, verify2FA } from '@/lib/api';

export default function Setup2FAPage() {
  const router = useRouter();
  const [otpEnabled, setOtpEnabled] = useState(false);
  const [otpSecret, setOtpSecret] = useState('');
  const [qrCodeDataUrl, setQrCodeDataUrl] = useState('');
  const [enableOtpCode, setEnableOtpCode] = useState('');
  const [disableOtpCode, setDisableOtpCode] = useState('');
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [loadingSetup, setLoadingSetup] = useState(false);
  const [loadingEnable, setLoadingEnable] = useState(false);
  const [loadingDisable, setLoadingDisable] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    async function loadStatus() {
      const token = getToken();
      if (!token) {
        router.replace('/login');
        return;
      }

      setLoadingStatus(true);
      try {
        const status = await get2FAStatus(token);
        setOtpEnabled(status.enabled);
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : 'Could not load 2FA status');
      } finally {
        setLoadingStatus(false);
      }
    }

    void loadStatus();
  }, [router]);

  async function handleGenerateSetup() {
    const token = getToken();
    if (!token) {
      router.replace('/login');
      return;
    }

    setLoadingSetup(true);
    setError('');
    setMessage('');
    try {
      const response = await setup2FA(token);
      setOtpSecret(response.otp_secret);
      setQrCodeDataUrl(response.qr_code_data_url);
      setMessage('Scan the QR code and verify using your authenticator app.');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not generate 2FA setup');
    } finally {
      setLoadingSetup(false);
    }
  }

  async function handleEnable(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setMessage('');

    const token = getToken();
    if (!token) {
      router.replace('/login');
      return;
    }

    const sanitizedCode = enableOtpCode.trim();
    if (!otpSecret || !/^\d{6}$/.test(sanitizedCode)) {
      setError('Generate setup first and enter a valid 6-digit OTP code.');
      return;
    }

    setLoadingEnable(true);
    try {
      await verify2FA(token, otpSecret, sanitizedCode);
      setOtpEnabled(true);
      setEnableOtpCode('');
      setOtpSecret('');
      setQrCodeDataUrl('');
      setMessage('2FA enabled successfully. Future logins require OTP.');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not enable 2FA');
    } finally {
      setLoadingEnable(false);
    }
  }

  async function handleDisable(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setMessage('');

    const token = getToken();
    if (!token) {
      router.replace('/login');
      return;
    }

    const sanitizedCode = disableOtpCode.trim();
    if (!/^\d{6}$/.test(sanitizedCode)) {
      setError('Enter a valid 6-digit OTP code to disable 2FA.');
      return;
    }

    setLoadingDisable(true);
    try {
      await disable2FA(token, sanitizedCode);
      setOtpEnabled(false);
      setDisableOtpCode('');
      setMessage('2FA disabled successfully.');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not disable 2FA');
    } finally {
      setLoadingDisable(false);
    }
  }

  return (
    <main className="h-full px-6 py-6 text-[#0C4763]">
      <div className="mx-auto max-w-4xl space-y-6 rounded-3xl bg-white p-8 shadow-[0_18px_50px_rgba(12,71,99,0.12)]">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.25em] text-[#3D92CB]">SecureDrop</p>
          <h1 className="mt-3 text-3xl font-semibold">Two-Factor Authentication</h1>
          <p className="mt-2 text-sm text-slate-600">
            Enable or disable 2FA for your account.
          </p>
        </div>

        {error ? <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}
        {message ? <p className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</p> : null}

        <div className="flex flex-wrap items-center gap-3">
          <span className={`rounded-full px-4 py-2 text-sm font-semibold ${otpEnabled ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
            {loadingStatus ? 'Checking status...' : otpEnabled ? '2FA is enabled' : '2FA is disabled'}
          </span>
          <button
            type="button"
            className="rounded-2xl border border-slate-300 px-4 py-3 font-semibold text-slate-700"
            onClick={() => router.push('/dashboard')}
          >
            Back to dashboard
          </button>
        </div>

        {!otpEnabled ? (
          <div className="space-y-6">
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                className="rounded-2xl bg-[#3D92CB] px-4 py-3 font-semibold text-white"
                onClick={handleGenerateSetup}
                disabled={loadingSetup}
              >
                {loadingSetup ? 'Generating...' : 'Generate QR setup'}
              </button>
            </div>

            {qrCodeDataUrl ? (
              <div className="grid gap-6 md:grid-cols-2">
                <div className="rounded-2xl border border-slate-200 p-4">
                  <h2 className="mb-3 text-lg font-semibold">QR code</h2>
                  <img src={qrCodeDataUrl} alt="2FA QR code" className="max-w-full rounded-xl" />
                </div>

                <div className="rounded-2xl border border-slate-200 p-4">
                  <h2 className="mb-2 text-lg font-semibold">Manual setup key</h2>
                  <p className="mb-3 text-sm text-slate-600">Use this key if your app cannot scan the QR code.</p>
                  <p className="break-all rounded-lg bg-slate-50 p-3 font-mono text-sm">{otpSecret}</p>

                  <form className="mt-4 space-y-3" onSubmit={handleEnable}>
                    <input
                      className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
                      placeholder="Enter 6-digit OTP"
                      inputMode="numeric"
                      maxLength={6}
                      value={enableOtpCode}
                      onChange={(event) => setEnableOtpCode(event.target.value.replace(/\D/g, ''))}
                    />
                    <button
                      className="w-full rounded-2xl bg-[#6DBB48] px-4 py-3 font-semibold text-white"
                      disabled={loadingEnable}
                    >
                      {loadingEnable ? 'Enabling...' : 'Verify and enable 2FA'}
                    </button>
                  </form>
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="rounded-2xl border border-slate-200 p-6">
            <h2 className="text-lg font-semibold">Disable 2FA</h2>
            <p className="mt-2 text-sm text-slate-600">
              To disable 2FA, confirm with a current 6-digit OTP from your authenticator app.
            </p>

            <form className="mt-4 space-y-3" onSubmit={handleDisable}>
              <input
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
                placeholder="Enter current 6-digit OTP"
                inputMode="numeric"
                maxLength={6}
                value={disableOtpCode}
                onChange={(event) => setDisableOtpCode(event.target.value.replace(/\D/g, ''))}
              />
              <button
                className="rounded-2xl bg-red-600 px-4 py-3 font-semibold text-white"
                disabled={loadingDisable}
              >
                {loadingDisable ? 'Disabling...' : 'Disable 2FA'}
              </button>
            </form>
          </div>
        )}
      </div>
    </main>
  );
}
