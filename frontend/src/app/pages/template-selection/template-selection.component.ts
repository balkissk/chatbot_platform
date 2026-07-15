import { CommonModule } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';
import { AssistantCreationWizardComponent } from '../chatbots/assistant-creation-wizard.component';

type TemplateOption = {
  key: string;
  name: string;
  description: string;
};

@Component({
  selector: 'app-template-selection',
  standalone: true,
  imports: [CommonModule, RouterModule, AssistantCreationWizardComponent],
  templateUrl: './template-selection.component.html',
  styleUrls: ['./template-selection.component.css']
})
export class TemplateSelectionComponent implements OnInit {
  projectId: number;
  chatbotId: number;
  chatbot = signal<any | null>(null);
  templates = signal<TemplateOption[]>([]);
  selectedTemplate = signal('');
  loading = signal(false);
  applying = signal(false);
  setupWizardOpen = signal(false);
  savingSetup = signal(false);
  setupDraft = signal<any | null>(null);
  error = signal('');

  private readonly templateMap: Record<string, TemplateOption[]> = {
    customer_support: [
      { key: 'customer_support_basic', name: 'Customer Support Basic', description: 'Message, customer question, AI/RAG answer, and closing step.' },
      { key: 'customer_support_rag', name: 'Customer Support + RAG', description: 'Support assistant optimized for answering from uploaded knowledge.' },
      { key: 'customer_support_handoff', name: 'Customer Support + Human Handoff', description: 'Support answer flow with a handoff step for complex issues.' },
      { key: 'customer_support_ticket_creation', name: 'Customer Support + Ticket Creation', description: 'Collect issue details and prepare a support ticket handoff.' }
    ],
    employee_knowledge: [
      { key: 'hr_knowledge_bot', name: 'HR Knowledge Bot', description: 'Answer HR policy and employee process questions from knowledge.' },
      { key: 'it_helpdesk_bot', name: 'IT Helpdesk Bot', description: 'Guide employees through common IT support requests.' },
      { key: 'company_policies_bot', name: 'Company Policies Bot', description: 'Help employees find company policy answers quickly.' },
      { key: 'employee_onboarding_bot', name: 'Employee Onboarding Bot', description: 'Guide new employees through onboarding steps and resources.' }
    ],
    training_certification: [
      { key: 'microsoft_certification_advisor', name: 'Microsoft Certification Advisor', description: 'Recommend Microsoft certification paths based on goals.' },
      { key: 'azure_training_assistant', name: 'Azure Training Assistant', description: 'Help users choose Azure learning paths and next courses.' },
      { key: 'cybersecurity_learning_assistant', name: 'Cybersecurity Learning Assistant', description: 'Recommend cybersecurity learning tracks and certifications.' },
      { key: 'course_recommendation_bot', name: 'Course Recommendation Bot', description: 'Collect learner goals and suggest relevant courses.' }
    ],
    lead_generation: [
      { key: 'simple_lead_capture', name: 'Simple Lead Capture', description: 'Collect contact details and route the request to the team.' },
      { key: 'consultation_booking', name: 'Consultation Booking', description: 'Capture consultation needs, preferred date, and contact details.' },
      { key: 'cloud_assessment_lead_form', name: 'Cloud Assessment Lead Form', description: 'Qualify Azure and Microsoft Cloud assessment requests.' },
      { key: 'training_registration_bot', name: 'Training Registration Bot', description: 'Collect training interest and registration contact details.' }
    ],
    custom: [
      { key: 'blank_business_bot', name: 'Blank Business Bot', description: 'A minimal business assistant starter flow.' },
      { key: 'ai_assistant_starter', name: 'AI Assistant Starter', description: 'Start with a question and AI/RAG answer structure.' },
      { key: 'faq_starter', name: 'FAQ Starter', description: 'Start with a guided FAQ-style button flow.' },
      { key: 'sales_starter', name: 'Sales Starter', description: 'Start with a simple sales intake and qualification flow.' }
    ]
  };

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
    this.api.getChatbot(this.chatbotId).subscribe({
      next: chatbot => {
        this.chatbot.set(chatbot);
        const assistantType = chatbot.assistant_type || chatbot.purpose || 'custom';
        const options = this.templateMap[assistantType] || this.templateMap['custom'];
        this.templates.set(options);
        const requestedTemplate = this.route.snapshot.queryParamMap.get('template') || '';
        this.selectedTemplate.set(options.some(option => option.key === requestedTemplate) ? requestedTemplate : '');
        this.loading.set(false);
      },
      error: err => {
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

  private currentSetupState() {
    const chatbot = this.chatbot();
    return {
      assistant_type: chatbot?.assistant_type || chatbot?.purpose || 'custom',
      creation_mode: chatbot?.creation_mode || chatbot?.build_method || 'template',
      name: chatbot?.name || '',
      description: chatbot?.description || '',
      language: chatbot?.language || 'fr'
    };
  }

  openSetupWizard() {
    this.error.set('');
    this.setupDraft.set(this.currentSetupState());
    this.setupWizardOpen.set(true);
  }

  closeSetupWizard() {
    if (this.savingSetup()) return;
    this.setupWizardOpen.set(false);
    this.setupDraft.set(null);
  }

  saveAssistantSetup(state: any) {
    const name = state.name?.trim();
    if (!name) {
      this.error.set('Assistant name is required');
      return;
    }

    this.savingSetup.set(true);
    this.error.set('');
    this.api.updateChatbot(this.chatbotId, {
      name,
      description: state.description?.trim() || '',
      language: state.language,
      type: 'builder',
      purpose: state.assistant_type,
      mode: 'builder',
      channel: this.chatbot()?.channel || 'web_widget',
      build_method: state.creation_mode,
      creation_mode: state.creation_mode,
      template_key: this.chatbot()?.template_key || null
    }).subscribe({
      next: updated => {
        this.chatbot.set(updated);
        const assistantType = updated.assistant_type || updated.purpose || 'custom';
        this.templates.set(this.templateMap[assistantType] || this.templateMap['custom']);
        this.selectedTemplate.set('');
        this.router.navigate([], {
          relativeTo: this.route,
          queryParams: { template: null },
          queryParamsHandling: 'merge',
          replaceUrl: true
        });
        this.savingSetup.set(false);
        this.setupWizardOpen.set(false);
        this.setupDraft.set(null);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not update assistant setup');
        this.savingSetup.set(false);
      }
    });
  }

  assistantTypeLabel(): string {
    const value = this.chatbot()?.assistant_type || this.chatbot()?.purpose || 'custom';
    return String(value)
      .split('_')
      .map(part => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ');
  }

  applyTemplate() {
    const templateKey = this.selectedTemplate();
    if (!templateKey) return;

    this.applying.set(true);
    this.error.set('');
    this.api.getChatbotBuilder(this.chatbotId).subscribe({
      next: context => {
        const flowId = context?.flow?.id;
        if (!flowId) {
          this.error.set('No draft flow is available for this assistant.');
          this.applying.set(false);
          return;
        }

        this.api.applyFlowTemplate(flowId, templateKey).subscribe({
          next: () => {
            this.applying.set(false);
            this.router.navigate(
              ['/dashboard/projects', this.projectId, 'chatbots', this.chatbotId, 'flow'],
              { queryParams: { template: templateKey } }
            );
          },
          error: err => {
            this.error.set(err.error?.detail || 'Could not apply template');
            this.applying.set(false);
          }
        });
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load flow builder');
        this.applying.set(false);
      }
    });
  }
}
