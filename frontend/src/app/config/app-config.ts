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

function viteEnvValue(key: string) {
  try {
    const meta = import.meta as unknown as { env?: Record<string, string | undefined> };
    return meta.env?.[key];
  } catch {
    return undefined;
  }
}

function runtimeConfig(): RuntimeConfig {
  if (typeof window === 'undefined') return {};
  return window.__CHATBOT_FACTORY_CONFIG__ || {};
}

function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, '');
}

export function apiBaseUrl() {
  return trimTrailingSlash(runtimeConfig().apiBaseUrl || viteEnvValue('VITE_BACKEND_BASE_URL') || localApiBaseUrl);
}

export function frontendBaseUrl() {
  if (typeof window !== 'undefined') {
    return trimTrailingSlash(runtimeConfig().frontendBaseUrl || viteEnvValue('VITE_FRONTEND_BASE_URL') || window.location.origin);
  }

  return trimTrailingSlash(runtimeConfig().frontendBaseUrl || viteEnvValue('VITE_FRONTEND_BASE_URL') || 'http://localhost:4200');
}
