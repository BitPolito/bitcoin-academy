/**
 * Integration tests for authentication flow
 */
import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { signIn, useSession } from 'next-auth/react';
import { useRouter, useSearchParams } from 'next/navigation';

// Mock modules
jest.mock('next-auth/react', () => {
  const originalModule = jest.requireActual('next-auth/react');
  return {
    ...originalModule,
    signIn: jest.fn(),
    signOut: jest.fn(),
    useSession: jest.fn(),
  };
});

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useSearchParams: jest.fn(),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const LoginPage = require('../../src/app/(auth)/login/page').default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const SignupPage = require('../../src/app/(auth)/signup/page').default;

global.fetch = jest.fn();

describe('Authentication Flow Integration', () => {
  const mockRouter = {
    push: jest.fn(),
    refresh: jest.fn(),
    replace: jest.fn(),
  };

  const mockSearchParams = {
    get: jest.fn().mockReturnValue(null),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue(mockRouter);
    (useSearchParams as jest.Mock).mockReturnValue(mockSearchParams);
    (useSession as jest.Mock).mockReturnValue({ data: null, status: 'unauthenticated' });
    (global.fetch as jest.Mock).mockReset();
  });

  describe('Complete Registration and Login Flow', () => {
    it('allows a user to register and automatically log in', async () => {
      // Mock successful registration
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          user: {
            id: 'new-user-id',
            email: 'newuser@example.com',
            display_name: 'New User',
            role: 'student',
          },
          tokens: {
            access_token: 'new-access-token',
            refresh_token: 'new-refresh-token',
            token_type: 'bearer',
            expires_in: 1800,
          },
        }),
      });

      // Mock successful auto-login after registration
      (signIn as jest.Mock).mockResolvedValue({ ok: true });

      render(<SignupPage />);

      // Fill out registration form
      await userEvent.type(screen.getByLabelText(/display name/i), 'New User');
      await userEvent.type(screen.getByLabelText(/email/i), 'newuser@example.com');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'SecurePass123');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'SecurePass123');

      // Submit form
      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      // Verify API call
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/auth/register'),
          expect.objectContaining({
            method: 'POST',
            body: expect.stringContaining('newuser@example.com'),
          })
        );
      });

      // Verify auto-login
      await waitFor(() => {
        expect(signIn).toHaveBeenCalledWith(
          'credentials',
          expect.objectContaining({
            email: 'newuser@example.com',
            password: 'SecurePass123',
          })
        );
      });

      // Verify redirect
      await waitFor(() => {
        expect(mockRouter.push).toHaveBeenCalledWith('/dashboard');
      });
    });

    it('allows an existing user to log in', async () => {
      (signIn as jest.Mock).mockResolvedValue({ ok: true });

      render(<LoginPage />);

      // Fill out login form
      await userEvent.type(screen.getByLabelText(/email/i), 'existing@example.com');
      await userEvent.type(screen.getByLabelText(/password/i), 'ExistingPass123');

      // Submit form
      fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

      // Verify login call
      await waitFor(() => {
        expect(signIn).toHaveBeenCalledWith(
          'credentials',
          expect.objectContaining({
            email: 'existing@example.com',
            password: 'ExistingPass123',
            redirect: false,
          })
        );
      });

      // Verify redirect
      await waitFor(() => {
        expect(mockRouter.push).toHaveBeenCalledWith('/dashboard');
      });
    });
  });

  describe('Error Handling', () => {
    it('handles login failure gracefully', async () => {
      (signIn as jest.Mock).mockResolvedValue({
        ok: false,
        error: 'Invalid email or password',
      });

      render(<LoginPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'wrong@example.com');
      await userEvent.type(screen.getByLabelText(/password/i), 'WrongPass123');

      fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

      await waitFor(() => {
        expect(screen.getByText(/invalid/i)).toBeInTheDocument();
      });

      // Should not redirect
      expect(mockRouter.push).not.toHaveBeenCalled();
    });

    it('handles registration failure for duplicate email', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 409,
        json: async () => ({
          detail: 'A user with this email already exists',
        }),
      });

      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'duplicate@example.com');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'SecurePass123');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'SecurePass123');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByText(/already exists/i)).toBeInTheDocument();
      });

      // Should not attempt login
      expect(signIn).not.toHaveBeenCalled();
    });

    it('handles network errors during registration', async () => {
      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('Network error'));

      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'SecurePass123');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'SecurePass123');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByText(/unexpected error/i)).toBeInTheDocument();
      });
    });
  });

  describe('Session Expired Flow', () => {
    it('shows session expired message and allows re-login', async () => {
      mockSearchParams.get.mockImplementation((key: string) => {
        if (key === 'error') return 'SessionExpired';
        if (key === 'callbackUrl') return '/courses';
        return null;
      });

      (signIn as jest.Mock).mockResolvedValue({ ok: true });

      render(<LoginPage />);

      // Session expired message should be visible
      expect(screen.getByText(/session has expired/i)).toBeInTheDocument();

      // User should be able to log in again
      await userEvent.type(screen.getByLabelText(/email/i), 'user@example.com');
      await userEvent.type(screen.getByLabelText(/password/i), 'Password123');

      fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

      await waitFor(() => {
        expect(signIn).toHaveBeenCalledWith(
          'credentials',
          expect.objectContaining({
            callbackUrl: '/courses',
          })
        );
      });
    });
  });

  describe('Navigation Between Auth Pages', () => {
    it('has link from login to signup page', () => {
      render(<LoginPage />);

      const signupLink = screen.getByRole('link', { name: /create an account/i });
      expect(signupLink).toHaveAttribute('href', '/signup');
    });

    it('has link from signup to login page', () => {
      render(<SignupPage />);

      const loginLink = screen.getByRole('link', { name: /sign in instead/i });
      expect(loginLink).toHaveAttribute('href', '/login');
    });
  });

  describe('Form Validation Feedback', () => {
    it('clears errors when user starts typing', async () => {
      render(<LoginPage />);

      // Trigger validation error
      fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

      await waitFor(() => {
        expect(screen.getByText(/email is required/i)).toBeInTheDocument();
      });

      // Start typing
      await userEvent.type(screen.getByLabelText(/email/i), 't');

      // Submit again to revalidate
      fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

      await waitFor(() => {
        // Should show different error now (invalid format, not empty)
        expect(screen.getByText(/valid email/i)).toBeInTheDocument();
      });
    });
  });
});
