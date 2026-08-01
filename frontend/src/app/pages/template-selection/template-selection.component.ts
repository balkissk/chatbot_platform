import { CommonModule } from '@angular/common';
import { Component, HostListener, OnInit, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';
import {
  AssistantPurposeCode,
  AssistantTemplateOption,
  normalizeAssistantPurpose,
  purposeLabel,
  templatesForPurpose
} from '../../shared/assistant-options';

@Component({
  selector: 'app-template-selection',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './template-selection.component.html',
  styleUrls: ['./template-selection.component.css']
})
export class TemplateSelectionComponent implements OnInit {
  projectId: number;
  chatbotId: number;
  chatbot = signal<any | null>(null);
  templates = signal<ReadonlyArray<AssistantTemplateOption>>([]);
  selectedPurpose = signal<AssistantPurposeCode>('custom');
  selectedTemplate = signal('');
  loading = signal(false);
  applying = signal(false);
  applyConfirmOpen = signal(false);
  error = signal('');
  errorTitle = signal('');

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private api: ApiService
  ) {
    this.projectId = Number(this.route.snapshot.paramMap.get('projectId'));
    this.chatbotId = Number(this.route.snapshot.paramMap.get('chatbotId'));
  }

  ngOnInit() {
    this.loadAssistant();
  }

  loadAssistant() {
    this.loading.set(true);
    this.error.set('');
    this.errorTitle.set('');
    this.api.getChatbot(this.chatbotId).subscribe({
      next: chatbot => {
        this.chatbot.set(chatbot);
        const purpose = this.requestedPurpose(chatbot);
        this.selectedPurpose.set(purpose);
        const options = templatesForPurpose(purpose);
        this.templates.set(options);
        const requestedTemplate = this.route.snapshot.queryParamMap.get('template') || '';
        this.selectedTemplate.set(options.some(option => option.key === requestedTemplate) ? requestedTemplate : '');
        this.loading.set(false);
      },
      error: err => {
        this.errorTitle.set('');
        this.error.set(err.error?.detail || 'Could not load assistant');
        this.loading.set(false);
      }
    });
  }

  selectTemplate(templateKey: string) {
    this.selectedTemplate.set(templateKey);
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { template: templateKey },
      queryParamsHandling: 'merge',
      replaceUrl: true
    });
  }

  selectedTemplateName(): string {
    return this.templates().find(template => template.key === this.selectedTemplate())?.name || '';
  }

  isSetupMode() {
    return this.route.snapshot.queryParamMap.get('source') === 'setup';
  }

  backToAssistantSetup() {
    this.router.navigate(
      ['/dashboard/projects', this.projectId, 'chatbots', this.chatbotId, 'flow'],
      { queryParams: { setup: '1' } }
    );
  }

  assistantTypeLabel(): string {
    return purposeLabel(this.selectedPurpose());
  }

  private requestedPurpose(chatbot: any): AssistantPurposeCode {
    return normalizeAssistantPurpose(
      this.route.snapshot.queryParamMap.get('purpose')
      || chatbot?.assistant_type
      || chatbot?.purpose
      || 'custom'
    );
  }

  applyTemplate() {
    const templateKey = this.selectedTemplate();
    if (!templateKey) return;
    this.applyConfirmOpen.set(true);
  }

  clearError() {
    this.errorTitle.set('');
    this.error.set('');
  }

  cancelApplyTemplate() {
    this.applyConfirmOpen.set(false);
  }

  @HostListener('document:keydown.escape')
  onEscape() {
    if (this.applyConfirmOpen() && !this.applying()) {
      this.cancelApplyTemplate();
    }
  }

  confirmApplyTemplate() {
    const templateKey = this.selectedTemplate();
    if (!templateKey) return;

    this.applying.set(true);
    this.applyConfirmOpen.set(false);
    this.error.set('');
    this.errorTitle.set('');
    this.api.getChatbotBuilder(this.chatbotId).subscribe({
      next: context => {
        const flowId = context?.flow?.id;
        if (!flowId) {
          this.errorTitle.set('');
          this.error.set('No draft flow is available for this assistant.');
          this.applying.set(false);
          return;
        }

        this.api.applyFlowTemplate(flowId, templateKey, this.selectedPurpose()).subscribe({
          next: () => {
            if (typeof sessionStorage !== 'undefined') {
              sessionStorage.removeItem(`assistantSetupDraft:${this.chatbotId}`);
            }
            this.applying.set(false);
            this.router.navigate(
              ['/dashboard/projects', this.projectId, 'chatbots', this.chatbotId, 'flow'],
              { queryParams: { template: templateKey, refresh: Date.now() } }
            );
          },
          error: () => {
            this.errorTitle.set('Template could not be applied');
            this.error.set('The selected template contains an incomplete workflow configuration.');
            this.applying.set(false);
          }
        });
      },
      error: err => {
        this.errorTitle.set('');
        this.error.set(err.error?.detail || 'Could not load flow builder');
        this.applying.set(false);
      }
    });
  }
}
