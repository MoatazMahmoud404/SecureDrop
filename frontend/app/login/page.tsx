"use client";

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import { clearPending2FA, isApiError, login, setAuthTokens, setPending2FA } from '@/lib/api';

const loginSchema = z.object({
  username: z.string().min(3, 'Username must be at least 3 characters'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [cooldownSeconds, setCooldownSeconds] = useState(0);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      username: '',
      password: '',
    },
  });

  useEffect(() => {
    if (cooldownSeconds <= 0) {
      return;
    }
    const timer = window.setInterval(() => {
      setCooldownSeconds((current) => (current > 1 ? current - 1 : 0));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [cooldownSeconds]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const searchParams = new URLSearchParams(window.location.search);
    const hasSensitiveQuery =
      searchParams.has('username') ||
      searchParams.has('password') ||
      searchParams.has('confirmPassword');

    if (!hasSensitiveQuery) {
      return;
    }

    window.history.replaceState({}, '', '/login');
    setError('Detected an insecure form submission URL. Please login again.');
  }, []);

  async function onSubmit(values: LoginFormValues) {
    setError('');
    setLoading(true);
    try {
      const username = values.username.trim();
      const result = await login(username, values.password);
      if (result.requires_2fa) {
        setPending2FA(result.temp_token, username);
        router.push('/login-2fa');
        return;
      }

      clearPending2FA();
      setAuthTokens({
        accessToken: result.access_token,
        refreshToken: result.refresh_token,
      });
      router.push('/dashboard');
    } catch (requestError) {
      if (isApiError(requestError)) {
        if (requestError.statusCode === 429) {
          const retryAfter = requestError.retryAfterSeconds && requestError.retryAfterSeconds > 0
            ? requestError.retryAfterSeconds
            : 30;
          setCooldownSeconds(retryAfter);
          setError(`Too many login attempts. Please wait ${retryAfter} seconds and try again.`);
        } else if (requestError.statusCode === 423) {
          setError('Account temporarily locked after repeated failed attempts. Please try again later.');
        } else {
          setError(requestError.message || 'Login failed');
        }
      } else {
        const fallback = requestError instanceof Error ? requestError.message : 'Login failed';
        setError(fallback);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#FDFDFD] px-6 py-10 text-[#0C4763]">
      <div className="mx-auto max-w-md rounded-3xl bg-white p-8 shadow-[0_18px_50px_rgba(12,71,99,0.12)]">
        <p className="text-sm font-semibold uppercase tracking-[0.25em] text-[#3D92CB]">SecureDrop</p>
        <h1 className="mt-3 text-3xl font-semibold">Sign in</h1>
        <p className="mt-2 text-sm text-slate-600">Authenticate to access your files. If 2FA is enabled, you will be asked for an OTP code next.</p>

        <form
          className="mt-8 space-y-4"
          noValidate
          onSubmit={handleSubmit(onSubmit)}
        >
          <input
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
            placeholder="Username"
            {...register('username')}
          />
          {errors.username ? <p className="text-sm text-red-600">{errors.username.message}</p> : null}
          <input
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
            placeholder="Password"
            type="password"
            {...register('password')}
          />
          {errors.password ? <p className="text-sm text-red-600">{errors.password.message}</p> : null}
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <button
            type="submit"
            className="w-full rounded-2xl bg-[#3D92CB] px-4 py-3 font-semibold text-white"
            disabled={loading || cooldownSeconds > 0}
          >
            {loading
              ? 'Signing in...'
              : cooldownSeconds > 0
                ? `Try again in ${cooldownSeconds}s`
                : 'Login'}
          </button>
        </form>
      </div>
    </main>
  );
}
