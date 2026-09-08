import { apiBaseUrl } from './app-config';

describe('app-config', () => {
  it('defaults the local API base URL to localhost', () => {
    expect(apiBaseUrl()).toBe('http://localhost:8000');
  });
});
