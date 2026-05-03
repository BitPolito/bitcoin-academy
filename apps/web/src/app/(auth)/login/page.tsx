'use client';

import { Suspense } from 'react';
import { signIn } from 'next-auth/react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { FormEvent, useState } from 'react';

interface FormErrors {
  email?: string;
  password?: string;
  general?: string;
}

const inputBase =
  'appearance-none block w-full px-3 py-2 border rounded-md bg-white dark:bg-[#0a0a0a] text-[#001CE0] dark:text-white placeholder-[rgba(0,28,224,0.25)] dark:placeholder-white/25 focus:outline-none focus:ring-1 focus:ring-blue-dark focus:border-blue-dark sm:text-sm transition-colors';

const inputBorder = 'border-[rgba(0,28,224,0.18)] dark:border-[rgba(255,255,255,0.22)]';
const inputBorderErr = 'border-err dark:border-red-400';

const labelClass = 'block font-mono text-[11px] tracking-wide uppercase text-[#001CE0]/70 dark:text-white/60';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get('callbackUrl') || '/courses';
  const errorParam = searchParams.get('error');

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({});

  const sessionError =
    errorParam === 'SessionExpired' ? 'Your session has expired. Please log in again.' : null;

  const validateForm = (): boolean => {
    const newErrors: FormErrors = {};
    if (!email) {
      newErrors.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      newErrors.email = 'Please enter a valid email address';
    }
    if (!password) {
      newErrors.password = 'Password is required';
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrors({});
    if (!validateForm()) return;
    setIsLoading(true);
    try {
      const result = await signIn('credentials', {
        email,
        password,
        redirect: false,
        callbackUrl,
      });
      if (result?.error) {
        setErrors({ general: result.error });
      } else if (result?.ok) {
        router.push(callbackUrl);
        router.refresh();
      }
    } catch {
      setErrors({ general: 'An unexpected error occurred. Please try again.' });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="mt-8 bg-white dark:bg-[#0f0f0f] py-8 px-4 b-thin sm:rounded-lg sm:px-10">
      <h2 className="text-center text-xl font-bold ink dark:text-white mb-6 font-mono tracking-tight">
        Sign in
      </h2>

      {sessionError && (
        <div className="mb-4 p-3 rounded bg-amber-50 dark:bg-[rgba(255,180,0,0.07)] border border-amber-200 dark:border-amber-600/30">
          <p className="text-sm text-amber-800 dark:text-amber-400">{sessionError}</p>
        </div>
      )}

      {errors.general && (
        <div className="mb-4 p-3 rounded bg-red-50 dark:bg-[rgba(255,0,0,0.06)] border border-red-200 dark:border-red-700/40">
          <p className="text-sm text-red-600 dark:text-red-400">{errors.general}</p>
        </div>
      )}

      <form className="space-y-5" onSubmit={handleSubmit} noValidate>
        <div>
          <label htmlFor="email" className={labelClass}>
            Email address
          </label>
          <div className="mt-1.5">
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={`${inputBase} ${errors.email ? inputBorderErr : inputBorder}`}
              placeholder="you@example.com"
              aria-invalid={errors.email ? 'true' : 'false'}
              aria-describedby={errors.email ? 'email-error' : undefined}
            />
          </div>
          {errors.email && (
            <p className="mt-1 font-mono text-[11px] text-err dark:text-red-400" id="email-error" role="alert">
              {errors.email}
            </p>
          )}
        </div>

        <div>
          <label htmlFor="password" className={labelClass}>
            Password
          </label>
          <div className="mt-1.5">
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={`${inputBase} ${errors.password ? inputBorderErr : inputBorder}`}
              placeholder="••••••••"
              aria-invalid={errors.password ? 'true' : 'false'}
              aria-describedby={errors.password ? 'password-error' : undefined}
            />
          </div>
          {errors.password && (
            <p className="mt-1 font-mono text-[11px] text-err dark:text-red-400" id="password-error" role="alert">
              {errors.password}
            </p>
          )}
        </div>

        <div>
          <button
            type="submit"
            disabled={isLoading}
            className="btn-primary w-full justify-center"
          >
            {isLoading ? (
              <>
                <svg
                  className="animate-spin h-4 w-4"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Signing in...
              </>
            ) : (
              'Sign in'
            )}
          </button>
        </div>
      </form>

      <div className="mt-6">
        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-[rgba(0,28,224,0.12)] dark:border-[rgba(255,255,255,0.12)]" />
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-2 bg-white dark:bg-[#0f0f0f] font-mono text-[11px] tracking-wide text-[#001CE0]/40 dark:text-white/30">
              Don&apos;t have an account?
            </span>
          </div>
        </div>

        <div className="mt-4">
          <Link href="/signup" className="btn-ghost w-full justify-center">
            Create an account
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="mt-8 bg-white dark:bg-[#0f0f0f] py-8 px-4 b-thin sm:rounded-lg sm:px-10 min-h-[320px]" />}>
      <LoginForm />
    </Suspense>
  );
}
