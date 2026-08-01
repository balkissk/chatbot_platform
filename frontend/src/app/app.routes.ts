import { Routes } from '@angular/router';
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
    path: 'privacy-policy',
    loadComponent: () =>
      import('./pages/privacy-policy/privacy-policy.component')
        .then(m => m.PrivacyPolicyComponent)
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
      {
        path: 'projects',
        loadComponent: () =>
          import('./pages/projects/projects.component')
            .then(m => m.ProjectsComponent)
      },
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
        path: 'projects/:projectId/chatbots/:chatbotId/analytics',
        loadComponent: () =>
          import('./pages/chatbot-analytics/chatbot-analytics.component')
            .then(m => m.ChatbotAnalyticsComponent)
      },
      {
        path: 'projects/:projectId/chatbots/:chatbotId/conversations',
        loadComponent: () =>
          import('./pages/chatbot-conversations/chatbot-conversations.component')
            .then(m => m.ChatbotConversationsComponent)
      },
      {
        path: 'projects/:projectId/chatbots/:chatbotId/flow',
        loadComponent: () =>
          import('./pages/flow-builder/flow-builder.component')
            .then(m => m.FlowBuilderComponent)
      },
      {
        path: 'projects/:projectId/chatbots/:chatbotId/templates',
        loadComponent: () =>
          import('./pages/template-selection/template-selection.component')
            .then(m => m.TemplateSelectionComponent)
      },
      {
        path: 'projects/:projectId/chatbots/:chatbotId/ai-generator',
        loadComponent: () =>
          import('./pages/ai-generator/ai-generator.component')
            .then(m => m.AiGeneratorComponent)
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
        path: 'projects/:projectId/analytics',
        loadComponent: () =>
          import('./pages/project-analytics/project-analytics.component')
            .then(m => m.ProjectAnalyticsComponent)
      },
      {
        path: 'projects/:projectId/settings',
        loadComponent: () =>
          import('./pages/project-settings/project-settings.component')
            .then(m => m.ProjectSettingsComponent)
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
        path: 'chatbots',
        loadComponent: () =>
          import('./pages/admin-chatbots/admin-chatbots.component')
            .then(m => m.AdminChatbotsComponent)
      },
      {
        path: 'runtime-logs',
        loadComponent: () =>
          import('./pages/admin-runtime-logs/admin-runtime-logs.component')
            .then(m => m.AdminRuntimeLogsComponent)
      },
      {
        path: 'analytics',
        loadComponent: () =>
          import('./pages/admin-analytics/admin-analytics.component')
            .then(m => m.AdminAnalyticsComponent)
      },
      {
        path: 'users',
        loadComponent: () =>
          import('./pages/admin-users/admin-users.component')
            .then(m => m.AdminUsersComponent)
      },
      {
        path: 'audit-logs',
        loadComponent: () =>
          import('./pages/admin-audit-logs/admin-audit-logs.component')
            .then(m => m.AdminAuditLogsComponent)
      },
      {
        path: 'platform-settings',
        loadComponent: () =>
          import('./pages/admin-platform-settings/admin-platform-settings.component')
            .then(m => m.AdminPlatformSettingsComponent)
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
