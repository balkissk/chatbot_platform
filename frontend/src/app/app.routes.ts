import { Routes } from '@angular/router';
import { ProjectsComponent } from './pages/projects/projects.component';

export const routes: Routes = [
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
  }
];
