export interface RuntimeConfig {
  apiBaseUrl?: string;
  frontendBaseUrl?: string;
}

declare global {
  interface Window {
    __CHATBOT_FACTORY_CONFIG__?: RuntimeConfig;
  }
}

const localApiBaseUrl = 'http://127.0.0.1:8000';

function runtimeConfig(): RuntimeConfig {
  if (typeof window === 'undefined') return {};
  return window.__CHATBOT_FACTORY_CONFIG__ || {};
}

function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, '');
}

export function apiBaseUrl() {
  return trimTrailingSlash(runtimeConfig().apiBaseUrl || localApiBaseUrl);
}

export function frontendBaseUrl() {
  if (typeof window !== 'undefined') {
    return trimTrailingSlash(runtimeConfig().frontendBaseUrl || window.location.origin);
  }

  return trimTrailingSlash(runtimeConfig().frontendBaseUrl || 'http://localhost:4200');
}
