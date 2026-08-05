import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { ActivatedRoute, RouterModule } from '@angular/router';
import {
  LucideBarChart3,
  LucideBookOpen,
  LucideGitBranch,
  LucideMessageSquareText,
  LucideRocket,
  LucideSettings,
  LucideWorkflow
} from '@lucide/angular';
import { ApiService } from '../../services/api';
import { channelLabel, languageLabel, purposeLabel } from '../../shared/assistant-options';

@Component({
  selector: 'app-assistant-overview',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    LucideBarChart3,
    LucideBookOpen,
    LucideGitBranch,
    LucideMessageSquareText,
    LucideRocket,
    LucideSettings,
    LucideWorkflow
  ],
  templateUrl: './assistant-overview.component.html',
  styleUrls: ['./assistant-overview.component.css']
})
export class AssistantOverviewComponent implements OnInit {
  projectId!: number;
  chatbotId!: number;
  assistant = signal<any | null>(null);
  loading = signal(false);
  error = signal('');
  private isBrowser: boolean;

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    this.projectId = Number(this.route.snapshot.paramMap.get('projectId'));
    this.chatbotId = Number(this.route.snapshot.paramMap.get('chatbotId'));
    if (!this.isBrowser) return;
    this.loadAssistant();
  }

  loadAssistant() {
    this.loading.set(true);
    this.error.set('');
    this.api.getChatbot(this.chatbotId).subscribe({
      next: assistant => {
        this.assistant.set(assistant);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load assistant');
        this.loading.set(false);
      }
    });
  }

  statusLabel() {
    const assistant = this.assistant();
    if (!assistant) return 'Loading';
    return assistant.is_active ? 'Live' : 'Draft';
  }

  purpose() {
    const assistant = this.assistant();
    return purposeLabel(assistant?.purpose || assistant?.assistant_type);
  }

  language() {
    return languageLabel(this.assistant()?.language);
  }

  channel() {
    return channelLabel(this.assistant()?.channel);
  }

  versionSummary() {
    const assistant = this.assistant();
    if (!assistant) return 'No version data';
    const latest = assistant.latest_version_number || assistant.draft_version_number || assistant.version_number;
    const live = assistant.published_version_number || assistant.live_version_number;
    return `Draft ${latest ? 'v' + latest : 'none'} · ${live ? 'Live v' + live : 'No live version'}`;
  }
}
