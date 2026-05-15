"use client";

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import { isApiError, register } from '@/lib/api';

const registerSchema = z
  .object({
    username: z.string().min(3, 'Username must be at least 3 characters'),
    password: z.string().min(8, 'Password must be at least 8 characters'),
    confirmPassword: z.string().min(8, 'Confirm password is required'),
  })
  .refine((values) => values.password === values.confirmPassword, {
    path: ['confirmPassword'],
    message: 'Passwords do not match',
  });

type RegisterFormValues = z.infer<typeof registerSchema>;

export default function RegisterPage() {
  const router = useRouter();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [cooldownSeconds, setCooldownSeconds] = useState(0);
  const {
    register: bind,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      username: '',
      password: '',
      confirmPassword: '',
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

    window.history.replaceState({}, '', '/register');
    setError('Detected an insecure form submission URL. Please register again.');
  }, []);

  async function onSubmit(values: RegisterFormValues) {
    setError('');

    setLoading(true);
    try {
      await register(values.username.trim(), values.password);
      router.push('/login');
    } catch (requestError) {
      if (isApiError(requestError) && requestError.statusCode === 429) {
        const retryAfter = requestError.retryAfterSeconds && requestError.retryAfterSeconds > 0
          ? requestError.retryAfterSeconds
          : 30;
        setCooldownSeconds(retryAfter);
        setError(`Too many registration attempts. Please wait ${retryAfter} seconds and try again.`);
      } else {
        setError(requestError instanceof Error ? requestError.message : 'Registration failed');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#FDFDFD] px-6 py-10 text-[#0C4763]">
      <div className="mx-auto max-w-md rounded-3xl bg-white p-8 shadow-[0_18px_50px_rgba(12,71,99,0.12)]">
        <p className="text-sm font-semibold uppercase tracking-[0.25em] text-[#3D92CB]">SecureDrop</p>
        <h1 className="mt-3 text-3xl font-semibold">Create account</h1>
        <p className="mt-2 text-sm text-slate-600">Register to start uploading files.</p>

        <form
          className="mt-8 space-y-4"
          noValidate
          onSubmit={handleSubmit(onSubmit)}
        >
          <input
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
            placeholder="Username"
            {...bind('username')}
          />
          {errors.username ? <p className="text-sm text-red-600">{errors.username.message}</p> : null}
          <input
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
            placeholder="Password"
            type="password"
            {...bind('password')}
          />
          {errors.password ? <p className="text-sm text-red-600">{errors.password.message}</p> : null}
          <input
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
            placeholder="Confirm password"
            type="password"
            {...bind('confirmPassword')}
          />
          {errors.confirmPassword ? <p className="text-sm text-red-600">{errors.confirmPassword.message}</p> : null}
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <button
            type="submit"
            className="w-full rounded-2xl bg-[#6DBB48] px-4 py-3 font-semibold text-white"
            disabled={loading || cooldownSeconds > 0}
          >
            {loading
              ? 'Creating account...'
              : cooldownSeconds > 0
                ? `Try again in ${cooldownSeconds}s`
                : 'Register'}
          </button>
        </form>
      </div>
    </main>
  );
}
