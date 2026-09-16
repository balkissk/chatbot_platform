export interface RuntimeConfig {
  apiBaseUrl?: string;
  frontendBaseUrl?: string;
}

declare global {
  interface Window {
    __CHATBOT_FACTORY_CONFIG__?: RuntimeConfig;
  }
}

const localApiBaseUrl = 'http://localhost:8000';
const azureFrontendBaseUrl = 'https://chatbot-factory-frontend-balkis-a4dchke0bucchbgk.francecentral-01.azurewebsites.net';
const azureApiBaseUrl = 'https://chatbot-factory-api-balkis-hkfhh2adh8hzhkbu.francecentral-01.azurewebsites.net';

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

function productionApiBaseUrl() {
  if (typeof window === 'undefined') return undefined;
  return trimTrailingSlash(window.location.origin) === azureFrontendBaseUrl ? azureApiBaseUrl : undefined;
}

export function apiBaseUrl() {
  return trimTrailingSlash(runtimeConfig().apiBaseUrl || viteEnvValue('VITE_BACKEND_BASE_URL') || productionApiBaseUrl() || localApiBaseUrl);
}

export function frontendBaseUrl() {
  if (typeof window !== 'undefined') {
    return trimTrailingSlash(runtimeConfig().frontendBaseUrl || viteEnvValue('VITE_FRONTEND_BASE_URL') || window.location.origin);
  }

  return trimTrailingSlash(runtimeConfig().frontendBaseUrl || viteEnvValue('VITE_FRONTEND_BASE_URL') || 'http://localhost:4200');
}
