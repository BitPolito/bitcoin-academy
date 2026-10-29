import type { JWT } from 'next-auth/jwt';

import { authOptions, refreshAccessTokenSingleFlight } from '@/lib/auth/config';

const mockFetch = jest.fn();
global.fetch = mockFetch as unknown as typeof fetch;

describe('refresh token single-flight', () => {
  beforeEach(() => mockFetch.mockReset());

  it('shares one rotation request between concurrent callers', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: 'access-2', refresh_token: 'refresh-2' }),
    });
    const token = {
      accessToken: 'access-1',
      refreshToken: 'refresh-1',
      accessTokenExpires: 0,
    } as JWT;

    const [first, second] = await Promise.all([
      refreshAccessTokenSingleFlight(token),
      refreshAccessTokenSingleFlight(token),
    ]);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(first.refreshToken).toBe('refresh-2');
    expect(second).toEqual(first);
  });
});

describe('login rate-limit feedback', () => {
  const authorize = (
    authOptions.providers[0] as unknown as {
      options: {
        authorize: (credentials: { email: string; password: string }) => Promise<unknown>;
      };
    }
  ).options.authorize;

  beforeEach(() => mockFetch.mockReset());

  it.each([
    [{ error: { code: 'ACCOUNT_LOCKED', message: 'Private diagnostic' } }, 'AccountLocked'],
    [{ error: { code: 'RATE_LIMIT_EXCEEDED' } }, 'TooManyRequests'],
  ])('maps the backend error to safe login feedback', async (body, expected) => {
    mockFetch.mockResolvedValue({ ok: false, status: 429, json: async () => body });
    await expect(
      authorize({ email: 'learner@example.com', password: 'Password123!' })
    ).rejects.toThrow(expected);
  });
});
