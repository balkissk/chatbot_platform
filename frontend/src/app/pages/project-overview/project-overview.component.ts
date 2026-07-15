import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-project-overview',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './project-overview.component.html',
  styleUrls: ['./project-overview.component.css']
})
export class ProjectOverviewComponent implements OnInit {
  projectId!: number;
  project = signal<any | null>(null);
  chatbots = signal<any[]>([]);
  operations = signal<any | null>(null);
  conversations = signal<any[]>([]);
  loading = signal(false);
  chatbotsLoading = signal(false);
  operationsLoading = signal(false);
  conversationsLoading = signal(false);
  saving = signal(false);
  error = signal('');
  message = signal('');

  editing = false;
  editName = '';
  editDescription = '';

  private isBrowser: boolean;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private api: ApiService,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    if (!this.isBrowser) return;
    this.projectId = Number(this.route.snapshot.paramMap.get('projectId'));
    this.loadProject();
    this.loadChatbots();
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
        const chatbot = chatbots?.[0];
        if (chatbot) {
          this.loadOperations(chatbot.id);
          this.loadConversations(chatbot.id);
        }
      },
      error: () => {
        this.chatbots.set([]);
        this.chatbotsLoading.set(false);
      }
    });
  }

  loadOperations(chatbotId: number) {
    this.operationsLoading.set(true);
    this.api.getChatbotOperationsDashboard(chatbotId).subscribe({
      next: operations => {
        this.operations.set(operations);
        this.operationsLoading.set(false);
      },
      error: () => {
        this.operations.set(null);
        this.operationsLoading.set(false);
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

  chatbotStatus(bot: any) {
    return bot.is_active ? 'Active' : 'Inactive';
  }

  firstChatbot() {
    return this.chatbots()[0];
  }

  workspaceStatus() {
    const bot = this.firstChatbot();
    if (!bot) return 'No chatbot';
    if (Number(bot.published_version_count || 0) > 0) return 'Published';
    return bot.is_active ? 'Active draft' : 'Draft';
  }

  lastUpdated() {
    const bot = this.firstChatbot();
    const project = this.project();
    return bot?.updated_at || bot?.created_at || project?.updated_at || project?.created_at;
  }

  operationsWidgets() {
    const widgets = this.operations()?.widgets || {};
    return [
      {
        label: 'Knowledge Coverage',
        value: widgets.knowledge_coverage_score?.value,
        suffix: '%',
        helper: `${widgets.knowledge_coverage_score?.covered_questions || 0} of ${widgets.knowledge_coverage_score?.total_questions || 0} questions used knowledge`,
        tone: 'coverage'
      },
      {
        label: 'AI Resolution',
        value: widgets.ai_resolution_rate?.value,
        suffix: '%',
        helper: `${widgets.ai_resolution_rate?.resolved_without_handoff || 0} of ${widgets.ai_resolution_rate?.total_conversations || 0} conversations without handoff`,
        tone: 'resolution'
      },
      {
        label: 'Runtime Health',
        value: widgets.runtime_health?.value,
        suffix: '%',
        helper: `${widgets.runtime_health?.retrieval_failures || 0} retrieval failures, ${widgets.runtime_health?.runtime_errors || 0} runtime errors`,
        tone: 'health'
      },
      {
        label: 'Current Version',
        value: this.operations()?.current_version?.active_version?.version_number,
        prefix: 'v',
        helper: this.operations()?.current_version?.last_published_version ? `Last published v${this.operations()?.current_version?.last_published_version?.version_number}` : 'No published version yet',
        tone: 'version'
      }
    ];
  }

  formatKpiValue(value: unknown, suffix = '', prefix = '') {
    return value === undefined || value === null ? 'No data' : `${prefix}${value}${suffix}`;
  }

  validationItems() {
    return this.operations()?.validation_center || [];
  }

  knowledgeGaps() {
    return this.operations()?.knowledge_gaps || [];
  }

  recommendations() {
    return this.operations()?.ai_recommendations || [];
  }

  runtimeEvents() {
    return this.operations()?.recent_runtime_events || [];
  }

  replayRows() {
    return this.operations()?.conversation_replay || [];
  }

  versionInfo() {
    return this.operations()?.current_version || {};
  }

  statusLabel(status: string) {
    return status === 'ready' ? 'Ready' : 'Needs attention';
  }

  goToFirstChatbot(path: 'flow' | 'knowledge' | 'analytics' | 'test' | 'versions') {
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
