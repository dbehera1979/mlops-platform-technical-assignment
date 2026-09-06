import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';
import { AppShellComponent } from './shared/components/app-shell/app-shell.component';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./features/login/login.component').then((m) => m.LoginComponent),
  },
  {
    path: '',
    component: AppShellComponent,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'models' },
      {
        path: 'models',
        loadComponent: () =>
          import('./features/model-inventory/model-inventory.component').then((m) => m.ModelInventoryComponent),
      },
      {
        path: 'models/:modelId',
        loadComponent: () =>
          import('./features/model-version-detail/model-version-detail.component').then(
            (m) => m.ModelVersionDetailComponent
          ),
      },
      {
        path: 'deployments',
        loadComponent: () =>
          import('./features/deployments/deployment-list.component').then((m) => m.DeploymentListComponent),
      },
      {
        path: 'monitoring',
        loadComponent: () =>
          import('./features/monitoring/monitoring-dashboard.component').then((m) => m.MonitoringDashboardComponent),
      },
      {
        path: 'events',
        loadComponent: () =>
          import('./features/event-timeline/event-timeline.component').then((m) => m.EventTimelineComponent),
      },
    ],
  },
  { path: '**', redirectTo: 'models' },
];
