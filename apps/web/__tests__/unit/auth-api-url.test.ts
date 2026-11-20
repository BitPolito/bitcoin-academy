describe('authentication API address', () => {
  const originalEnv = { ...process.env };
  const originalFetch = global.fetch;

  afterEach(() => {
    process.env = { ...originalEnv };
    global.fetch = originalFetch;
    jest.resetModules();
  });

  it.each([
    ['http://api:8000/api', 'http://browser:8000/api', 'http://api:8000/api'],
    ['', 'http://browser:8000/api', 'http://browser:8000/api'],
    ['', '', 'http://legacy:8000/api'],
  ])('uses the configured address for login and refresh', async (internal, browser, expected) => {
    process.env.API_BASE_URL = internal;
    process.env.NEXT_PUBLIC_API_BASE_URL = browser;
    process.env.NEXT_PUBLIC_API_URL = 'http://legacy:8000';
    jest.resetModules();
    const { authOptions, refreshAccessTokenSingleFlight } = await import('@/lib/auth/config');
    const mockFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        user: { id: 'learner', email: 'learner@example.com' },
        tokens: { access_token: 'access', refresh_token: 'refresh' },
        access_token: 'new-access',
      }),
    });
    global.fetch = mockFetch;
    const provider = authOptions.providers[0] as unknown as {
      options: {
        authorize: (credentials: { email: string; password: string }) => Promise<unknown>;
      };
    };
    await provider.options.authorize({ email: 'learner@example.com', password: 'password' });
    expect(mockFetch).toHaveBeenNthCalledWith(1, expected + '/auth/login', expect.any(Object));
    await refreshAccessTokenSingleFlight({ refreshToken: 'refresh' });
    expect(mockFetch).toHaveBeenNthCalledWith(2, expected + '/auth/refresh', expect.any(Object));
  });
});
