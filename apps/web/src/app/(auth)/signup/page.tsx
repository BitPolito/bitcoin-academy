'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { signIn } from 'next-auth/react';
import { FormEvent, useState } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface FormErrors {
  email?: string;
  password?: string;
  confirmPassword?: string;
  displayName?: string;
  general?: string;
}

const inputBase =
  'appearance-none block w-full px-3 py-2 border rounded-md bg-white dark:bg-[#0a0a0a] text-[#001CE0] dark:text-white placeholder-[rgba(0,28,224,0.25)] dark:placeholder-white/25 focus:outline-none focus:ring-1 focus:ring-blue-dark focus:border-blue-dark sm:text-sm transition-colors';

const inputBorder = 'border-[rgba(0,28,224,0.18)] dark:border-[rgba(255,255,255,0.22)]';
const inputBorderErr = 'border-err dark:border-red-400';

const labelClass = 'block font-mono text-[11px] tracking-wide uppercase text-[#001CE0]/70 dark:text-white/60';

export default function SignupPage() {
  const router = useRouter();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({});

  const validateForm = (): boolean => {
    const newErrors: FormErrors = {};

    if (!email) {
      newErrors.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      newErrors.email = 'Please enter a valid email address';
    }

    if (!password) {
      newErrors.password = 'Password is required';
    } else if (password.length < 8) {
      newErrors.password = 'Password must be at least 8 characters long';
    } else if (!/[A-Z]/.test(password)) {
      newErrors.password = 'Password must contain at least one uppercase letter';
    } else if (!/[a-z]/.test(password)) {
      newErrors.password = 'Password must contain at least one lowercase letter';
    } else if (!/\d/.test(password)) {
      newErrors.password = 'Password must contain at least one digit';
    }

    if (!confirmPassword) {
      newErrors.confirmPassword = 'Please confirm your password';
    } else if (password !== confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    if (displayName && displayName.length < 2) {
      newErrors.displayName = 'Display name must be at least 2 characters long';
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
      const registerResponse = await fetch(`${API_URL}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, display_name: displayName || null }),
      });

      if (!registerResponse.ok) {
        const error = await registerResponse.json();
        if (registerResponse.status === 409) {
          setErrors({ email: 'A user with this email already exists' });
        } else if (registerResponse.status === 400) {
          setErrors({ general: error.detail || 'Invalid input data' });
        } else {
          setErrors({ general: error.detail || 'Registration failed' });
        }
        return;
      }

      const result = await signIn('credentials', {
        email,
        password,
        redirect: false,
        callbackUrl: '/dashboard',
      });

      if (result?.error) {
        router.push('/login?message=Registration successful. Please log in.');
      } else if (result?.ok) {
        router.push('/dashboard');
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
        Create account
      </h2>

      {errors.general && (
        <div className="mb-4 p-3 rounded bg-red-50 dark:bg-[rgba(255,0,0,0.06)] border border-red-200 dark:border-red-700/40" role="alert">
          <p className="text-sm text-red-600 dark:text-red-400">{errors.general}</p>
        </div>
      )}

      <form className="space-y-5" onSubmit={handleSubmit} noValidate>
        <div>
          <label htmlFor="displayName" className={labelClass}>
            Display name{' '}
            <span className="normal-case text-[#001CE0]/35 dark:text-white/30 tracking-normal">(optional)</span>
          </label>
          <div className="mt-1.5">
            <input
              id="displayName"
              name="displayName"
              type="text"
              autoComplete="name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className={`${inputBase} ${errors.displayName ? inputBorderErr : inputBorder}`}
              placeholder="Satoshi Nakamoto"
              aria-invalid={errors.displayName ? 'true' : 'false'}
              aria-describedby={errors.displayName ? 'displayName-error' : undefined}
            />
          </div>
          {errors.displayName && (
            <p className="mt-1 font-mono text-[11px] text-err dark:text-red-400" id="displayName-error" role="alert">
              {errors.displayName}
            </p>
          )}
        </div>

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
              autoComplete="new-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={`${inputBase} ${errors.password ? inputBorderErr : inputBorder}`}
              placeholder="••••••••"
              aria-invalid={errors.password ? 'true' : 'false'}
              aria-describedby={errors.password ? 'password-error' : 'password-hint'}
            />
          </div>
          {errors.password ? (
            <p className="mt-1 font-mono text-[11px] text-err dark:text-red-400" id="password-error" role="alert">
              {errors.password}
            </p>
          ) : (
            <p className="mt-1 font-mono text-[11px] text-[#001CE0]/40 dark:text-white/30" id="password-hint">
              Min 8 chars · uppercase · lowercase · digit
            </p>
          )}
        </div>

        <div>
          <label htmlFor="confirmPassword" className={labelClass}>
            Confirm password
          </label>
          <div className="mt-1.5">
            <input
              id="confirmPassword"
              name="confirmPassword"
              type="password"
              autoComplete="new-password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className={`${inputBase} ${errors.confirmPassword ? inputBorderErr : inputBorder}`}
              placeholder="••••••••"
              aria-invalid={errors.confirmPassword ? 'true' : 'false'}
              aria-describedby={errors.confirmPassword ? 'confirmPassword-error' : undefined}
            />
          </div>
          {errors.confirmPassword && (
            <p className="mt-1 font-mono text-[11px] text-err dark:text-red-400" id="confirmPassword-error" role="alert">
              {errors.confirmPassword}
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
                Creating account...
              </>
            ) : (
              'Create account'
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
              Already have an account?
            </span>
          </div>
        </div>

        <div className="mt-4">
          <Link href="/login" className="btn-ghost w-full justify-center">
            Sign in instead
          </Link>
        </div>
      </div>
    </div>
  );
}
