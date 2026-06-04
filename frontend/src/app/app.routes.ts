import { Routes } from '@angular/router';
import { ProjectsComponent } from './pages/projects/projects.component';
import { authGuard } from './guards/auth.guard';
import { roleGuard } from './guards/role.guard';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./pages/landing/landing.component')
        .then(m => m.LandingComponent)
  },
  {
    path: 'login',
    loadComponent: () =>
      import('./pages/login/login.component')
        .then(m => m.LoginComponent)
  },
  {
    path: 'register',
    loadComponent: () =>
      import('./pages/register/register.component')
        .then(m => m.RegisterComponent)
  },
  {
    path: 'dashboard',
    canActivate: [authGuard, roleGuard],
    data: { roles: ['admin', 'manager'] },
    loadComponent: () =>
      import('./layouts/dashboard-layout/dashboard-layout.component')
        .then(m => m.DashboardLayoutComponent),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'profile' },
      {
        path: 'profile',
        loadComponent: () =>
          import('./pages/profile/profile.component')
            .then(m => m.ProfileComponent)
      },
      { path: 'projects', component: ProjectsComponent },
      {
        path: 'projects/:projectId/chatbots',
        loadComponent: () =>
          import('./pages/chatbots/chatbots.component')
            .then(m => m.ChatbotsComponent)
      },
      {
        path: 'projects/:projectId/chatbots/:chatbotId/versions',
        loadComponent: () =>
          import('./pages/versions/versions.component')
            .then(m => m.VersionsComponent)
      },
      {
        path: 'projects/:projectId/chatbots/:chatbotId/flow',
        loadComponent: () =>
          import('./pages/flow-builder/flow-builder.component')
            .then(m => m.FlowBuilderComponent)
      },
      {
        path: 'projects/:projectId/chatbots/:chatbotId/flow/test',
        loadComponent: () =>
          import('./pages/flow-test/flow-test.component')
            .then(m => m.FlowTestComponent)
      },
      {
        path: 'projects/:projectId/chatbots/:chatbotId/knowledge',
        loadComponent: () =>
          import('./pages/knowledge-base/knowledge-base.component')
            .then(m => m.KnowledgeBaseComponent)
      },
      {
        path: 'projects/:projectId',
        loadComponent: () =>
          import('./pages/project-overview/project-overview.component')
            .then(m => m.ProjectOverviewComponent)
      }
    ]
  },
  {
    path: 'admin',
    canActivate: [authGuard, roleGuard],
    data: { roles: ['admin'] },
    loadComponent: () =>
      import('./layouts/dashboard-layout/dashboard-layout.component')
        .then(m => m.DashboardLayoutComponent),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      {
        path: 'dashboard',
        loadComponent: () =>
          import('./pages/admin-dashboard/admin-dashboard.component')
            .then(m => m.AdminDashboardComponent)
      },
      {
        path: 'conversations',
        loadComponent: () =>
          import('./pages/admin-conversations/admin-conversations.component')
            .then(m => m.AdminConversationsComponent)
      },
      {
        path: 'users',
        loadComponent: () =>
          import('./pages/admin-users/admin-users.component')
            .then(m => m.AdminUsersComponent)
      }
    ]
  },
  {
    path: 'public-chat/:chatbotId',
    loadComponent: () =>
      import('./pages/public-chat/public-chat.component')
        .then(m => m.PublicChatComponent)
  },
  { path: 'chat/:chatbotId', redirectTo: 'public-chat/:chatbotId' },
  { path: '**', redirectTo: 'login' }
];
