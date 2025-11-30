/**
 * Unit tests for login page component
 */
import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { signIn } from 'next-auth/react';
import { useRouter, useSearchParams } from 'next/navigation';

// eslint-disable-next-line @typescript-eslint/no-var-requires
const LoginPage = require('../../src/app/(auth)/login/page').default;

// Mock next-auth
jest.mock('next-auth/react', () => ({
  signIn: jest.fn(),
}));

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useSearchParams: jest.fn(),
}));

describe('LoginPage', () => {
  const mockRouter = {
    push: jest.fn(),
    refresh: jest.fn(),
  };

  const mockSearchParams = {
    get: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue(mockRouter);
    (useSearchParams as jest.Mock).mockReturnValue(mockSearchParams);
    mockSearchParams.get.mockReturnValue(null);
  });

  describe('Rendering', () => {
    it('renders login form with all elements', () => {
      render(<LoginPage />);

      expect(screen.getByRole('heading', { name: /sign in/i })).toBeInTheDocument();
      expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /create an account/i })).toBeInTheDocument();
    });

    it('displays session expired message when error param is present', () => {
      mockSearchParams.get.mockImplementation((key: string) => {
        if (key === 'error') return 'SessionExpired';
        return null;
      });

      render(<LoginPage />);

      expect(screen.getByText(/session has expired/i)).toBeInTheDocument();
    });
  });

  describe('Validation', () => {
    it('shows error when email is empty', async () => {
      render(<LoginPage />);

      const submitButton = screen.getByRole('button', { name: /sign in/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/email is required/i)).toBeInTheDocument();
      });
    });

    it('shows error when email format is invalid', async () => {
      render(<LoginPage />);

      const emailInput = screen.getByLabelText(/email/i);
      await userEvent.type(emailInput, 'invalid-email');

      const submitButton = screen.getByRole('button', { name: /sign in/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/valid email/i)).toBeInTheDocument();
      });
    });

    it('shows error when password is empty', async () => {
      render(<LoginPage />);

      const emailInput = screen.getByLabelText(/email/i);
      await userEvent.type(emailInput, 'test@example.com');

      const submitButton = screen.getByRole('button', { name: /sign in/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/password is required/i)).toBeInTheDocument();
      });
    });
  });

  describe('Form Submission', () => {
    it('calls signIn with correct credentials on valid submission', async () => {
      (signIn as jest.Mock).mockResolvedValue({ ok: true });

      render(<LoginPage />);

      const emailInput = screen.getByLabelText(/email/i);
      const passwordInput = screen.getByLabelText(/password/i);

      await userEvent.type(emailInput, 'test@example.com');
      await userEvent.type(passwordInput, 'Password123');

      const submitButton = screen.getByRole('button', { name: /sign in/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(signIn).toHaveBeenCalledWith('credentials', {
          email: 'test@example.com',
          password: 'Password123',
          redirect: false,
          callbackUrl: '/dashboard',
        });
      });
    });

    it('redirects to dashboard on successful login', async () => {
      (signIn as jest.Mock).mockResolvedValue({ ok: true });

      render(<LoginPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/password/i), 'Password123');
      fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

      await waitFor(() => {
        expect(mockRouter.push).toHaveBeenCalledWith('/dashboard');
        expect(mockRouter.refresh).toHaveBeenCalled();
      });
    });

    it('uses callbackUrl from query params', async () => {
      mockSearchParams.get.mockImplementation((key: string) => {
        if (key === 'callbackUrl') return '/courses';
        return null;
      });

      (signIn as jest.Mock).mockResolvedValue({ ok: true });

      render(<LoginPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
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

    it('displays error message on failed login', async () => {
      (signIn as jest.Mock).mockResolvedValue({ ok: false, error: 'Invalid credentials' });

      render(<LoginPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/password/i), 'WrongPassword');
      fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

      await waitFor(() => {
        expect(screen.getByText(/invalid credentials/i)).toBeInTheDocument();
      });
    });

    it('shows loading state while submitting', async () => {
      (signIn as jest.Mock).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({ ok: true }), 100))
      );

      render(<LoginPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/password/i), 'Password123');
      fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

      expect(screen.getByText(/signing in/i)).toBeInTheDocument();
    });

    it('disables button while loading', async () => {
      (signIn as jest.Mock).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({ ok: true }), 100))
      );

      render(<LoginPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/password/i), 'Password123');

      const submitButton = screen.getByRole('button', { name: /sign in/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByRole('button')).toBeDisabled();
      });
    });
  });

  describe('Accessibility', () => {
    it('has accessible form labels', () => {
      render(<LoginPage />);

      expect(screen.getByLabelText(/email/i)).toHaveAccessibleName();
      expect(screen.getByLabelText(/password/i)).toHaveAccessibleName();
    });

    it('marks inputs as invalid when errors occur', async () => {
      render(<LoginPage />);

      fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

      await waitFor(() => {
        expect(screen.getByLabelText(/email/i)).toHaveAttribute('aria-invalid', 'true');
      });
    });
  });
});
