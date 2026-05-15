"use client";

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { clearPending2FA, getPending2FA, isApiError, loginWith2FA, setAuthTokens } from '@/lib/api';

export default function Login2FAPage() {
  const router = useRouter();
  const [otpCode, setOtpCode] = useState('');
  const [username, setUsername] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [cooldownSeconds, setCooldownSeconds] = useState(0);

  useEffect(() => {
    const pending = getPending2FA();
    if (!pending) {
      router.replace('/login');
      return;
    }
    setUsername(pending.username);
  }, [router]);

  useEffect(() => {
    if (cooldownSeconds <= 0) {
      return;
    }
    const timer = window.setInterval(() => {
      setCooldownSeconds((current) => (current > 1 ? current - 1 : 0));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [cooldownSeconds]);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');

    const sanitizedCode = otpCode.trim();
    if (!/^\d{6}$/.test(sanitizedCode)) {
      setError('Enter a valid 6-digit OTP code.');
      return;
    }

    const pending = getPending2FA();
    if (!pending) {
      setError('Your 2FA session expired. Please login again.');
      router.replace('/login');
      return;
    }

    setLoading(true);
    try {
      const tokens = await loginWith2FA(pending.tempToken, sanitizedCode);
      setAuthTokens(tokens);
      clearPending2FA();
      router.push('/dashboard');
    } catch (requestError) {
      if (isApiError(requestError) && requestError.statusCode === 429) {
        const retryAfter = requestError.retryAfterSeconds && requestError.retryAfterSeconds > 0
          ? requestError.retryAfterSeconds
          : 30;
        setCooldownSeconds(retryAfter);
        setError(`Too many OTP attempts. Please wait ${retryAfter} seconds and try again.`);
        return;
      }

      const message = requestError instanceof Error ? requestError.message : 'OTP verification failed';
      setError(message);
      if (message.toLowerCase().includes('expired')) {
        clearPending2FA();
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#FDFDFD] px-6 py-10 text-[#0C4763]">
      <div className="mx-auto max-w-md rounded-3xl bg-white p-8 shadow-[0_18px_50px_rgba(12,71,99,0.12)]">
        <p className="text-sm font-semibold uppercase tracking-[0.25em] text-[#3D92CB]">SecureDrop</p>
        <h1 className="mt-3 text-3xl font-semibold">Two-factor verification</h1>
        <p className="mt-2 text-sm text-slate-600">
          Enter the 6-digit authenticator code for {username || 'your account'}.
        </p>

        <form className="mt-8 space-y-4" onSubmit={onSubmit}>
          <input
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
            placeholder="123456"
            inputMode="numeric"
            maxLength={6}
            value={otpCode}
            onChange={(event) => setOtpCode(event.target.value.replace(/\D/g, ''))}
          />
          {error ? <p className="text-sm text-red-600">{error}</p> : null}

          <button className="w-full rounded-2xl bg-[#3D92CB] px-4 py-3 font-semibold text-white" disabled={loading || cooldownSeconds > 0}>
            {loading
              ? 'Verifying...'
              : cooldownSeconds > 0
                ? `Try again in ${cooldownSeconds}s`
                : 'Verify OTP'}
          </button>

          <button
            type="button"
            className="w-full rounded-2xl border border-slate-300 px-4 py-3 font-semibold text-slate-700"
            onClick={() => {
              clearPending2FA();
              router.push('/login');
            }}
          >
            Back to login
          </button>
        </form>
      </div>
    </main>
  );
}
