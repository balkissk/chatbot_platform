import {
  AngularNodeAppEngine,
  createNodeRequestHandler,
  isMainModule,
  writeResponseToNodeResponse,
} from '@angular/ssr/node';
import express from 'express';
import { join } from 'node:path';

const browserDistFolder = join(import.meta.dirname, '../browser');

const app = express();
app.set('trust proxy', true);

const angularApp = new AngularNodeAppEngine();

function jsString(value: string) {
  return JSON.stringify(value);
}

app.get('/config.js', (_req, res) => {
  const apiBaseUrl = process.env['PUBLIC_API_BASE_URL'] || process.env['API_BASE_URL'] || 'http://127.0.0.1:8000';
  const frontendBaseUrl = process.env['PUBLIC_FRONTEND_BASE_URL'] || process.env['FRONTEND_URL'] || '';

  res
    .type('application/javascript')
    .set('Cache-Control', 'no-store')
    .send(
      `window.__CHATBOT_FACTORY_CONFIG__={apiBaseUrl:${jsString(apiBaseUrl)},frontendBaseUrl:${jsString(frontendBaseUrl)}};`,
    );
});

/**
 * Example Express Rest API endpoints can be defined here.
 * Uncomment and define endpoints as necessary.
 *
 * Example:
 * ```ts
 * app.get('/api/{*splat}', (req, res) => {
 *   // Handle API request
 * });
 * ```
 */

/**
 * Serve static files from /browser
 */
app.use(
  express.static(browserDistFolder, {
    maxAge: '1y',
    immutable: true,
    index: false,
    redirect: false,
    setHeaders: (res, path) => {
      if (path.endsWith('index.csr.html') || path.endsWith('config.js')) {
        res.setHeader('Cache-Control', 'no-store');
        return;
      }

      if (/\.(?:js|css|woff2|webp|png|jpg|jpeg|svg|ico)$/i.test(path)) {
        res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
      }
    },
  }),
);

/**
 * Handle all other requests by rendering the Angular application.
 */
app.use((req, res, next) => {
  angularApp
    .handle(req)
    .then((response) =>
      response ? writeResponseToNodeResponse(response, res) : next(),
    )
    .catch(next);
});

/**
 * Start the server if this module is the main entry point, or it is ran via PM2.
 * The server listens on the port defined by the `PORT` environment variable, or defaults to 4000.
 */
if (isMainModule(import.meta.url) || process.env['pm_id']) {
  const port = Number(process.env['PORT'] || 4000);
  const host = process.env['HOST'] || '0.0.0.0';

  app.listen(port, host, (error) => {
    if (error) {
      throw error;
    }

    console.log(`Node Express server listening on http://${host}:${port}`);
  });
}

/**
 * Request handler used by the Angular CLI (for dev-server and during build) or Firebase Cloud Functions.
 */
export const reqHandler = createNodeRequestHandler(app);
