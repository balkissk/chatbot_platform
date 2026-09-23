import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, ElementRef, HostListener, Inject, OnDestroy, OnInit, PLATFORM_ID, ViewChild, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';
import { AuthService } from '../../services/auth';
import { apiBaseUrl, frontendBaseUrl } from '../../config/app-config';
import { AssistantCreationWizardComponent } from './assistant-creation-wizard.component';
import { ToastService } from '../../services/toast.service';
import {
  LucideArrowRight,
  LucideBot,
  LucideClock3,
  LucideFilter,
  LucideGlobe,
  LucideLanguages,
  LucideLayers3,
  LucideMoreVertical,
  LucidePlus,
  LucideRefreshCw,
  LucideSearch
} from '@lucide/angular';
import {
  ASSISTANT_CHANNEL_OPTIONS,
  ASSISTANT_LANGUAGE_OPTIONS,
  ASSISTANT_PURPOSE_OPTIONS,
  channelLabel,
  normalizeAssistantChannel,
  normalizeAssistantLanguage,
  normalizeAssistantPurpose,
  languageLabel,
  purposeLabel
} from '../../shared/assistant-options';

@Component({
  selector: 'app-chatbots',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterModule,
    AssistantCreationWizardComponent,
    LucideArrowRight,
    LucideBot,
    LucideClock3,
    LucideFilter,
    LucideGlobe,
    LucideLanguages,
    LucideLayers3,
    LucideMoreVertical,
    LucidePlus,
    LucideRefreshCw,
    LucideSearch
  ],
  templateUrl: './chatbots.component.html',
  styleUrls: ['./chatbots.component.css']
})
export class ChatbotsComponent implements OnInit, OnDestroy {
  projectId!: number;
  project = signal<any | null>(null);
  chatbots = signal<any[]>([]);
  wizardOpen = signal(false);
  loading = signal(false);
  refreshing = signal(false);
  creating = signal(false);
  savingId = signal<number | undefined>(undefined);
  deletingId = signal<number | undefined>(undefined);
  statusId = signal<number | undefined>(undefined);
  apiKeyId = signal<number | undefined>(undefined);
  editingId = signal<number | undefined>(undefined);
  selectedDetails = signal<any | null>(null);
  pendingDeleteAssistant = signal<any | null>(null);
  pendingApiKeyReset = signal<any | null>(null);
  deleteError = signal('');
  channels = signal<any[]>([]);
  channelsLoading = signal(false);
  detailsMode = signal<'overview' | 'deploy' | 'settings'>('overview');
  detailsLoading = signal(false);
  activeActionBot = signal<any | null>(null);
  actionMenuPosition = signal({ top: 0, left: 0 });
  actionMenuReady = signal(false);
  statusFilter = signal<'all' | 'live' | 'draft' | 'attention'>('all');
  purposeFilter = signal('all');
  channelFilter = signal('all');
  languageFilter = signal('all');
  creationFilter = signal('all');
  filtersOpen = signal(false);
  assistantSearch = signal('');
  currentPage = signal(1);
  readonly pageSize = 8;
  error = signal('');
  success = signal('');
  editForm = {
    name: '',
    description: '',
    language: 'fr',
    type: 'builder',
    purpose: 'custom',
    mode: 'builder',
    channel: 'web_widget',
    template_key: null as string | null
  };
  channelSaving = signal<string | undefined>(undefined);
  channelTesting = signal<string | undefined>(undefined);
  languageOptions = ASSISTANT_LANGUAGE_OPTIONS;
  channelOptions = ASSISTANT_CHANNEL_OPTIONS;
  purposeOptions = ASSISTANT_PURPOSE_OPTIONS;
  creationOptions = [
    { label: 'Start From Scratch', value: 'scratch' },
    { label: 'Use Template', value: 'template' },
    { label: 'Build With AI', value: 'ai' }
  ];
  private isBrowser: boolean;
  private pendingPanelChatbotId: number | undefined;
  private pendingPanelMode: 'deploy' | 'settings' | undefined;
  private actionMenuAnchor: HTMLElement | null = null;
  private repositionFrame: number | undefined;
  private readonly viewportChangeHandler = () => this.onViewportChange();

  @ViewChild('actionPopover') actionPopover?: ElementRef<HTMLElement>;

  assistantCounts = computed(() => {
    const items = this.chatbots();
    return {
      all: items.length,
      live: items.filter(item => this.assistantLifecycleStatus(item) === 'live').length,
      draft: items.filter(item => this.assistantLifecycleStatus(item) === 'draft').length,
      attention: items.filter(item => this.assistantLifecycleStatus(item) === 'attention').length
    };
  });

  filteredChatbots = computed(() => {
    const query = this.assistantSearch().trim().toLowerCase();
    const filter = this.statusFilter();
    const purpose = this.purposeFilter();
    const channel = this.channelFilter();
    const language = this.languageFilter();
    const creation = this.creationFilter();
    return this.chatbots().filter(bot => {
      const status = this.assistantLifecycleStatus(bot);
      if (filter !== 'all' && status !== filter) return false;
      if (purpose !== 'all' && this.normalizedPurpose(bot.purpose || bot.assistant_type) !== purpose) return false;
      if (channel !== 'all' && this.normalizedChannel(bot.channel) !== channel) return false;
      if (language !== 'all' && this.normalizedLanguage(bot.language) !== language) return false;
      if (creation !== 'all' && this.normalizedCreationMode(bot.build_method || bot.creation_mode) !== creation) return false;
      if (!query) return true;
      const haystack = [
        bot.name,
        bot.description,
        bot.purpose,
        bot.assistant_type,
        bot.channel,
        bot.language
      ].filter(Boolean).join(' ').toLowerCase();
      return haystack.includes(query);
    });
  });

  activeFilterCount = computed(() => {
    return [
      this.statusFilter() !== 'all',
      this.purposeFilter() !== 'all',
      this.channelFilter() !== 'all',
      this.languageFilter() !== 'all',
      this.creationFilter() !== 'all'
    ].filter(Boolean).length;
  });

  totalPages = computed(() => Math.max(1, Math.ceil(this.filteredChatbots().length / this.pageSize)));

  pagedChatbots = computed(() => {
    const page = Math.min(this.currentPage(), this.totalPages());
    const start = (page - 1) * this.pageSize;
    return this.filteredChatbots().slice(start, start + this.pageSize);
  });

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    public auth: AuthService,
    private router: Router,
    private toast: ToastService,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    this.projectId = Number(this.route.snapshot.paramMap.get('projectId'));
    if (!this.isBrowser) return;
    const query = this.route.snapshot.queryParamMap;
    const returnedChatbotId = Number(query.get('chatbot_id'));
    const returnedMode = query.get('mode');
    if ((returnedMode === 'deploy' || returnedMode === 'settings') && returnedChatbotId) {
      this.pendingPanelChatbotId = returnedChatbotId;
      this.pendingPanelMode = returnedMode;
    }
    this.loadProject();
    const cachedChatbots = this.api.getCachedChatbotsByProject(this.projectId);
    if (cachedChatbots) {
      this.chatbots.set(cachedChatbots);
      this.loadChatbots(true, true);
    } else {
      this.loadChatbots();
    }
    if (query.get('create') === '1') {
      this.openWizard();
      this.router.navigate([], {
        relativeTo: this.route,
        queryParams: {},
        replaceUrl: true
      });
    }
    window.addEventListener('scroll', this.viewportChangeHandler, true);
    window.addEventListener('resize', this.viewportChangeHandler);
  }

  ngOnDestroy() {
    if (!this.isBrowser) return;
    window.removeEventListener('scroll', this.viewportChangeHandler, true);
    window.removeEventListener('resize', this.viewportChangeHandler);
    if (this.repositionFrame !== undefined) {
      window.cancelAnimationFrame(this.repositionFrame);
    }
  }

  loadProject(force = false) {
    if (!this.isBrowser) return;

    this.api.getProject(this.projectId, force).subscribe({
      next: project => {
        this.project.set(project);
      },
      error: () => {
        this.project.set(null);
      }
    });
  }

  loadChatbots(force = false, background = false) {
    if (!this.isBrowser) return;
    if (this.loading() || this.refreshing()) return;

    const hasVisibleData = this.chatbots().length > 0;
    if (background || hasVisibleData) {
      this.refreshing.set(true);
    } else {
      this.loading.set(true);
    }
    this.error.set('');
    if (!background) {
      this.success.set('');
    }

    this.api.getChatbotsByProject(this.projectId, force).subscribe({
      next: chatbots => {
        this.chatbots.set(chatbots);
        this.currentPage.set(1);
        this.loading.set(false);
        this.refreshing.set(false);
        this.openPendingPanel(chatbots);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load assistants');
        this.loading.set(false);
        this.refreshing.set(false);
      }
    });
  }

  setStatusFilter(value: 'all' | 'live' | 'draft' | 'attention') {
    this.statusFilter.set(value);
    this.currentPage.set(1);
  }

  setPurposeFilter(value: string) {
    this.purposeFilter.set(value || 'all');
    this.currentPage.set(1);
  }

  setChannelFilter(value: string) {
    this.channelFilter.set(value || 'all');
    this.currentPage.set(1);
  }

  setLanguageFilter(value: string) {
    this.languageFilter.set(value || 'all');
    this.currentPage.set(1);
  }

  setCreationFilter(value: string) {
    this.creationFilter.set(value || 'all');
    this.currentPage.set(1);
  }

  clearFilters() {
    this.statusFilter.set('all');
    this.purposeFilter.set('all');
    this.channelFilter.set('all');
    this.languageFilter.set('all');
    this.creationFilter.set('all');
    this.currentPage.set(1);
  }

  toggleFilters(event: MouseEvent) {
    event.stopPropagation();
    if (!this.isBrowser) return;
    if (this.filtersOpen()) {
      this.filtersOpen.set(false);
      return;
    }
    this.closeActionMenu();
    this.filtersOpen.set(true);
  }

  applyFilters() {
    this.currentPage.set(1);
    this.filtersOpen.set(false);
  }

  setAssistantSearch(value: string) {
    this.assistantSearch.set(value);
    this.currentPage.set(1);
  }

  goToPage(page: number) {
    const normalized = Math.max(1, Math.min(page, this.totalPages()));
    this.currentPage.set(normalized);
  }

  paginationPages() {
    return Array.from({ length: this.totalPages() }, (_, index) => index + 1);
  }

  showingStart() {
    if (!this.filteredChatbots().length) return 0;
    return (Math.min(this.currentPage(), this.totalPages()) - 1) * this.pageSize + 1;
  }

  showingEnd() {
    return Math.min(this.filteredChatbots().length, Math.min(this.currentPage(), this.totalPages()) * this.pageSize);
  }

  assistantLifecycleStatus(bot: any): 'live' | 'draft' | 'attention' {
    const rawStatus = String(bot.status || bot.lifecycle_status || '').toLowerCase();
    if (rawStatus.includes('attention') || rawStatus.includes('error') || rawStatus.includes('failed')) return 'attention';
    if (bot.needs_attention || bot.has_validation_errors || bot.validation_errors?.length) return 'attention';
    if (bot.is_active || Number(bot.published_version_count || 0) > 0 || bot.published) return 'live';
    return 'draft';
  }

  assistantStatusLabel(bot: any) {
    const status = this.assistantLifecycleStatus(bot);
    if (status === 'live') return 'Live';
    if (status === 'attention') return 'Needs attention';
    return 'Draft';
  }

  assistantAvatarClass(index: number) {
    const classes = ['blue', 'purple', 'green', 'indigo', 'orange'];
    return classes[index % classes.length];
  }

  assistantVersionSummary(bot: any) {
    const latest = bot.latest_version_number || bot.draft_version_number || bot.version_number;
    const live = bot.published_version_number || bot.live_version_number;
    if (latest || live) {
      return `Draft ${latest ? 'v' + latest : 'none'} · ${live ? 'Live v' + live : 'No live version'}`;
    }
    const versions = Number(bot.version_count || 0);
    const published = Number(bot.published_version_count || 0);
    return `${versions} ${versions === 1 ? 'version' : 'versions'} · ${published ? published + ' published' : 'No live version'}`;
  }

  assistantUpdatedLabel(bot: any) {
    const value = bot.updated_at || bot.created_at;
    if (!value) return 'No activity yet';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'Updated recently';
    const diffMs = Date.now() - date.getTime();
    const minutes = Math.floor(diffMs / 60000);
    if (minutes < 1) return 'Updated just now';
    if (minutes < 60) return `Updated ${minutes} min ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `Updated ${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `Updated ${days}d ago`;
    return `Updated ${date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}`;
  }

  openPendingPanel(chatbots: any[]) {
    if (!this.pendingPanelChatbotId || !this.pendingPanelMode) return;
    const bot = chatbots.find(item => Number(item.id) === this.pendingPanelChatbotId);
    if (!bot) return;
    const id = this.pendingPanelChatbotId;
    const mode = this.pendingPanelMode;
    this.pendingPanelChatbotId = undefined;
    this.pendingPanelMode = undefined;
    if (mode === 'deploy') {
      this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots', id, 'deployment'], { replaceUrl: true });
      return;
    }
    if (mode === 'settings') {
      this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots', id, 'settings'], { replaceUrl: true });
      return;
    }
    this.openPanel(bot, mode);
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { chatbot_id: id, mode },
      replaceUrl: true
    });
  }

  openWizard() {
    if (!this.canManageWorkspace() || this.isArchivedProject()) return;
    this.error.set('');
    this.success.set('');
    this.wizardOpen.set(true);
  }

  closeWizard() {
    if (this.creating()) return;
    this.wizardOpen.set(false);
  }

  finishWizard(state: any) {
    if (!this.canManageWorkspace()) return;
    this.creating.set(true);
    this.error.set('');
    this.success.set('');

    this.api.createChatbot({
      assistant_type: state.assistant_type,
      creation_mode: state.creation_mode,
      name: state.name.trim(),
      description: state.description?.trim() || '',
      language: normalizeAssistantLanguage(state.language),
      project_id: this.projectId,
      type: 'builder',
      purpose: state.assistant_type,
      mode: 'builder',
      channel: normalizeAssistantChannel(state.channel),
      build_method: state.creation_mode,
      template_key: null,
      status: 'draft',
      published: false
    }).subscribe({
      next: (created: any) => {
        this.creating.set(false);
        this.wizardOpen.set(false);
        this.success.set(`Assistant created as draft. Assistant ID: ${created.id}`);
        this.navigateAfterCreation(state.creation_mode, created.id);
      },
      error: err => {
        this.creating.set(false);
        this.error.set(err.error?.detail || 'Could not create assistant');
      }
    });
  }

  navigateAfterCreation(creationMode: string, chatbotId: number) {
    const base = ['/dashboard/projects', this.projectId, 'chatbots', chatbotId];
    if (creationMode === 'template') {
      this.router.navigate([...base, 'templates']);
      return;
    }
    if (creationMode === 'ai') {
      this.router.navigate([...base, 'ai-generator']);
      return;
    }
    this.router.navigate([...base, 'flow']);
  }

  deleteChatbot(bot: any) {
    if (!this.canManageWorkspace() || this.isArchivedProject()) return;
    this.closeActionMenu();
    this.deleteError.set('');
    this.pendingDeleteAssistant.set(bot);
  }

  cancelDeleteAssistant() {
    if (this.deletingId()) return;
    this.pendingDeleteAssistant.set(null);
    this.deleteError.set('');
  }

  confirmDeleteAssistant() {
    if (!this.canManageWorkspace()) return;
    const bot = this.pendingDeleteAssistant();
    if (!bot || this.deletingId()) return;

    this.deletingId.set(bot.id);
    this.deleteError.set('');
    this.api.deleteChatbot(bot.id).subscribe({
      next: () => {
        this.deletingId.set(undefined);
        this.pendingDeleteAssistant.set(null);
        if (this.selectedDetails()?.id === bot.id) {
          this.closeDetails();
        }
        this.toast.success('Assistant deleted successfully');
        this.loadChatbots(true, true);
      },
      error: () => {
        this.deleteError.set('Assistant could not be deleted. Please try again.');
        this.toast.error('Assistant could not be deleted. Please try again.');
        this.deletingId.set(undefined);
      }
    });
  }

  trapDeleteModalFocus(event: Event) {
    if (!this.isBrowser || !this.pendingDeleteAssistant()) return;
    const keyboardEvent = event as KeyboardEvent;
    const modal = document.querySelector('.confirm-modal') as HTMLElement | null;
    if (!modal) return;
    const focusable = Array.from(
      modal.querySelectorAll<HTMLElement>('button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement as HTMLElement | null;
    if (keyboardEvent.shiftKey && active === first) {
      event.preventDefault();
      last.focus();
    } else if (!keyboardEvent.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  openPanel(bot: any, mode: 'overview' | 'deploy' | 'settings') {
    if ((!this.canManageWorkspace() || this.isArchivedProject()) && mode !== 'overview') return;
    if (mode === 'deploy') {
      this.closeActionMenu();
      this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots', bot.id, 'deployment']);
      return;
    }
    if (mode === 'settings') {
      this.closeActionMenu();
      this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots', bot.id, 'settings']);
      return;
    }
    this.closeActionMenu();
    this.detailsMode.set(mode);
    this.detailsLoading.set(true);
    this.error.set('');
    this.selectedDetails.set(null);

    this.api.getChatbot(bot.id).subscribe({
      next: details => {
        this.selectedDetails.set(details);
        this.detailsLoading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load assistant details');
        this.detailsLoading.set(false);
      }
    });
  }

  loadChannels(chatbotId: number) {
    this.channelsLoading.set(true);
    this.api.getChatbotChannels(chatbotId).subscribe({
      next: channels => {
        this.channels.set(channels || []);
        this.channelsLoading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load deployment channels');
        this.channels.set([]);
        this.channelsLoading.set(false);
      }
    });
  }

  closeDetails() {
    this.selectedDetails.set(null);
    this.editingId.set(undefined);
  }

  toggleActionMenu(bot: any, event: MouseEvent) {
    event.stopPropagation();
    if (!this.isBrowser) return;
    if (this.activeActionBot()?.id === bot.id) {
      this.closeActionMenu();
      return;
    }
    this.activeActionBot.set(bot);
    this.actionMenuAnchor = event.currentTarget as HTMLElement;
    this.actionMenuReady.set(false);
    this.positionActionMenu(this.actionMenuAnchor);
    this.queueActionMenuPosition();
  }

  closeActionMenu() {
    this.activeActionBot.set(null);
    this.actionMenuAnchor = null;
    this.actionMenuReady.set(false);
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent) {
    const target = event.target as HTMLElement | null;
    if (target?.closest('.filter-popover, .lifecycle-filter-button')) return;
    if (target?.closest('.action-popover, .assistant-menu-button')) return;
    this.closeActionMenu();
    this.filtersOpen.set(false);
  }

  @HostListener('document:keydown.escape')
  onEscape() {
    if (this.pendingApiKeyReset() && !this.apiKeyId()) {
      this.cancelRegenerateApiKey();
      return;
    }
    if (this.pendingDeleteAssistant() && !this.deletingId()) {
      this.cancelDeleteAssistant();
      return;
    }
    this.closeActionMenu();
    this.filtersOpen.set(false);
  }

  onViewportChange() {
    if (this.activeActionBot() && this.actionMenuAnchor) {
      this.queueActionMenuPosition();
    }
    this.filtersOpen.set(false);
  }

  private queueActionMenuPosition() {
    if (!this.isBrowser || !this.actionMenuAnchor) return;
    if (this.repositionFrame !== undefined) {
      window.cancelAnimationFrame(this.repositionFrame);
    }
    this.repositionFrame = window.requestAnimationFrame(() => {
      this.repositionFrame = undefined;
      if (!this.actionMenuAnchor || !this.activeActionBot()) return;
      this.positionActionMenu(this.actionMenuAnchor, this.actionPopover?.nativeElement);
      this.actionMenuReady.set(true);
    });
  }

  private positionActionMenu(anchor: HTMLElement, menu?: HTMLElement) {
    const rect = anchor.getBoundingClientRect();
    const margin = 12;
    const gap = 8;
    const measured = menu?.getBoundingClientRect();
    const fallbackWidth = 188;
    const fallbackHeight = 204;
    const menuWidth = Math.min(
      Math.max(measured?.width || fallbackWidth, 1),
      Math.max(1, window.innerWidth - margin * 2)
    );
    const menuHeight = Math.min(
      Math.max(measured?.height || fallbackHeight, 1),
      Math.max(1, window.innerHeight - margin * 2)
    );
    const canOpenDown = rect.bottom + gap + menuHeight <= window.innerHeight - margin;
    const preferredTop = canOpenDown ? rect.bottom + gap : rect.top - gap - menuHeight;
    const top = Math.min(
      Math.max(margin, preferredTop),
      Math.max(margin, window.innerHeight - menuHeight - margin)
    );
    const maxLeft = Math.max(margin, window.innerWidth - menuWidth - margin);
    const left = Math.min(Math.max(margin, rect.right - menuWidth), maxLeft);
    this.actionMenuPosition.set({ top, left });
  }

  private normalizedPurpose(value: unknown) {
    const raw = String(value || '').trim();
    return raw ? normalizeAssistantPurpose(raw) : '';
  }

  private normalizedChannel(value: unknown) {
    const raw = String(value || '').trim();
    return raw ? normalizeAssistantChannel(raw) : '';
  }

  private normalizedLanguage(value: unknown) {
    const raw = String(value || '').trim();
    return raw ? normalizeAssistantLanguage(raw) : '';
  }

  private normalizedCreationMode(value: unknown) {
    const normalized = String(value || '').trim().toLowerCase();
    if (normalized === 'blank' || normalized === 'manual') return 'scratch';
    if (normalized === 'scratch' || normalized === 'template' || normalized === 'ai') return normalized;
    return '';
  }

  startEdit(bot: any) {
    if (!this.canManageWorkspace() || this.isArchivedProject()) return;
    this.editingId.set(bot.id);
    this.error.set('');
    this.success.set('');
    this.editForm = {
      name: bot.name || '',
      description: bot.description || '',
      language: normalizeAssistantLanguage(bot.language),
      type: 'builder',
      purpose: bot.purpose || 'custom',
      mode: 'builder',
      channel: normalizeAssistantChannel(bot.channel),
      template_key: bot.template_key || null
    };
  }

  cancelEdit() {
    this.editingId.set(undefined);
  }

  saveChatbot(bot: any) {
    if (!this.canManageWorkspace()) return;
    const name = this.editForm.name.trim();
    if (!name) {
      this.error.set('Assistant name is required');
      return;
    }

    this.savingId.set(bot.id);
    this.error.set('');
    this.success.set('');

    this.api.updateChatbot(bot.id, {
      ...this.editForm,
      type: 'builder',
      mode: 'builder',
      name,
      description: this.editForm.description.trim(),
      language: normalizeAssistantLanguage(this.editForm.language),
      channel: normalizeAssistantChannel(this.editForm.channel)
    }).subscribe({
      next: updated => {
        this.savingId.set(undefined);
        this.editingId.set(undefined);
        this.selectedDetails.update(details => details?.id === bot.id ? { ...details, ...updated } : details);
        this.success.set('Assistant updated');
        this.loadChatbots(true, true);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not update assistant');
        this.savingId.set(undefined);
      }
    });
  }

  setActive(bot: any, isActive: boolean) {
    if (!this.canManageWorkspace() || this.isArchivedProject()) return;
    this.statusId.set(bot.id);
    this.error.set('');
    this.success.set('');

    this.api.updateChatbotStatus(bot.id, isActive).subscribe({
      next: updated => {
        this.statusId.set(undefined);
        this.selectedDetails.update(details => details?.id === bot.id ? { ...details, ...updated } : details);
        this.success.set(isActive ? 'Assistant activated' : 'Assistant deactivated');
        this.loadChatbots(true, true);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not update assistant status');
        this.statusId.set(undefined);
      }
    });
  }

  publicLink(bot: any) {
    return `${frontendBaseUrl()}/public-chat/${bot.id}`;
  }

  widgetCode(bot: any) {
    const baseUrl = apiBaseUrl();
    return `<script src="${baseUrl}/public/widget.js" data-api-base="${baseUrl}" data-chatbot-id="${bot.id}" data-title="${bot.name || 'Support'}"></script>`;
  }

  apiEndpoint() {
    return `${apiBaseUrl()}/public/api/chat`;
  }

  channel(type: string) {
    return this.channels().find(item => item.channel_type === type);
  }

  channelStatus(type: string) {
    return this.channel(type)?.status || (['web', 'widget', 'api'].includes(type) ? 'connected' : 'not_configured');
  }

  statusText(type: string) {
    const value = this.channelStatus(type);
    return value ? value.replace(/_/g, ' ') : 'disconnected';
  }

  masked(value: string | undefined) {
    return value ? '********' : 'Not configured';
  }

  saveChannel(bot: any, type: 'web' | 'widget' | 'api', config: any = {}) {
    if (!this.canManageWorkspace() || this.isArchivedProject()) return;
    this.channelSaving.set(type);
    this.error.set('');
    this.success.set('');
    this.api.updateChatbotChannel(bot.id, type, {
      status: 'configured',
      config_json: config
    }).subscribe({
      next: savedChannel => {
        this.channels.update(channels => {
          const existingIndex = channels.findIndex(item => item.channel_type === savedChannel.channel_type);
          if (existingIndex === -1) {
            return [...channels, savedChannel];
          }
          return channels.map(item => item.channel_type === savedChannel.channel_type ? savedChannel : item);
        });
        this.success.set(`${this.channelDisplayName(type)} channel saved`);
        this.channelSaving.set(undefined);
        this.loadChannels(bot.id);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not save channel');
        this.channelSaving.set(undefined);
      }
    });
  }

  testChannel(bot: any, type: 'web' | 'widget' | 'api') {
    if (!this.canManageWorkspace() || this.isArchivedProject()) return;
    this.channelTesting.set(type);
    this.error.set('');
    this.success.set('');
    this.api.testChatbotChannel(bot.id, type).subscribe({
      next: result => {
        this.channelTesting.set(undefined);
        this.success.set(result.configured
          ? `${type} channel is configured.`
          : `${type} missing: ${(result.missing_fields || []).join(', ') || 'configuration'}`);
        this.loadChannels(bot.id);
      },
      error: err => {
        this.channelTesting.set(undefined);
        this.error.set(err.error?.detail || 'Could not test channel');
      }
    });
  }

  channelLog(type: string, key: 'last_verification' | 'last_incoming_message' | 'last_error') {
    return this.channel(type)?.[key];
  }

  channelDisplayName(type: string) {
    const labels: Record<string, string> = {
      web: 'Public Chat',
      widget: 'Web Widget',
      api: 'REST API'
    };
    return labels[type] || type;
  }

  assistantLanguageLabel(value: unknown) {
    return languageLabel(value);
  }

  assistantChannelLabel(value: unknown) {
    return channelLabel(value);
  }

  assistantPurposeLabel(value: unknown) {
    return purposeLabel(value);
  }

  assistantCreationLabel(value: unknown) {
    const normalized = String(value || '').trim().toLowerCase();
    if (normalized === 'ai') return 'Build With AI';
    if (normalized === 'template') return 'Template';
    if (normalized === 'blank' || normalized === 'scratch') return 'Start From Scratch';
    return normalized ? normalized.charAt(0).toUpperCase() + normalized.slice(1) : 'Start From Scratch';
  }

  channelCurrentError(type: string) {
    const channel = this.channel(type);
    return channel?.last_error || channel?.last_error_log?.message || channel?.last_error?.message || '';
  }

  channelCurrentErrorAt(type: string) {
    const channel = this.channel(type);
    return channel?.last_error_log?.created_at || channel?.last_historical_error?.created_at || channel?.updated_at || '';
  }

  channelConfig(type: string) {
    return this.channel(type)?.config_json || {};
  }

  historicalChannelError(type: string) {
    const channel = this.channel(type);
    if (channel?.last_error) return '';
    return channel?.last_historical_error?.message || '';
  }

  historicalChannelErrorAt(type: string) {
    return this.channel(type)?.last_historical_error?.created_at || '';
  }

  clearChannelError(details: any, type: 'web' | 'widget' | 'api') {
    if (!this.canManageWorkspace() || this.isArchivedProject()) return;
    this.error.set('');
    this.success.set('');
    this.api.clearChatbotChannelError(details.id, type).subscribe({
      next: savedChannel => {
        this.channels.update(channels => channels.map(item => item.channel_type === savedChannel.channel_type ? savedChannel : item));
        this.success.set(`${this.channelDisplayName(type)} channel error cleared`);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not clear channel error');
      }
    });
  }

  channelStatusLabel(type: string) {
    const value = this.channelStatus(type);
    const labels: Record<string, string> = {
      disconnected: 'Not Configured',
      not_configured: 'Not Configured',
      configured: 'Configured',
      verified: 'Verified',
      connected: 'Connected',
      deployed: 'Connected',
      error: 'Error'
    };
    return labels[value] || value || 'Not Configured';
  }

  channelStatusClass(type: string) {
    return `channel-status-${this.channelStatus(type)}`;
  }

  widgetCustomizationPlaceholder() {
    this.success.set('Widget customization will open the customization workspace in a later step.');
  }

  apiCurl(bot: any) {
    return `curl -X POST "${this.apiEndpoint()}" -H "Content-Type: application/json" -H "x-chatbot-api-key: ${bot.public_api_key}" -d "{\\"chatbot_id\\":${bot.id},\\"message\\":\\"Hello\\",\\"session_id\\":null}"`;
  }

  maskedApiKey(bot: any) {
    const key = bot.public_api_key || '';
    if (!key) return 'Not generated';
    return `${key.slice(0, 5)}${'*'.repeat(18)}${key.slice(-4)}`;
  }

  copyText(text: string) {
    if (!text) {
      this.error.set('No value available to copy');
      return;
    }
    if (!this.isBrowser || !navigator.clipboard) return;
    navigator.clipboard.writeText(text).then(() => {
      this.success.set('Copied');
    });
  }

  regenerateApiKey(bot: any) {
    if (!this.canManageWorkspace() || this.isArchivedProject()) return;
    if (this.apiKeyId()) return;
    this.pendingApiKeyReset.set(bot);
  }

  cancelRegenerateApiKey() {
    if (this.apiKeyId()) return;
    this.pendingApiKeyReset.set(null);
  }

  confirmRegenerateApiKey() {
    if (!this.canManageWorkspace() || this.isArchivedProject()) return;
    const bot = this.pendingApiKeyReset();
    if (!bot || this.apiKeyId()) return;

    this.apiKeyId.set(bot.id);
    this.error.set('');
    this.success.set('');

    this.api.regenerateChatbotApiKey(bot.id).subscribe({
      next: response => {
        this.apiKeyId.set(undefined);
        this.pendingApiKeyReset.set(null);
        this.success.set('API key regenerated');
        this.selectedDetails.update(details => details ? { ...details, public_api_key: response.public_api_key } : details);
        this.loadChatbots(true, true);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not regenerate API key');
        this.apiKeyId.set(undefined);
      }
    });
  }

  goBack() {
    this.router.navigate(['/dashboard/projects', this.projectId]);
  }

  isArchivedProject() {
    return String(this.project()?.status || '').toLowerCase() === 'archived';
  }

  canManageWorkspace() {
    return this.auth.canManageWorkspace();
  }
}
