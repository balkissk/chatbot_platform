import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnDestroy, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import {
  LucideActivity,
  LucideBell,
  LucideChevronRight,
  LucideCircleAlert,
  LucideCircleCheck,
  LucideClock3,
  LucideDatabase,
  LucideGitBranch,
  LucideLayers,
  LucideListChecks,
  LucideRadio,
  LucideRotateCcw,
  LucideSearchCheck,
  LucideSparkles,
  LucideTriangleAlert
} from '@lucide/angular';
import { ApiService } from '../../services/api';
import { ToastService } from '../../services/toast.service';

@Component({
  selector: 'app-project-overview',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterModule,
    LucideActivity,
    LucideBell,
    LucideChevronRight,
    LucideCircleAlert,
    LucideCircleCheck,
    LucideClock3,
    LucideDatabase,
    LucideGitBranch,
    LucideLayers,
    LucideListChecks,
    LucideRadio,
    LucideRotateCcw,
    LucideSearchCheck,
    LucideSparkles,
    LucideTriangleAlert
  ],
  templateUrl: './project-overview.component.html',
  styleUrls: ['./project-overview.component.css']
})
export class ProjectOverviewComponent implements OnInit, OnDestroy {
  projectId!: number;
  project = signal<any | null>(null);
  chatbots = signal<any[]>([]);
  workspaceDashboard = signal<any | null>(null);
  conversations = signal<any[]>([]);
  loading = signal(false);
  chatbotsLoading = signal(false);
  workspaceLoading = signal(false);
  workspaceLoaded = signal(false);
  conversationsLoading = signal(false);
  saving = signal(false);
  restoring = signal(false);
  error = signal('');
  workspaceError = signal('');
  message = signal('');
  selectedQualitySignal = signal<any | null>(null);

  editing = false;
  editName = '';
  editDescription = '';

  private isBrowser: boolean;
  private nonCriticalLoadTimer?: ReturnType<typeof setTimeout>;
  private destroyed = false;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private api: ApiService,
    private toast: ToastService,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    if (!this.isBrowser) return;
    this.projectId = Number(this.route.snapshot.paramMap.get('projectId'));
    this.hydrateCachedShellData();
    this.loadProject();
    this.loadChatbots();
    this.scheduleNonCriticalWorkspaceData();
  }

  ngOnDestroy() {
    this.destroyed = true;
    if (this.nonCriticalLoadTimer) {
      clearTimeout(this.nonCriticalLoadTimer);
    }
  }

  private hydrateCachedShellData() {
    const cachedChatbots = this.api.getCachedChatbotsByProject(this.projectId);
    if (cachedChatbots) {
      this.chatbots.set(cachedChatbots);
    }
  }

  private scheduleNonCriticalWorkspaceData() {
    const start = () => {
      if (!this.destroyed) {
        this.loadWorkspaceDashboard();
      }
    };
    const browserWindow = window as any;

    if (typeof browserWindow.requestAnimationFrame === 'function') {
      browserWindow.requestAnimationFrame(() => {
        if (typeof browserWindow.requestIdleCallback === 'function') {
          browserWindow.requestIdleCallback(start, { timeout: 800 });
          return;
        }
        this.nonCriticalLoadTimer = setTimeout(start, 0);
      });
      return;
    }

    this.nonCriticalLoadTimer = setTimeout(start, 0);
  }

  loadProject() {
    this.loading.set(true);
    this.error.set('');

    this.api.getProject(this.projectId).subscribe({
      next: project => {
        this.project.set(project);
        this.editName = project.name;
        this.editDescription = project.description || '';
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load project');
        this.loading.set(false);
      }
    });
  }

  loadChatbots() {
    this.chatbotsLoading.set(true);
    this.api.getChatbotsByProject(this.projectId).subscribe({
      next: chatbots => {
        this.chatbots.set(chatbots);
        this.chatbotsLoading.set(false);
      },
      error: () => {
        this.chatbots.set([]);
        this.chatbotsLoading.set(false);
      }
    });
  }

  loadWorkspaceDashboard() {
    this.workspaceLoading.set(true);
    this.workspaceLoaded.set(false);
    this.workspaceError.set('');
    this.api.getProjectWorkspaceDashboard(this.projectId).subscribe({
      next: dashboard => {
        this.workspaceDashboard.set(dashboard);
        this.workspaceLoading.set(false);
        this.workspaceLoaded.set(true);
      },
      error: () => {
        this.workspaceDashboard.set(null);
        this.workspaceError.set('Could not load the project overview. Please try again.');
        this.workspaceLoading.set(false);
        this.workspaceLoaded.set(true);
      }
    });
  }

  loadConversations(chatbotId: number) {
    this.conversationsLoading.set(true);
    this.api.getChatbotConversations(chatbotId, { limit: 5, offset: 0 }).subscribe({
      next: conversations => {
        this.conversations.set(conversations || []);
        this.conversationsLoading.set(false);
      },
      error: () => {
        this.conversations.set([]);
        this.conversationsLoading.set(false);
      }
    });
  }

  startEdit() {
    const project = this.project();
    if (!project) return;

    this.editing = true;
    this.editName = project.name;
    this.editDescription = project.description || '';
    this.message.set('');
  }

  cancelEdit() {
    this.editing = false;
    this.message.set('');
  }

  saveProject() {
    const name = this.editName.trim();
    if (!name) {
      this.error.set('Project name is required');
      return;
    }

    this.saving.set(true);
    this.error.set('');
    this.message.set('');

    this.api.updateProject(this.projectId, {
      name,
      description: this.editDescription.trim() || 'No description'
    }).subscribe({
      next: project => {
        this.project.set(project);
        this.editName = project.name;
        this.editDescription = project.description || '';
        this.editing = false;
        this.message.set('Project updated');
        this.saving.set(false);
        this.loadWorkspaceDashboard();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not update project');
        this.saving.set(false);
      }
    });
  }

  goBack() {
    this.router.navigate(['/dashboard/projects']);
  }

  goToChatbots() {
    this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots']);
  }

  newAssistant() {
    if (this.isArchived()) return;
    this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots'], {
      queryParams: { create: 1 }
    });
  }

  isArchived() {
    return String(this.project()?.status || '').toLowerCase() === 'archived';
  }

  lifecycleLabel() {
    const value = String(this.project()?.status || 'active').toLowerCase();
    return value ? value.charAt(0).toUpperCase() + value.slice(1) : 'Active';
  }

  healthLabel() {
    return this.project()?.health_status || this.workspaceDashboard()?.project?.health_status || '';
  }

  liveLabel() {
    return this.versionInfo()?.published_version ? 'Live' : 'Not live';
  }

  restoreProject() {
    if (!this.isArchived() || this.restoring()) return;
    this.restoring.set(true);
    this.error.set('');
    this.api.restoreProject(this.projectId).subscribe({
      next: project => {
        this.project.set(project);
        this.restoring.set(false);
        this.toast.success('Project restored successfully');
        this.loadWorkspaceDashboard();
      },
      error: () => {
        this.restoring.set(false);
        this.toast.error('Could not restore project. Please try again.');
      }
    });
  }

  chatbotStatus(bot: any) {
    return bot.is_active ? 'Active' : 'Inactive';
  }

  firstChatbot() {
    return this.chatbots()[0];
  }

  noAssistantConfirmed() {
    return !this.chatbotsLoading() && !this.firstChatbot();
  }

  dashboardDataLoading() {
    return this.workspaceLoading() && !this.workspaceDashboard();
  }

  lastUpdated() {
    const project = this.project();
    return this.workspaceDashboard()?.project?.last_activity_at || project?.last_activity_at || project?.created_at;
  }

  workspaceSummary() {
    return this.workspaceDashboard()?.summary || {
      total_assistants: this.project()?.assistant_count || 0,
      published_assistants: this.project()?.published_assistant_count || 0,
      draft_only_assistants: this.project()?.draft_only_assistant_count || 0
    };
  }

  operationsWidgets() {
    return this.workspaceDashboard()?.metrics || [];
  }

  metricByLabel(label: string) {
    const normalized = label.toLowerCase();
    return this.operationsWidgets().find((metric: any) => String(metric.label || '').toLowerCase() === normalized);
  }

  metricValue(label: string) {
    const metric = this.metricByLabel(label);
    return this.formatKpiValue(metric?.value, metric?.suffix, metric?.prefix);
  }

  metricHelper(label: string, fallback: string) {
    return this.metricByLabel(label)?.helper || fallback;
  }

  healthStripItems() {
    const version = this.versionInfo();
    const liveVersion = version?.published_version ? `v${version.published_version.version_number}` : 'None';
    const draftVersion = version?.latest_version ? `v${version.latest_version.version_number}` : 'None';
    const runtimeSuccess = this.metricByLabel('Runtime Success Rate');
    const knowledgeCoverage = this.metricByLabel('Knowledge Answer Coverage');
    const requestCount = this.metricByLabel('Runtime Requests');

    return [
      {
        label: 'Runtime success',
        value: this.formatKpiValue(runtimeSuccess?.value, runtimeSuccess?.suffix, runtimeSuccess?.prefix),
        helper: runtimeSuccess?.helper || 'No runtime window available',
        tone: runtimeSuccess?.tone || 'neutral'
      },
      {
        label: 'Knowledge coverage',
        value: this.formatKpiValue(knowledgeCoverage?.value, knowledgeCoverage?.suffix, knowledgeCoverage?.prefix),
        helper: knowledgeCoverage?.helper || 'No knowledge usage yet',
        tone: knowledgeCoverage?.tone || 'neutral'
      },
      {
        label: 'Requests',
        value: this.formatKpiValue(requestCount?.value, requestCount?.suffix, requestCount?.prefix),
        helper: requestCount?.helper || 'All tracked runtime requests',
        tone: requestCount?.tone || 'neutral'
      },
      {
        label: 'Versions',
        value: `${draftVersion} draft / ${liveVersion} live`,
        helper: version?.rollback_available ? 'Rollback available' : 'Rollback unavailable',
        tone: liveVersion === 'None' ? 'warning' : 'success'
      },
      {
        label: 'Blockers',
        value: String(this.groupedRuntimeEvents().length),
        helper: this.groupedRuntimeEvents().length ? 'Open items need review' : 'No active blockers',
        tone: this.groupedRuntimeEvents().length ? 'danger' : 'success'
      }
    ];
  }

  formatKpiValue(value: unknown, suffix = '', prefix = '') {
    return value === undefined || value === null || value === '' ? '-' : `${prefix}${value}${suffix || ''}`;
  }

  validationItems() {
    return this.workspaceDashboard()?.readiness_center || [];
  }

  knowledgeGaps() {
    return this.workspaceDashboard()?.knowledge_gaps || [];
  }

  recommendations() {
    return this.workspaceDashboard()?.recommended_actions || [];
  }

  runtimeEvents() {
    return this.workspaceDashboard()?.operational_alerts || [];
  }

  groupedRuntimeEvents() {
    const grouped = new Map<string, any>();
    for (const event of this.runtimeEvents()) {
      const key = [
        event.affected_assistant_id || event.affected_assistant_name || 'project',
        event.category || event.type || 'alert',
        event.title || 'Alert',
        event.message || ''
      ].join('|');
      const existing = grouped.get(key);
      if (existing) {
        existing.count += 1;
        if (event.created_at && (!existing.created_at || new Date(event.created_at) > new Date(existing.created_at))) {
          existing.created_at = event.created_at;
        }
      } else {
        grouped.set(key, { ...event, count: 1 });
      }
    }
    return Array.from(grouped.values());
  }

  replayRows() {
    return this.workspaceDashboard()?.quality_signals || [];
  }

  visibleReplayRows() {
    return this.replayRows().slice(0, 4);
  }

  versionInfo() {
    return this.workspaceDashboard()?.release_state || {};
  }

  statusLabel(status: string) {
    return status === 'ready' ? 'Ready' : 'Needs attention';
  }

  readinessProgress() {
    const items = this.validationItems();
    if (!items.length) return { ready: 0, total: 0, percent: 0 };
    const ready = items.filter((item: any) => item.status === 'ready').length;
    return {
      ready,
      total: items.length,
      percent: Math.round((ready / items.length) * 100)
    };
  }

  knowledgeSummary() {
    const ready = this.validationItems().find((item: any) => String(item.label || '').toLowerCase().includes('knowledge'));
    return ready?.status === 'ready' ? 'Knowledge sources are searchable.' : 'Knowledge coverage needs attention.';
  }

  releaseCardTone(status: 'draft' | 'live' | 'rollback') {
    return status;
  }

  signalSeverity(signal: any) {
    return signal?.severity || (signal?.issue_type === 'Runtime error' ? 'critical' : 'warning');
  }

  actionLabel(action: string | null | undefined) {
    const labels: Record<string, string> = {
      knowledge: 'Open Knowledge Base',
      analytics: 'Open Analytics',
      versions: 'Open Versions',
      flow: 'Open Flow Builder'
    };
    return labels[action || ''] || 'Review';
  }

  handleRecommendation(item: any) {
    const action = item?.action;
    if (!action) return;
    const targetAssistantId = item.affected_assistant_id || this.firstChatbot()?.id;
    if (!targetAssistantId) return;
    const base = ['/dashboard/projects', this.projectId, 'chatbots', targetAssistantId];
    if (action === 'knowledge') {
      this.router.navigate([...base, 'knowledge']);
    } else if (action === 'analytics') {
      this.router.navigate([...base, 'analytics']);
    } else if (action === 'versions') {
      this.router.navigate([...base, 'versions']);
    } else if (action === 'flow') {
      this.router.navigate([...base, 'flow']);
    }
  }

  openQualitySignal(signal: any) {
    this.selectedQualitySignal.set(signal);
  }

  closeQualitySignal() {
    this.selectedQualitySignal.set(null);
  }

  versionActionLabel() {
    const version = this.versionInfo();
    if (!version?.latest_version) return 'Open Versions';
    if (version?.latest_version?.status === 'draft') return 'Review Changes';
    return 'Open Versions';
  }

  versionAction() {
    this.goToFirstChatbot('versions');
  }

  goToFirstChatbot(path: 'flow' | 'knowledge' | 'analytics' | 'test' | 'versions') {
    if (this.isArchived() && (path === 'flow' || path === 'knowledge')) return;
    const bot = this.firstChatbot();
    if (!bot) return;
    const base = ['/dashboard/projects', this.projectId, 'chatbots', bot.id];
    if (path === 'versions') {
      this.router.navigate([...base, 'versions']);
      return;
    }
    if (path === 'test') {
      this.router.navigate([...base, 'flow', 'test']);
      return;
    }
    this.router.navigate([...base, path]);
  }
}
