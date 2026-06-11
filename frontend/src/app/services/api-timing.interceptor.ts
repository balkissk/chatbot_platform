import { HttpInterceptorFn } from '@angular/common/http';
import { tap } from 'rxjs';

function isDevelopmentHost() {
  if (typeof window === 'undefined') return false;
  return ['localhost', '127.0.0.1'].includes(window.location.hostname);
}

export const apiTimingInterceptor: HttpInterceptorFn = (req, next) => {
  if (!isDevelopmentHost()) {
    return next(req);
  }

  const startedAt = performance.now();
  return next(req).pipe(
    tap({
      next: () => {
        const elapsed = Math.round(performance.now() - startedAt);
        console.info(`[api] ${req.method} ${req.urlWithParams} ${elapsed}ms`);
      },
      error: () => {
        const elapsed = Math.round(performance.now() - startedAt);
        console.warn(`[api] ${req.method} ${req.urlWithParams} failed after ${elapsed}ms`);
      }
    })
  );
};
