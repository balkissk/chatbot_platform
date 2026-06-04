import { PLATFORM_ID, inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../services/auth';


export const roleGuard: CanActivateFn = route => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const platformId = inject(PLATFORM_ID);
  const roles = route.data?.['roles'] as string[] | undefined;

  if (!isPlatformBrowser(platformId)) {
    return true;
  }

  if (!roles || auth.hasRole(roles)) {
    return true;
  }

  const user = auth.currentUser();
  return router.createUrlTree([auth.homeForRole(user?.role || 'end_user')]);
};
