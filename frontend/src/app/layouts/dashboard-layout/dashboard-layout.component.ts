import { CommonModule, DOCUMENT } from '@angular/common';
import { Component, HostListener, Inject, OnDestroy, OnInit, signal } from '@angular/core';
import { ActivatedRoute, NavigationEnd, Router, RouterModule } from '@angular/router';
import {
  LucideBarChart3,
  LucideBot,
  LucideChevronDown,
  LucideChevronRight,
  LucideDatabase,
  LucideFolderKanban,
  LucideGitBranch,
  LucideLayoutDashboard,
  LucideLogOut,
  LucideMessageSquareText,
  LucideMoon,
  LucidePanelLeftClose,
  LucidePanelLeftOpen,
  LucideRocket,
  LucideScrollText,
  LucideSearch,
  LucideSlidersHorizontal,
  LucideSun,
  LucideUser,
  LucideWorkflow
} from '@lucide/angular';
import { Subject, catchError, debounceTime, distinctUntilChanged, filter, of, switchMap, takeUntil } from 'rxjs';
import { ApiService } from '../../services/api';
import { AuthService } from '../../services/auth';
import { ToastOutletComponent } from '../../components/toast-outlet.component';

type Breadcrumb = {
  label: string;
  link?: any[];
};

type GlobalSearchResult = {
  type: 'Project' | 'Assistant' | 'Knowledge Base';
  id: number;
  title: string;
  subtitle?: string;
  route: any[];
};

@Component({
  selector: 'app-dashboard-layout',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    LucideBarChart3,
    LucideBot,
    LucideChevronDown,
    LucideChevronRight,
    LucideDatabase,
    LucideFolderKanban,
    LucideGitBranch,
    LucideLayoutDashboard,
    LucideLogOut,
    LucideMessageSquareText,
    LucideMoon,
    LucidePanelLeftClose,
    LucidePanelLeftOpen,
    LucideRocket,
    LucideScrollText,
    LucideSearch,
    LucideSlidersHorizontal,
    LucideSun,
    LucideUser,
    LucideWorkflow,
    ToastOutletComponent
  ],
  templateUrl: './dashboard-layout.component.html',
  styleUrls: ['./dashboard-layout.component.css']
})
export class DashboardLayoutComponent implements OnInit, OnDestroy {
  constructor(
    public auth: AuthService,
    private api: ApiService,
    private route: ActivatedRoute,
    private router: Router,
    @Inject(DOCUMENT) private readonly document: Document
  ) {}

  navCollapsed = false;
  userMenuOpen = false;
  projectId = signal<number | null>(null);
  chatbotId = signal<number | null>(null);
  projectName = signal('');
  chatbotName = signal('');
  darkMode = signal(false);
  breadcrumbs = signal<Breadcrumb[]>([]);
  projectNavExpanded = signal(true);
  assistantNavExpanded = signal(true);
  searchQuery = signal('');
  searchResults = signal<GlobalSearchResult[]>([]);
  searchLoading = signal(false);
  searchPanelOpen = signal(false);
  searchSubmitted = signal(false);

  private readonly navStorageKey = 'managerSidebarCollapsed';
  private readonly themeStorageKey = 'chatbotFactoryLandingTheme';
  private activeProjectNavId: number | null = null;
  private drawerReturnFocus: HTMLElement | null = null;
  private readonly searchInput$ = new Subject<string>();
  private readonly destroy$ = new Subject<void>();

  ngOnInit() {
    this.restoreThemePreference();
    this.restoreNavPreference();
    this.updateRouteContext();
    this.router.events.pipe(
      filter(event => event instanceof NavigationEnd),
      takeUntil(this.destroy$)
    ).subscribe(() => this.updateRouteContext());
    this.searchInput$.pipe(
      debounceTime(250),
      distinctUntilChanged(),
      switchMap(query => {
        const trimmed = query.trim();
        this.searchSubmitted.set(Boolean(trimmed));
        if (!trimmed) {
          this.searchLoading.set(false);
          this.searchResults.set([]);
          return of({ results: [] });
        }
        this.searchLoading.set(true);
        return this.api.globalSearch(trimmed).pipe(
          catchError(() => of({ results: [] }))
        );
      }),
      takeUntil(this.destroy$)
    ).subscribe(response => {
      this.searchResults.set(response?.results || []);
      this.searchLoading.set(false);
      this.searchPanelOpen.set(Boolean(this.searchQuery().trim()));
    });
  }

  ngOnDestroy() {
    this.destroy$.next();
    this.destroy$.complete();
  }

  toggleNav() {
    const willOpen = this.navCollapsed;
    if (willOpen && typeof document !== 'undefined') {
      this.drawerReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    }
    this.navCollapsed = !this.navCollapsed;
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(this.navStorageKey, String(this.navCollapsed));
    }
    if (willOpen && typeof window !== 'undefined' && window.matchMedia?.('(max-width: 991px)').matches) {
      window.setTimeout(() => this.focusFirstNavItem(), 0);
    }
  }

  toggleUserMenu() {
    this.userMenuOpen = !this.userMenuOpen;
  }

  toggleTheme() {
    this.darkMode.update(isDark => !isDark);
    this.safeLocalStorage()?.setItem(this.themeStorageKey, this.darkMode() ? 'dark' : 'light');
    this.updateThemeClass();
  }

  closeUserMenu() {
    this.userMenuOpen = false;
  }

  onSearchInput(event: Event) {
    const value = event.target instanceof HTMLInputElement ? event.target.value : '';
    this.searchQuery.set(value);
    this.searchPanelOpen.set(Boolean(value.trim()));
    this.searchInput$.next(value);
  }

  onSearchFocus() {
    if (this.searchQuery().trim()) {
      this.searchPanelOpen.set(true);
    }
  }

  selectSearchResult(result: GlobalSearchResult) {
    this.searchQuery.set('');
    this.searchResults.set([]);
    this.searchSubmitted.set(false);
    this.searchPanelOpen.set(false);
    this.router.navigate(result.route);
  }

  closeSearchPanel() {
    this.searchPanelOpen.set(false);
  }

  toggleProjectNav() {
    this.projectNavExpanded.update(expanded => !expanded);
  }

  toggleAssistantNav() {
    this.assistantNavExpanded.update(expanded => !expanded);
  }

  closeNavDrawer() {
    if (typeof window !== 'undefined' && window.matchMedia?.('(max-width: 991px)').matches) {
      this.navCollapsed = true;
      this.drawerReturnFocus?.focus();
      this.drawerReturnFocus = null;
    }
  }

  trapNavDrawerFocus(event: Event) {
    if (typeof window === 'undefined' || !window.matchMedia?.('(max-width: 991px)').matches || this.navCollapsed) return;
    const keyboardEvent = event as KeyboardEvent;
    const nav = document.querySelector('.pcoded-navbar') as HTMLElement | null;
    if (!nav) return;
    const focusable = Array.from(
      nav.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])')
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

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent) {
    const target = event.target;
    if (target instanceof Element) {
      if (this.userMenuOpen && !target.closest('.profile-menu')) {
        this.closeUserMenu();
      }
      if (!target.closest('.topbar-search-wrap')) {
        this.closeSearchPanel();
      }
    }
  }

  @HostListener('document:keydown.escape')
  onEscape() {
    this.closeUserMenu();
    this.closeSearchPanel();
    this.closeNavDrawer();
  }

  greeting() {
    const hour = new Date().getHours();
    if (hour >= 5 && hour < 12) return 'Good morning';
    if (hour >= 12 && hour < 18) return 'Good afternoon';
    return 'Good evening';
  }

  displayName() {
    return this.auth.currentUser()?.name || 'Workspace user';
  }

  displayRole() {
    const role = this.auth.currentUser()?.role || 'member';
    return role === 'admin' ? 'Platform Admin' : 'Workspace Manager';
  }

  initials() {
    return this.displayName()
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map(part => part[0]?.toUpperCase())
      .join('') || 'U';
  }

  isManager() {
    return this.auth.currentUser()?.role !== 'admin';
  }

  workspaceLabel() {
    return this.projectName() || 'All projects';
  }

  assistantLabel() {
    return this.chatbotName() || 'Assistant';
  }

  topbarPrimaryLabel() {
    if (this.chatbotId()) return 'Assistant';
    if (this.projectId()) return 'Project';
    if (this.router.url.includes('/dashboard/projects')) return 'Workspace';
    if (this.router.url.includes('/dashboard/profile')) return 'Profile';
    return this.auth.currentUser()?.role === 'admin' ? 'Admin' : 'Workspace';
  }

  topbarSecondaryLabel() {
    if (this.router.url === '/dashboard/projects') return 'All Projects';
    if (this.chatbotId()) return this.assistantLabel();
    if (this.projectId()) return this.workspaceLabel();
    return this.displayRole();
  }

  assistantPanelLink(mode: 'deploy' | 'settings') {
    const projectId = this.projectId();
    return projectId ? ['/dashboard/projects', projectId, 'chatbots'] : ['/dashboard/projects'];
  }

  assistantPanelQueryParams(mode: 'deploy' | 'settings') {
    return { mode, chatbot_id: this.chatbotId() };
  }

  navHiddenFromAssistiveTech() {
    return this.navCollapsed && this.isMobileViewport();
  }

  private focusFirstNavItem() {
    const nav = document.querySelector('.pcoded-navbar') as HTMLElement | null;
    const firstItem = nav?.querySelector<HTMLElement>('a[href], button:not([disabled])');
    firstItem?.focus();
  }

  private restoreNavPreference() {
    if (this.isMobileViewport()) {
      this.navCollapsed = true;
      return;
    }
    if (typeof localStorage === 'undefined') return;
    this.navCollapsed = localStorage.getItem(this.navStorageKey) === 'true';
  }

  private restoreThemePreference() {
    const savedTheme = this.safeLocalStorage()?.getItem(this.themeStorageKey);
    const prefersDark = typeof window !== 'undefined'
      ? window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
      : false;
    this.darkMode.set(savedTheme ? savedTheme === 'dark' : prefersDark);
    this.updateThemeClass();
  }

  private updateThemeClass() {
    this.document.documentElement.classList.toggle('landing-dark-mode', this.darkMode());
    this.document.documentElement.classList.toggle('dark-mode', this.darkMode());
  }

  private safeLocalStorage(): Storage | null {
    if (typeof localStorage === 'undefined') return null;
    if (
      typeof localStorage.getItem !== 'function' ||
      typeof localStorage.setItem !== 'function'
    ) {
      return null;
    }
    return localStorage;
  }

  private isMobileViewport() {
    return typeof window !== 'undefined' && window.matchMedia?.('(max-width: 991px)').matches;
  }

  private updateRouteContext() {
    const params = this.collectParams(this.route.root);
    const projectId = Number(params['projectId'] || 0) || null;
    const chatbotId = Number(params['chatbotId'] || 0) || null;

    this.projectId.set(projectId);
    this.chatbotId.set(chatbotId);

    if (!projectId) {
      this.projectName.set('');
      this.chatbotName.set('');
      this.activeProjectNavId = null;
      this.assistantNavExpanded.set(true);
      this.breadcrumbs.set(this.baseBreadcrumbs());
      return;
    }

    if (this.activeProjectNavId !== projectId) {
      this.activeProjectNavId = projectId;
      this.projectNavExpanded.set(true);
    }

    this.api.getProject(projectId).subscribe({
      next: project => {
        this.projectName.set(project?.name || 'Project');
        this.updateBreadcrumbs();
      },
      error: () => {
        this.projectName.set('Project');
        this.updateBreadcrumbs();
      }
    });

    if (chatbotId) {
      this.assistantNavExpanded.set(true);
      this.api.getChatbot(chatbotId).subscribe({
        next: chatbot => {
          this.chatbotName.set(chatbot?.name || 'Assistant');
          this.updateBreadcrumbs();
        },
        error: () => {
          this.chatbotName.set('Assistant');
          this.updateBreadcrumbs();
        }
      });
    } else {
      this.chatbotName.set('');
    }

    this.updateBreadcrumbs();
  }

  private updateBreadcrumbs() {
    const projectId = this.projectId();
    const chatbotId = this.chatbotId();
    if (!projectId) {
      this.breadcrumbs.set(this.baseBreadcrumbs());
      return;
    }

    const crumbs: Breadcrumb[] = [
      { label: 'Projects', link: ['/dashboard/projects'] },
      { label: this.projectName() || 'Project', link: ['/dashboard/projects', projectId] }
    ];

    if (this.router.url.includes('/chatbots')) {
      crumbs.push({ label: 'Assistants', link: ['/dashboard/projects', projectId, 'chatbots'] });
    }

    if (!chatbotId && this.router.url.includes('/analytics')) {
      crumbs.push({ label: 'Analytics' });
    }

    if (!chatbotId && this.router.url.includes('/settings')) {
      crumbs.push({ label: 'Settings' });
    }

    if (chatbotId) {
      crumbs.push({ label: this.chatbotName() || 'Assistant' });
      if (this.router.url.includes('/flow')) crumbs.push({ label: this.router.url.includes('/flow/test') ? 'Test' : 'Flow Builder' });
      else if (this.router.url.includes('/knowledge')) crumbs.push({ label: 'Knowledge' });
      else if (this.router.url.includes('/versions')) crumbs.push({ label: 'Versions' });
      else if (this.router.url.includes('/evaluations')) crumbs.push({ label: 'Evaluations' });
      else if (this.router.url.includes('/analytics')) crumbs.push({ label: 'Analytics' });
      else if (this.router.url.includes('/collected-data')) crumbs.push({ label: 'Collected data' });
      else if (this.router.url.includes('/conversations')) crumbs.push({ label: 'Conversations' });
      else if (this.router.url.includes('/templates')) crumbs.push({ label: 'Templates' });
      else if (this.router.url.includes('/ai-generator')) crumbs.push({ label: 'AI Generator' });
    }

    this.breadcrumbs.set(crumbs);
  }

  private baseBreadcrumbs(): Breadcrumb[] {
    if (this.router.url.includes('/dashboard/profile')) return [{ label: 'Profile' }];
    if (this.router.url.includes('/dashboard/template-qa')) return [{ label: 'Template QA' }];
    return [];
  }

  private collectParams(route: ActivatedRoute): Record<string, string> {
    let params: Record<string, string> = {};
    let current: ActivatedRoute | null = route;
    while (current) {
      params = { ...params, ...current.snapshot.params };
      current = current.firstChild;
    }
    return params;
  }
}
