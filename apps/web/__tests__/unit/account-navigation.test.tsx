import { fireEvent, render, screen } from '@testing-library/react';
import { signOut, useSession } from 'next-auth/react';
import { TopBar } from '@/components/ui/TopBar';
import { SessionErrorGuard } from '@/components/providers/SessionErrorGuard';

jest.mock('next/navigation', () => ({ usePathname: () => '/courses' }));
jest.mock('next-auth/react', () => ({ useSession: jest.fn(), signOut: jest.fn() }));

beforeEach(() => {
  jest.clearAllMocks();
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: jest.fn(() => ({ matches: false })),
  });
});

it('offers sign out to an authenticated learner', () => {
  (useSession as jest.Mock).mockReturnValue({ data: { user: { name: 'Learner' } } });
  render(<TopBar />);
  fireEvent.click(screen.getByRole('button', { name: /sign out/i }));
  expect(signOut).toHaveBeenCalledWith({ callbackUrl: '/login' });
});

it('does not offer sign out without a session', () => {
  (useSession as jest.Mock).mockReturnValue({ data: null });
  render(<TopBar />);
  expect(screen.queryByRole('button', { name: /sign out/i })).not.toBeInTheDocument();
});

it('ends the browser session when refresh is rejected', () => {
  (useSession as jest.Mock).mockReturnValue({ data: { error: 'RefreshAccessTokenError' } });
  render(<SessionErrorGuard />);
  expect(signOut).toHaveBeenCalledWith({ callbackUrl: '/login' });
});
