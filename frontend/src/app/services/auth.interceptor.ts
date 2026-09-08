import { HttpContextToken, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { Observable, catchError, finalize, shareReplay, switchMap, throwError } from 'rxjs';

import { AuthService } from './auth';


const RETRIED_AFTER_REFRESH = new HttpContextToken<boolean>(() => false);
let refreshRequest$: Observable<unknown> | null = null;

function requestPath(req: HttpRequest<unknown>) {
  try {
    return new URL(req.url).pathname;
  } catch {
    return req.url.split('?')[0];
  }
}

function isExcludedFromRefresh(req: HttpRequest<unknown>) {
  const path = requestPath(req);
  return [
    '/auth/login',
    '/auth/refresh',
    '/auth/logout',
    '/auth/forgot-password',
    '/auth/reset-password',
    '/auth/register'
  ].some(authPath => path.endsWith(authPath)) || path.includes('/public/');
}

function canAttemptRefresh(req: HttpRequest<unknown>, auth: AuthService) {
  return !req.context.get(RETRIED_AFTER_REFRESH)
    && !isExcludedFromRefresh(req)
    && auth.hasStoredSession();
}

function refreshOnce(auth: AuthService) {
  if (!refreshRequest$) {
    refreshRequest$ = auth.refreshSession().pipe(
      finalize(() => {
        refreshRequest$ = null;
      }),
      shareReplay({ bufferSize: 1, refCount: false })
    );
  }
  return refreshRequest$;
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const credentialedRequest = req.clone({ withCredentials: true });

  return next(credentialedRequest).pipe(
    catchError(error => {
      if (error.status !== 401 || !canAttemptRefresh(credentialedRequest, auth)) {
        return throwError(() => error);
      }

      return refreshOnce(auth).pipe(
        catchError(refreshError => {
          auth.expireSession();
          return throwError(() => refreshError);
        }),
        switchMap(() => next(credentialedRequest.clone({
          withCredentials: true,
          context: credentialedRequest.context.set(RETRIED_AFTER_REFRESH, true)
        })).pipe(
          catchError(retryError => {
            if (retryError.status === 401) {
              auth.expireSession();
            }
            return throwError(() => retryError);
          })
        ))
      );
    })
  );
};
