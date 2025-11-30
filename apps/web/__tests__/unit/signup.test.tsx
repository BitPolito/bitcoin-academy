/**
 * Unit tests for signup page component
 */
import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { signIn } from 'next-auth/react';
import { useRouter } from 'next/navigation';

// eslint-disable-next-line @typescript-eslint/no-var-requires
const SignupPage = require('../../src/app/(auth)/signup/page').default;

// Mock next-auth
jest.mock('next-auth/react', () => ({
  signIn: jest.fn(),
}));

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

// Mock fetch
global.fetch = jest.fn();

describe('SignupPage', () => {
  const mockRouter = {
    push: jest.fn(),
    refresh: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue(mockRouter);
    (global.fetch as jest.Mock).mockReset();
  });

  describe('Rendering', () => {
    it('renders signup form with all elements', () => {
      render(<SignupPage />);

      expect(screen.getByRole('heading', { name: /create your account/i })).toBeInTheDocument();
      expect(screen.getByLabelText(/display name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /sign in instead/i })).toBeInTheDocument();
    });

    it('shows password requirements hint', () => {
      render(<SignupPage />);

      expect(screen.getByText(/min 8 characters/i)).toBeInTheDocument();
    });
  });

  describe('Validation', () => {
    it('shows error when email is empty', async () => {
      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/^password$/i), 'ValidPass123');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'ValidPass123');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByText(/email is required/i)).toBeInTheDocument();
      });
    });

    it('shows error when email format is invalid', async () => {
      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'invalid-email');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'ValidPass123');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'ValidPass123');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByText(/valid email/i)).toBeInTheDocument();
      });
    });

    it('shows error when password is too short', async () => {
      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'Short1');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'Short1');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByText(/at least 8 characters/i)).toBeInTheDocument();
      });
    });

    it('shows error when password has no uppercase', async () => {
      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'nouppercase123');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'nouppercase123');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByText(/uppercase letter/i)).toBeInTheDocument();
      });
    });

    it('shows error when password has no lowercase', async () => {
      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'NOLOWERCASE123');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'NOLOWERCASE123');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByText(/lowercase letter/i)).toBeInTheDocument();
      });
    });

    it('shows error when password has no digit', async () => {
      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'NoDigitsHere');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'NoDigitsHere');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByText(/one digit/i)).toBeInTheDocument();
      });
    });

    it('shows error when passwords do not match', async () => {
      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'ValidPass123');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'DifferentPass456');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByText(/do not match/i)).toBeInTheDocument();
      });
    });

    it('shows error when confirm password is empty', async () => {
      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'ValidPass123');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByText(/confirm your password/i)).toBeInTheDocument();
      });
    });

    it('accepts empty display name (optional field)', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          user: { id: '1', email: 'test@example.com', display_name: null, role: 'student' },
          tokens: { access_token: 'token', refresh_token: 'refresh', expires_in: 1800 },
        }),
      });
      (signIn as jest.Mock).mockResolvedValue({ ok: true });

      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'ValidPass123');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'ValidPass123');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalled();
      });
    });
  });

  describe('Form Submission', () => {
    it('calls API with correct data on valid submission', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          user: { id: '1', email: 'test@example.com', display_name: 'Test User', role: 'student' },
          tokens: { access_token: 'token', refresh_token: 'refresh', expires_in: 1800 },
        }),
      });
      (signIn as jest.Mock).mockResolvedValue({ ok: true });

      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/display name/i), 'Test User');
      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'ValidPass123');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'ValidPass123');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/auth/register'),
          expect.objectContaining({
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              email: 'test@example.com',
              password: 'ValidPass123',
              display_name: 'Test User',
            }),
          })
        );
      });
    });

    it('auto-logs in after successful registration', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          user: { id: '1', email: 'test@example.com', display_name: null, role: 'student' },
          tokens: { access_token: 'token', refresh_token: 'refresh', expires_in: 1800 },
        }),
      });
      (signIn as jest.Mock).mockResolvedValue({ ok: true });

      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'ValidPass123');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'ValidPass123');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(signIn).toHaveBeenCalledWith(
          'credentials',
          expect.objectContaining({
            email: 'test@example.com',
            password: 'ValidPass123',
          })
        );
      });
    });

    it('redirects to dashboard after successful registration', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          user: { id: '1', email: 'test@example.com', display_name: null, role: 'student' },
          tokens: { access_token: 'token', refresh_token: 'refresh', expires_in: 1800 },
        }),
      });
      (signIn as jest.Mock).mockResolvedValue({ ok: true });

      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'ValidPass123');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'ValidPass123');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(mockRouter.push).toHaveBeenCalledWith('/dashboard');
      });
    });

    it('shows error when email already exists (409)', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 409,
        json: async () => ({ detail: 'A user with this email already exists' }),
      });

      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'existing@example.com');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'ValidPass123');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'ValidPass123');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByText(/already exists/i)).toBeInTheDocument();
      });
    });

    it('shows error on server error', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Internal server error' }),
      });

      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'ValidPass123');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'ValidPass123');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
      });
    });

    it('shows loading state while submitting', async () => {
      (global.fetch as jest.Mock).mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      );

      render(<SignupPage />);

      await userEvent.type(screen.getByLabelText(/email/i), 'test@example.com');
      await userEvent.type(screen.getByLabelText(/^password$/i), 'ValidPass123');
      await userEvent.type(screen.getByLabelText(/confirm password/i), 'ValidPass123');

      fireEvent.click(screen.getByRole('button', { name: /create account/i }));

      expect(screen.getByText(/creating account/i)).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('has accessible form labels', () => {
      render(<SignupPage />);

      expect(screen.getByLabelText(/email/i)).toHaveAccessibleName();
      expect(screen.getByLabelText(/^password$/i)).toHaveAccessibleName();
      expect(screen.getByLabelText(/confirm password/i)).toHaveAccessibleName();
    });

    it('has password hint for screen readers', () => {
      render(<SignupPage />);

      const passwordInput = screen.getByLabelText(/^password$/i);
      expect(passwordInput).toHaveAttribute('aria-describedby');
    });
  });
});
