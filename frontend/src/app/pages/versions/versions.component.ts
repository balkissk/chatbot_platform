import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, HostListener, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';
import { AuthService } from '../../services/auth';

@Component({
  selector: 'app-versions',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './versions.component.html',
  styleUrls: ['./versions.component.css']
})
export class VersionsComponent implements OnInit {
  projectId!: number;
  chatbotId!: number;
  versions = signal<any[]>([]);
  selectedVersionId = signal<number | undefined>(undefined);
  configLoading = signal(false);
  configSaving = signal(false);
  configMessage = signal('');
  loading = signal(false);
  creating = signal(false);
  actionId = signal<number | undefined>(undefined);
  error = signal('');
  readiness = signal<any | null>(null);
  readinessLoading = signal(false);
  smokeLoading = signal(false);
  smokeMessage = signal('');
  pendingConfirm = signal<{
    type: 'version' | 'publish-warning';
    item: any;
    title: string;
    message: string;
    actionLabel: string;
  } | null>(null);
  private isBrowser: boolean;
  aiInstructions = {
    model: 'llama3',
    temperature: 0.7,
    system_instructions: '',
    tone: 'Professional',
    language: 'French',
    response_style: 'Concise'
  };

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private api: ApiService,
    private auth: AuthService,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    this.projectId = Number(this.route.snapshot.paramMap.get('projectId'));
    this.chatbotId = Number(this.route.snapshot.paramMap.get('chatbotId'));
    if (!this.isBrowser) return;
    this.loadVersions();
  }

  loadVersions() {
    if (!this.isBrowser) return;

    this.loading.set(true);
    this.error.set('');

    this.api.getVersionsByChatbot(this.chatbotId).subscribe({
      next: versions => {
        const sortedVersions = versions.sort((a: any, b: any) => b.version_number - a.version_number);
        const activeVersion = sortedVersions.find((version: any) => version.is_active);
        const publishedVersion = sortedVersions.find((version: any) => version.status === 'published');
        const selectedVersionId = activeVersion?.id || publishedVersion?.id || sortedVersions[0]?.id;
        this.versions.set(sortedVersions);
        this.selectedVersionId.set(selectedVersionId);
        this.loading.set(false);

        if (selectedVersionId) {
          this.loadLlmConfig(selectedVersionId);
          this.loadReadiness(selectedVersionId);
        } else {
          this.readiness.set(null);
        }
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load versions');
        this.loading.set(false);
      }
    });
  }

  createVersion() {
    if (!this.canManageWorkspace()) return;
    this.creating.set(true);
    this.error.set('');

    this.api.createVersion({ chatbot_id: this.chatbotId }).subscribe({
      next: () => {
        this.creating.set(false);
        this.loadVersions();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not create version');
        this.creating.set(false);
      }
    });
  }

  publish(versionId: number) {
    if (!this.canManageWorkspace()) return;
    this.actionId.set(versionId);
    this.error.set('');
    this.smokeMessage.set('');

    this.api.getVersionReadiness(versionId).subscribe({
      next: readiness => {
        this.readiness.set(readiness);
        const blocked = (readiness?.checks || []).filter((check: any) => check.status === 'BLOCKED');
        const warnings = (readiness?.checks || []).filter((check: any) => check.status === 'WARNING');
        if (blocked.length) {
          this.error.set(`Publication blocked: ${blocked.map((check: any) => check.message || check.label).join(' ')}`);
          this.actionId.set(undefined);
          return;
        }
        if (warnings.length) {
          this.pendingConfirm.set({
            type: 'publish-warning',
            item: { id: versionId, warnings },
            title: 'Publish with warnings?',
            message: `This version has ${warnings.length} warning${warnings.length === 1 ? '' : 's'}. Publishing is allowed, but confirm that you reviewed them.`,
            actionLabel: 'Publish anyway'
          });
          this.actionId.set(undefined);
          return;
        }
        this.publishNow(versionId, false);
      },
      error: err => {
        this.error.set(this.publishError(err));
        this.actionId.set(undefined);
      }
    });
  }

  private publishNow(versionId: number, confirmWarnings: boolean) {
    if (!this.canManageWorkspace()) return;
    this.actionId.set(versionId);
    this.api.publishVersion(versionId, confirmWarnings).subscribe({
      next: () => {
        this.actionId.set(undefined);
        this.pendingConfirm.set(null);
        this.loadVersions();
      },
      error: err => {
        const readiness = err?.error?.detail?.readiness;
        if (readiness) this.readiness.set(readiness);
        this.error.set(this.publishError(err));
        this.actionId.set(undefined);
      }
    });
  }

  archive(versionId: number) {
    if (!this.canManageWorkspace()) return;
    this.actionId.set(versionId);
    this.api.archiveVersion(versionId).subscribe({
      next: () => {
        this.actionId.set(undefined);
        this.loadVersions();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not archive version');
        this.actionId.set(undefined);
      }
    });
  }

  restore(versionId: number) {
    if (!this.canManageWorkspace()) return;
    this.actionId.set(versionId);
    this.api.restoreVersion(versionId).subscribe({
      next: () => {
        this.actionId.set(undefined);
        this.loadVersions();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not restore version');
        this.actionId.set(undefined);
      }
    });
  }

  duplicate(versionId: number) {
    if (!this.canManageWorkspace()) return;
    this.actionId.set(versionId);
    this.error.set('');
    this.api.duplicateVersion(versionId).subscribe({
      next: () => {
        this.actionId.set(undefined);
        this.loadVersions();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not duplicate version');
        this.actionId.set(undefined);
      }
    });
  }

  deleteVersion(version: any) {
    if (!this.canManageWorkspace()) return;
    this.pendingConfirm.set({
      type: 'version',
      item: version,
      title: 'Delete version?',
      message: `Are you sure you want to delete version ${version.version_number}? This action cannot be undone.`,
      actionLabel: 'Delete version'
    });
  }

  private deleteVersionNow(version: any) {
    if (!this.canManageWorkspace()) return;
    this.actionId.set(version.id);
    this.api.deleteVersion(version.id).subscribe({
      next: () => {
        this.actionId.set(undefined);
        this.pendingConfirm.set(null);
        this.loadVersions();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not delete version');
        this.actionId.set(undefined);
      }
    });
  }

  selectVersion(versionId: number) {
    this.selectedVersionId.set(versionId);
    this.loadLlmConfig(versionId);
    this.loadReadiness(versionId);
  }

  selectedVersion() {
    const selectedId = this.selectedVersionId();
    return this.versions().find(version => version.id === selectedId);
  }

  loadLlmConfig(versionId: number) {
    this.configLoading.set(true);
    this.configMessage.set('');
    this.api.getLlmConfig(versionId).subscribe({
      next: config => {
        this.aiInstructions = this.parseSystemPrompt(config);
        this.configLoading.set(false);
      },
      error: () => {
        this.aiInstructions = {
          model: 'llama3',
          temperature: 0.7,
          system_instructions: '',
          tone: 'Professional',
          language: 'French',
          response_style: 'Concise'
        };
        this.configLoading.set(false);
      }
    });
  }

  saveLlmConfig() {
    if (!this.canManageWorkspace()) return;
    const versionId = this.selectedVersionId();
    if (!versionId) return;

    this.configSaving.set(true);
    this.configMessage.set('');
    this.api.saveLlmConfig({
      version_id: versionId,
      model: this.aiInstructions.model || 'llama3',
      temperature: Number(this.aiInstructions.temperature) || 0.7,
      system_prompt: this.cleanSystemInstructions(this.aiInstructions.system_instructions) || 'You are a helpful assistant.',
      tone: this.aiInstructions.tone || 'Professional',
      language: this.aiInstructions.language || 'French',
      response_style: this.aiInstructions.response_style || 'Concise'
    }).subscribe({
      next: () => {
        this.configSaving.set(false);
        this.configMessage.set('AI instructions saved');
      },
      error: err => {
        this.configSaving.set(false);
        this.configMessage.set(err.error?.detail || 'Could not save AI instructions');
      }
    });
  }

  private parseSystemPrompt(config: any) {
    const prompt = config.system_prompt || '';
    const parsedPrompt = this.splitStructuredPromptMetadata(prompt);
    return {
      model: config.model || 'llama3',
      temperature: config.temperature ?? 0.7,
      system_instructions: parsedPrompt.body,
      tone: config.tone || parsedPrompt.metadata.tone || 'Professional',
      language: config.language || parsedPrompt.metadata.language || 'French',
      response_style: config.response_style || parsedPrompt.metadata.response_style || 'Concise'
    };
  }

  private cleanSystemInstructions(prompt: string) {
    return this.splitStructuredPromptMetadata(prompt).body.trim();
  }

  private splitStructuredPromptMetadata(prompt: string) {
    const lines = (prompt || '').split(/\r?\n/);
    const metadata: any = {};
    let index = lines.length - 1;
    let metadataLineCount = 0;

    while (index >= 0 && !lines[index].trim()) {
      index -= 1;
    }

    while (index >= 0) {
      const line = lines[index].trim();
      const separatorIndex = line.indexOf(':');
      if (separatorIndex < 0) break;

      const label = line.slice(0, separatorIndex).trim().toLowerCase();
      const value = line.slice(separatorIndex + 1).trim();
      if (label === 'tone') {
        metadata.tone = value;
      } else if (label === 'language') {
        metadata.language = value;
      } else if (label === 'response style') {
        metadata.response_style = value;
      } else {
        break;
      }

      metadataLineCount += 1;
      index -= 1;
      while (index >= 0 && !lines[index].trim()) {
        index -= 1;
      }
    }

    if (metadataLineCount < 2) {
      return { body: prompt || '', metadata: {} };
    }

    return {
      body: lines.slice(0, index + 1).join('\n').trim(),
      metadata
    };
  }

  loadReadiness(versionId = this.selectedVersionId()) {
    if (!versionId) return;
    this.readinessLoading.set(true);
    this.api.getVersionReadiness(versionId).subscribe({
      next: readiness => {
        this.readiness.set(readiness);
        this.readinessLoading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load readiness checklist');
        this.readinessLoading.set(false);
      }
    });
  }

  runSmokeTest() {
    if (!this.canManageWorkspace()) return;
    const versionId = this.selectedVersionId();
    if (!versionId) return;
    this.smokeLoading.set(true);
    this.smokeMessage.set('');
    this.error.set('');
    this.api.runVersionSmokeTest(versionId).subscribe({
      next: result => {
        this.smokeMessage.set(result.message || (result.status === 'passed' ? 'Smoke test passed' : 'Smoke test failed'));
        this.smokeLoading.set(false);
        this.loadReadiness(versionId);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Smoke test failed');
        this.smokeLoading.set(false);
        this.loadReadiness(versionId);
      }
    });
  }

  cancelPendingConfirm() {
    const pending = this.pendingConfirm();
    if (!pending) return;
    if (pending.type === 'version' && this.actionId() === pending.item.id) return;
    this.pendingConfirm.set(null);
  }

  confirmPendingAction() {
    if (!this.canManageWorkspace()) return;
    const pending = this.pendingConfirm();
    if (!pending) return;
    if (pending.type === 'version') {
      this.deleteVersionNow(pending.item);
      return;
    }
    if (pending.type === 'publish-warning') {
      this.publishNow(pending.item.id, true);
      return;
    }
  }

  readinessStatusClass(status: string) {
    return `readiness-${String(status || '').toLowerCase()}`;
  }

  @HostListener('document:keydown.escape')
  onEscape() {
    this.cancelPendingConfirm();
  }

  private publishError(err: any) {
    const detail = err?.error?.detail;
    if (Array.isArray(detail?.errors)) {
      return `Fix these flow issues before publishing: ${detail.errors.join(' ')}`;
    }
    const blocked = detail?.readiness?.checks?.filter((check: any) => check.status === 'BLOCKED') || [];
    if (blocked.length) {
      return `Publication blocked: ${blocked.map((check: any) => check.message || check.label).join(' ')}`;
    }
    if (typeof detail?.message === 'string') return detail.message;
    if (typeof detail === 'string') return detail;
    return 'Could not publish version';
  }

  goBack() {
    this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots']);
  }

  canManageWorkspace() {
    return this.auth.canManageWorkspace();
  }
}
