import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { AuthService } from './auth';


export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  return next(req.clone({ withCredentials: true })).pipe(
    catchError(error => {
      if (error.status === 401 && error.error?.detail === 'Token expired') {
        auth.expireSession();
      }
      return throwError(() => error);
    })
  );
};
