import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, HostListener, Inject, OnDestroy, OnInit, PLATFORM_ID, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import {
  LucideActivity,
  LucideArrowRight,
  LucideBot,
  LucideCheckCircle2,
  LucideClock3,
  LucideEllipsis,
  LucideFilter,
  LucideGrid2X2,
  LucideInfo,
  LucideLayoutDashboard,
  LucidePlus,
  LucideRefreshCw,
  LucideRocket,
  LucideSearch,
  LucideShieldCheck,
  LucideSparkles,
  LucideTable2,
  LucideTriangleAlert
} from '@lucide/angular';
import { ApiService } from '../../services/api';
import { AuthService } from '../../services/auth';
import { ToastService } from '../../services/toast.service';
import { ProjectActionsMenuComponent } from './project-actions-menu.component';

@Component({
  selector: 'app-projects',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterModule,
    LucideActivity,
    LucideArrowRight,
    LucideBot,
    LucideCheckCircle2,
    LucideClock3,
    LucideEllipsis,
    LucideFilter,
    LucideGrid2X2,
    LucideInfo,
    LucideLayoutDashboard,
    LucidePlus,
    LucideRefreshCw,
    LucideRocket,
    LucideSearch,
    LucideShieldCheck,
    LucideSparkles,
    LucideTable2,
    LucideTriangleAlert,
    ProjectActionsMenuComponent
  ],
  templateUrl: './projects.component.html',
  styleUrls: ['./projects.component.css']
})
export class ProjectsComponent implements OnInit, OnDestroy {
  projects = signal<any[]>([]);
  summary = signal({
    projects: 0,
    assistants: 0,
    published_assistants: 0,
    draft_only: 0
  });
  loading = signal(false);
  creating = signal(false);
  savingId = signal<number | undefined>(undefined);
  deletingId = signal<number | undefined>(undefined);
  duplicatingId = signal<number | undefined>(undefined);
  archivingId = signal<number | undefined>(undefined);
  restoringId = signal<number | undefined>(undefined);
  hasMore = signal(false);
  totalResults = signal(0);
  loadingMore = signal(false);
  error = signal('');
  message = signal('');
  createModalOpen = signal(false);
  menuProjectId = signal<number | undefined>(undefined);
  menuProject = signal<any | null>(null);
  projectMenuPosition = signal({ top: 0, left: 0 });
  filtersOpen = signal(false);
  filterPosition = signal({ top: 0, left: 0 });
  renameDialogProject = signal<any | null>(null);
  deleteDialogProject = signal<any | null>(null);
  archiveDialogProject = signal<any | null>(null);
  activeFilters = signal({
    status: 'all',
    activity: 'any',
    assistants: 'any'
  });
  viewMode = signal<'grid' | 'table'>('grid');

  search = '';
  sortMode = signal('recent');
  filterStatus = 'all';
  filterActivity = 'any';
  filterAssistants = 'any';
  newProjectName = '';
  newProjectDescription = '';
  editingId?: number;
  editName = '';
  editDescription = '';
  renameName = '';
  renameDescription = '';

  totalProjects = computed(() => this.summary().projects);
  totalAssistants = computed(() => this.summary().assistants);
  publishedAssistants = computed(() => this.summary().published_assistants);
  draftOnlyAssistants = computed(() => this.summary().draft_only);
  knowledgeBasesTotal = computed(() => this.sumProjectFields('knowledge_base_count', 'knowledge_bases_count'));
  versionTotal = computed(() => this.sumProjectFields('version_count', 'versions_count'));
  projectsNeedingPublication = computed(() =>
    this.projects().filter(project => this.assistantCount(project) > 0 && this.publishedCount(project) === 0 && !this.isArchived(project)).length
  );
  emptyProjectCount = computed(() => this.projects().filter(project => this.assistantCount(project) === 0 && !this.isArchived(project)).length);
  archivedProjectCount = computed(() => this.projects().filter(project => this.isArchived(project)).length);
  workspaceHealthState = computed(() => {
    if (!this.projects().length) return 'Empty';
    if (this.projectsNeedingPublication() || this.emptyProjectCount()) return 'Attention';
    return 'Healthy';
  });
  workspaceHealthScore = computed(() => {
    const total = this.projects().filter(project => !this.isArchived(project)).length;
    if (!total) return 0;
    const ready = this.projects().filter(project => !this.isArchived(project) && this.assistantCount(project) > 0 && this.publishedCount(project) > 0).length;
    return Math.round((ready / total) * 100);
  });
  runtimeHealthLabel = computed(() => {
    if (!this.projects().length) return 'No projects';
    if (this.projectsNeedingPublication()) return 'Needs publication';
    if (this.emptyProjectCount()) return 'Setup needed';
    return 'Healthy';
  });
  activeFilterCount = computed(() => {
    const filters = this.activeFilters();
    return Number(filters.status !== 'all') + Number(filters.activity !== 'any') + Number(filters.assistants !== 'any');
  });
  displayedProjects = computed(() => this.sortProjects(this.filterProjects(this.searchProjects(this.projects()))));
  initialLoading = computed(() => this.loading() && this.projects().length === 0 && !this.error());
  refreshing = computed(() => this.loading() && this.projects().length > 0);
  hasCriteria = computed(() => Boolean(this.search.trim()) || this.activeFilterCount() > 0);
  noProjects = computed(() => !this.loading() && !this.error() && this.projects().length === 0 && !this.hasCriteria());
  noResults = computed(() => !this.loading() && !this.error() && this.hasCriteria() && this.displayedProjects().length === 0);
  canRenderProjects = computed(() => this.displayedProjects().length > 0);

  private isBrowser: boolean;
  private searchTimer?: ReturnType<typeof setTimeout>;
  private readonly pageSize = 50;
  private readonly viewModeStorageKey = 'projectsViewMode';
  private page = 1;

  constructor(
    public auth: AuthService,
    private api: ApiService,
    private toast: ToastService,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    if (!this.isBrowser) return;
    this.restoreViewMode();
    this.loadProjects();
  }

  ngOnDestroy() {
    if (this.searchTimer) clearTimeout(this.searchTimer);
  }

  loadProjects(force = false, append = false) {
    if (!this.isBrowser) return;

    if (!append) {
      this.page = 1;
      this.loading.set(true);
    } else {
      this.loadingMore.set(true);
    }
    this.error.set('');

    const requestedPage = append ? this.page + 1 : 1;
    this.api.getProjectsPage({
      search: this.search,
      status: this.backendStatusFilter(),
      assistant_range: this.activeFilters().assistants,
      last_activity_from: this.activityFromDate(),
      sort: this.sortMode(),
      page: requestedPage,
      page_size: this.pageSize
    }).subscribe({
      next: response => {
        const items = response?.items || [];
        this.projects.set(append ? [...this.projects(), ...items] : items);
        this.totalResults.set(Number(response?.total || items.length));
        this.hasMore.set(Boolean(response?.has_next));
        this.page = Number(response?.page || requestedPage);
        this.loading.set(false);
        this.loadingMore.set(false);
      },
      error: err => {
        console.error('Projects load failed', err);
        this.error.set('Projects could not be loaded. Please try again.');
        this.toast.error('Projects could not be loaded. Please try again.');
        this.loading.set(false);
        this.loadingMore.set(false);
      }
    });

    if (!append) {
      this.loadSummary();
    }
  }

  loadSummary() {
    this.api.getProjectsSummary().subscribe({
      next: summary => this.summary.set({
        projects: Number(summary?.projects || 0),
        assistants: Number(summary?.assistants || 0),
        published_assistants: Number(summary?.published_assistants || 0),
        draft_only: Number(summary?.draft_only || 0)
      }),
      error: () => {
        this.summary.set({
          projects: this.projects().length,
          assistants: this.projects().reduce((sum, project) => sum + this.count(project, 'assistant_count', 'chatbot_count'), 0),
          published_assistants: this.projects().reduce((sum, project) => sum + this.count(project, 'published_assistant_count'), 0),
          draft_only: this.projects().reduce((sum, project) => sum + this.count(project, 'draft_only_assistant_count'), 0)
        });
      }
    });
  }

  loadMore() {
    if (!this.hasMore() || this.loadingMore()) return;
    this.loadProjects(false, true);
  }

  firstName() {
    const name = this.auth.currentUser()?.name || 'Balkis';
    return name.split(' ').filter(Boolean)[0] || name;
  }

  healthExplanation() {
    if (!this.projects().length) return 'Create a project to start tracking workspace readiness.';
    if (this.projectsNeedingPublication()) {
      return `${this.projectsNeedingPublication()} project${this.projectsNeedingPublication() === 1 ? '' : 's'} have assistants without a published version.`;
    }
    if (this.emptyProjectCount()) {
      return `${this.emptyProjectCount()} project${this.emptyProjectCount() === 1 ? '' : 's'} still need assistants.`;
    }
    return 'All active projects have assistants with published coverage.';
  }

  recentActivities() {
    return this.projects()
      .flatMap(project => this.projectActivity(project).map(item => ({ ...item, project })))
      .sort((a, b) => this.dateValue(b.date) - this.dateValue(a.date))
      .slice(0, 4);
  }

  workspaceInsights() {
    const insights: Array<{ tone: string; title: string; description: string; link?: any[] }> = [];
    const emptyProject = this.projects().find(project => this.assistantCount(project) === 0 && !this.isArchived(project));
    if (emptyProject) {
      insights.push({
        tone: 'warning',
        title: 'Assistant setup needed',
        description: `${emptyProject.name} has no assistants yet.`,
        link: ['/dashboard/projects', emptyProject.id, 'chatbots']
      });
    }

    const unpublishedProject = this.projects().find(project => this.assistantCount(project) > 0 && this.publishedCount(project) === 0 && !this.isArchived(project));
    if (unpublishedProject) {
      insights.push({
        tone: 'danger',
        title: 'Publication blocker',
        description: `${unpublishedProject.name} has assistants but no published assistant.`,
        link: ['/dashboard/projects', unpublishedProject.id]
      });
    }

    if (this.draftOnlyAssistants() > 0) {
      insights.push({
        tone: 'info',
        title: 'Draft assistants pending',
        description: `${this.draftOnlyAssistants()} draft-only assistant${this.draftOnlyAssistants() === 1 ? '' : 's'} need review.`
      });
    }

    if (this.archivedProjectCount() > 0) {
      insights.push({
        tone: 'muted',
        title: 'Archived workspaces',
        description: `${this.archivedProjectCount()} archived project${this.archivedProjectCount() === 1 ? '' : 's'} available through the status filter.`
      });
    }

    return insights.slice(0, 3);
  }

  insightActionLabel(insight: { tone: string; title: string }) {
    const title = String(insight.title || '').toLowerCase();
    if (title.includes('publish') || title.includes('publication')) return 'Review';
    if (title.includes('draft')) return 'Improve';
    if (title.includes('archived')) return 'Configure';
    if (insight.tone === 'warning' || insight.tone === 'danger') return 'Review';
    if (insight.tone === 'muted') return 'Configure';
    return 'Improve';
  }

  projectActivity(project: any) {
    const rows = [];
    if (this.lastActivity(project)) {
      rows.push({
        title: 'Project activity',
        detail: 'Workspace data changed',
        date: this.lastActivity(project),
        tone: 'blue'
      });
    }
    if (project?.created_at) {
      rows.push({
        title: 'Project created',
        detail: project.name || 'Project',
        date: project.created_at,
        tone: 'green'
      });
    }
    if (this.publishedCount(project) > 0) {
      rows.push({
        title: 'Published coverage',
        detail: `${this.publishedCount(project)} published assistant${this.publishedCount(project) === 1 ? '' : 's'}`,
        date: this.lastActivity(project) || project.created_at,
        tone: 'purple'
      });
    }
    return rows.slice(0, 3);
  }

  relativeDate(value: any) {
    const time = this.dateValue(value);
    if (!time) return 'No activity';
    const diff = Date.now() - time;
    const day = 24 * 60 * 60 * 1000;
    if (diff < day) return 'Today';
    const days = Math.floor(diff / day);
    if (days < 7) return `${days}d ago`;
    if (days < 30) return `${Math.floor(days / 7)}w ago`;
    if (days < 365) return `${Math.floor(days / 30)}mo ago`;
    return `${Math.floor(days / 365)}y ago`;
  }

  projectReadiness(project: any) {
    if (this.isArchived(project)) return 'Archived';
    if (this.assistantCount(project) === 0) return 'Needs setup';
    if (this.publishedCount(project) === 0) return 'Draft only';
    return 'Ready';
  }

  retryLoadProjects() {
    this.loadProjects(true);
  }

  createProject() {
    const name = this.newProjectName.trim();
    if (!name) return;

    this.creating.set(true);
    this.error.set('');
    this.message.set('');

    this.api.createProject({
      name,
      description: this.newProjectDescription.trim() || 'No description'
    }).subscribe({
      next: () => {
        this.newProjectName = '';
        this.newProjectDescription = '';
        this.createModalOpen.set(false);
        this.creating.set(false);
        this.toast.success('Project created');
        this.loadProjects();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not create project');
        this.toast.error('Could not create project');
        this.creating.set(false);
      }
    });
  }

  startEdit(project: any) {
    this.openRenameDialog(project);
  }

  openRenameDialog(project: any) {
    this.closeProjectMenu();
    this.renameDialogProject.set(project);
    this.renameName = project.name || '';
    this.renameDescription = project.description || '';
    this.error.set('');
    this.message.set('');
  }

  closeRenameDialog() {
    if (this.savingId()) return;
    this.renameDialogProject.set(null);
    this.renameName = '';
    this.renameDescription = '';
  }

  cancelEdit() {
    this.editingId = undefined;
    this.editName = '';
    this.editDescription = '';
  }

  saveProject(project: any) {
    const name = this.editName.trim();
    if (!name) {
      this.error.set('Project name is required');
      return;
    }

    this.savingId.set(project.id);
    this.error.set('');
    this.message.set('');

    this.api.updateProject(project.id, {
      name,
      description: this.editDescription.trim() || 'No description'
    }).subscribe({
      next: () => {
        this.savingId.set(undefined);
        this.cancelEdit();
        this.loadProjects();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not update project');
        this.savingId.set(undefined);
      }
    });
  }

  canSaveRename() {
    const project = this.renameDialogProject();
    if (!project) return false;
    const name = this.renameName.trim();
    const description = this.renameDescription.trim() || 'No description';
    return Boolean(name) && (
      name !== String(project.name || '').trim() ||
      description !== String(project.description || 'No description').trim()
    );
  }

  confirmRename() {
    const project = this.renameDialogProject();
    const name = this.renameName.trim();
    if (!project || !name) {
      this.error.set('Project name is required');
      return;
    }

    this.savingId.set(project.id);
    this.error.set('');

    this.api.updateProject(project.id, {
      name,
      description: this.renameDescription.trim() || 'No description'
    }).subscribe({
      next: () => {
        this.savingId.set(undefined);
        this.closeRenameDialog();
        this.toast.success('Project renamed');
        this.loadProjects();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not update project');
        this.toast.error('Could not update project');
        this.savingId.set(undefined);
      }
    });
  }

  openDeleteDialog(project: any) {
    this.closeProjectMenu();
    this.deleteDialogProject.set(project);
    this.error.set('');
    this.message.set('');
  }

  closeDeleteDialog() {
    if (this.deletingId()) return;
    this.deleteDialogProject.set(null);
  }

  confirmDeleteProject() {
    const project = this.deleteDialogProject();
    if (!project) return;

    this.deletingId.set(project.id);
    this.error.set('');
    this.message.set('');

    this.api.deleteProject(project.id).subscribe({
      next: () => {
        this.deletingId.set(undefined);
        this.closeDeleteDialog();
        this.toast.success('Project deleted successfully');
        this.loadProjects(true);
      },
      error: err => {
        this.error.set('Could not delete project. Please try again.');
        this.toast.error('Could not delete project. Please try again.');
        this.deletingId.set(undefined);
      }
    });
  }

  duplicateProject(project: any) {
    this.closeProjectMenu();
    this.duplicatingId.set(project.id);
    this.error.set('');
    this.message.set('');

    this.api.duplicateProject(project.id).subscribe({
      next: (duplicated: any) => {
        this.duplicatingId.set(undefined);
        this.toast.success(`Project duplicated as "${duplicated?.name || 'new project'}"`);
        this.loadProjects(true);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not duplicate project');
        this.toast.error('Could not duplicate project');
        this.duplicatingId.set(undefined);
      }
    });
  }

  openArchiveDialog(project: any) {
    this.closeProjectMenu();
    this.archiveDialogProject.set(project);
    this.error.set('');
    this.message.set('');
  }

  closeArchiveDialog() {
    if (this.archivingId()) return;
    this.archiveDialogProject.set(null);
  }

  confirmArchiveProject() {
    const project = this.archiveDialogProject();
    if (!project) return;

    this.archivingId.set(project.id);
    this.error.set('');
    this.message.set('');

    this.api.archiveProject(project.id).subscribe({
      next: () => {
        this.archivingId.set(undefined);
        this.closeArchiveDialog();
        this.toast.success('Project archived successfully');
        this.loadProjects(true);
      },
      error: err => {
        this.error.set('Could not archive project. Please try again.');
        this.toast.error('Could not archive project. Please try again.');
        this.archivingId.set(undefined);
      }
    });
  }

  restoreProject(project: any) {
    this.closeProjectMenu();
    this.restoringId.set(project.id);
    this.error.set('');
    this.message.set('');

    this.api.restoreProject(project.id).subscribe({
      next: () => {
        this.restoringId.set(undefined);
        this.toast.success('Project restored successfully');
        this.loadProjects(true);
      },
      error: () => {
        this.error.set('Could not restore project. Please try again.');
        this.toast.error('Could not restore project. Please try again.');
        this.restoringId.set(undefined);
      }
    });
  }

  updateSearch(value: string) {
    this.search = value;
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.loadProjects(true), 250);
  }

  resetSearch() {
    this.search = '';
    this.loadProjects();
  }

  clearSearchOnly() {
    this.search = '';
    this.loadProjects(true);
  }

  openCreateModal() {
    this.createModalOpen.set(true);
    this.error.set('');
  }

  closeCreateModal() {
    if (this.creating()) return;
    this.createModalOpen.set(false);
    this.newProjectName = '';
    this.newProjectDescription = '';
  }

  toggleProjectMenu(project: any, event: MouseEvent) {
    event.stopPropagation();
    if (!this.isBrowser) return;
    if (this.menuProjectId() === project.id) {
      this.closeProjectMenu();
      return;
    }
    this.menuProjectId.set(project.id);
    this.menuProject.set(project);
    this.positionProjectMenu(event.currentTarget as HTMLElement);
  }

  closeProjectMenu() {
    this.menuProjectId.set(undefined);
    this.menuProject.set(null);
  }

  toggleFilters(event: MouseEvent) {
    event.stopPropagation();
    if (!this.isBrowser) return;
    if (this.filtersOpen()) {
      this.filtersOpen.set(false);
      return;
    }
    const filters = this.activeFilters();
    this.filterStatus = filters.status;
    this.filterActivity = filters.activity;
    this.filterAssistants = filters.assistants;
    this.filtersOpen.set(true);
    this.positionFilterPopover(event.currentTarget as HTMLElement);
  }

  applyFilters() {
    this.activeFilters.set({
      status: this.filterStatus,
      activity: this.filterActivity,
      assistants: this.filterAssistants
    });
    this.filtersOpen.set(false);
    this.loadProjects(true);
  }

  clearFilters() {
    this.filterStatus = 'all';
    this.filterActivity = 'any';
    this.filterAssistants = 'any';
    this.activeFilters.set({
      status: 'all',
      activity: 'any',
      assistants: 'any'
    });
    this.filtersOpen.set(false);
    this.loadProjects(true);
  }

  setViewMode(mode: 'grid' | 'table') {
    this.viewMode.set(mode);
    this.safeLocalStorage()?.setItem(this.viewModeStorageKey, mode);
  }

  setSortMode(mode: string) {
    this.sortMode.set(mode);
    this.loadProjects(true);
  }

  projectStatus(project: any) {
    if (this.isArchived(project)) return 'Archived';
    if (this.normalizedProjectStatus(project) === 'active') return 'Active';
    if (this.normalizedProjectStatus(project) === 'draft') return 'Draft';
    if (this.publishedCount(project) > 0) return 'Published';
    if (this.assistantCount(project) > 0) return 'Draft';
    return 'Empty';
  }

  isArchived(project: any) {
    return this.normalizedProjectStatus(project) === 'archived';
  }

  canOpenWorkspace(project: any) {
    return !this.isArchived(project);
  }

  assistantCount(project: any) {
    return this.count(project, 'assistant_count', 'chatbot_count');
  }

  publishedCount(project: any) {
    return this.count(project, 'published_assistant_count');
  }

  draftCount(project: any) {
    return this.count(project, 'draft_only_assistant_count');
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent) {
    const target = event.target as HTMLElement | null;
    if (target?.closest('.project-actions-menu, .project-menu-button')) return;
    if (target?.closest('.filter-popover, .filter-button')) return;
    this.closeProjectMenu();
    this.filtersOpen.set(false);
  }

  @HostListener('document:keydown.escape')
  onEscape() {
    this.closeProjectMenu();
    this.filtersOpen.set(false);
    this.closeArchiveDialog();
    this.closeDeleteDialog();
  }

  @HostListener('window:resize')
  @HostListener('window:scroll')
  onViewportChange() {
    this.closeProjectMenu();
    this.filtersOpen.set(false);
  }

  private positionProjectMenu(anchor: HTMLElement) {
    const rect = anchor.getBoundingClientRect();
    const menuWidth = Math.min(224, window.innerWidth - 24);
    const menuHeight = 318;
    const margin = 12;
    const gap = 8;
    const top = rect.bottom + gap + menuHeight <= window.innerHeight - margin
      ? rect.bottom + gap
      : Math.max(margin, rect.top - gap - menuHeight);
    const maxLeft = Math.max(margin, window.innerWidth - menuWidth - margin);
    const left = Math.min(Math.max(margin, rect.right - menuWidth), maxLeft);
    this.projectMenuPosition.set({ top, left });
  }

  private positionFilterPopover(anchor: HTMLElement) {
    const rect = anchor.getBoundingClientRect();
    const menuWidth = Math.min(320, window.innerWidth - 24);
    const menuHeight = Math.min(380, window.innerHeight - 120);
    const margin = 12;
    const gap = 8;
    const top = rect.bottom + gap + menuHeight <= window.innerHeight - margin
      ? rect.bottom + gap
      : Math.max(margin, rect.top - gap - menuHeight);
    const maxLeft = Math.max(margin, window.innerWidth - menuWidth - margin);
    const left = Math.min(Math.max(margin, rect.left), maxLeft);
    this.filterPosition.set({ top, left });
  }

  private restoreViewMode() {
    const saved = this.safeLocalStorage()?.getItem(this.viewModeStorageKey);
    if (saved === 'grid' || saved === 'table') {
      this.viewMode.set(saved);
    }
  }

  private safeLocalStorage(): Storage | null {
    if (!this.isBrowser || typeof localStorage === 'undefined') return null;
    if (
      typeof localStorage.getItem !== 'function' ||
      typeof localStorage.setItem !== 'function'
    ) {
      return null;
    }
    return localStorage;
  }

  lastActivity(project: any) {
    return project?.last_activity_at || null;
  }

  private searchProjects(projects: any[]) {
    const query = this.search.trim().toLowerCase();
    if (!query) return projects;
    return projects.filter(project => {
      const name = String(project?.name || '').toLowerCase();
      const description = String(project?.description || '').toLowerCase();
      return name.includes(query) || description.includes(query);
    });
  }

  private filterProjects(projects: any[]) {
    const filters = this.activeFilters();
    return projects.filter(project =>
      this.matchesStatus(project, filters.status) &&
      this.matchesActivity(project, filters.activity) &&
      this.matchesAssistantRange(project, filters.assistants)
    );
  }

  private sortProjects(projects: any[]) {
    return [...projects].sort((a, b) => {
      if (this.sortMode() === 'created') {
        return this.dateValue(b.created_at) - this.dateValue(a.created_at);
      }
      if (this.sortMode() === 'name') {
        return String(a?.name || '').localeCompare(String(b?.name || ''), undefined, { sensitivity: 'base' });
      }
      if (this.sortMode() === 'assistants') {
        return this.assistantCount(b) - this.assistantCount(a);
      }
      return this.dateValue(this.lastActivity(b)) - this.dateValue(this.lastActivity(a));
    });
  }

  private matchesStatus(project: any, status: string) {
    const projectStatus = this.normalizedProjectStatus(project);
    if (status === 'archived') return projectStatus === 'archived';
    if (status === 'active') return projectStatus === 'active';
    if (status === 'draft') return projectStatus === 'draft';
    return projectStatus !== 'archived' && projectStatus !== 'disabled';
  }

  private matchesActivity(project: any, activity: string) {
    if (activity === 'any') return true;
    const days = Number(activity);
    const value = this.dateValue(this.lastActivity(project));
    if (!value) return false;
    return Date.now() - value <= days * 24 * 60 * 60 * 1000;
  }

  private matchesAssistantRange(project: any, range: string) {
    const count = this.assistantCount(project);
    if (range === 'none') return count === 0;
    if (range === '1-5') return count >= 1 && count <= 5;
    if (range === '6-10') return count >= 6 && count <= 10;
    if (range === '10+') return count > 10;
    return true;
  }

  private dateValue(value: any) {
    const time = value ? new Date(value).getTime() : 0;
    return Number.isFinite(time) ? time : 0;
  }

  resultLabel() {
    const total = this.projects().length;
    if (!this.search.trim()) return `${total} project${total === 1 ? '' : 's'}`;
    return `${total} result${total === 1 ? '' : 's'} for "${this.search.trim()}"`;
  }

  trend(...keys: string[]) {
    for (const project of this.projects()) {
      for (const key of keys) {
        if (project?.[key] !== undefined && project?.[key] !== null) return Number(project[key]);
      }
    }
    return undefined;
  }

  private sumProjectFields(...keys: string[]) {
    return this.projects().reduce((sum, project) => sum + this.count(project, ...keys), 0);
  }

  private count(project: any, ...keys: string[]) {
    for (const key of keys) {
      if (project?.[key] !== undefined && project?.[key] !== null) {
        return Number(project[key] || 0);
      }
    }
    return 0;
  }

  private backendStatusFilter() {
    const status = this.activeFilters().status;
    return status === 'active' || status === 'draft' || status === 'archived' ? status : '';
  }

  private normalizedProjectStatus(project: any) {
    return String(project?.status || 'active').toLowerCase();
  }

  private activityFromDate() {
    const activity = this.activeFilters().activity;
    if (activity === 'any') return '';
    const days = Number(activity);
    if (!Number.isFinite(days)) return '';
    const date = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
    return date.toISOString().slice(0, 10);
  }

}
