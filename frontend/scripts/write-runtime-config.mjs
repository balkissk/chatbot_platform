import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

const outputPath = join(process.cwd(), 'dist', 'frontend', 'browser', 'config.js');

const config = {
  apiBaseUrl: process.env.PUBLIC_API_BASE_URL || process.env.API_BASE_URL || process.env.BACKEND_BASE_URL || undefined,
  frontendBaseUrl: process.env.PUBLIC_FRONTEND_BASE_URL || process.env.FRONTEND_BASE_URL || process.env.FRONTEND_URL || undefined,
};

const entries = Object.fromEntries(
  Object.entries(config).filter(([, value]) => value),
);

mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(
  outputPath,
  `window.__CHATBOT_FACTORY_CONFIG__=${JSON.stringify(entries)};\n`,
);
