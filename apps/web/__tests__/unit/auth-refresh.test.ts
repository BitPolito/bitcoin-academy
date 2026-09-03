import type { JWT } from 'next-auth/jwt';

import { refreshAccessTokenSingleFlight } from '@/lib/auth/config';

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
