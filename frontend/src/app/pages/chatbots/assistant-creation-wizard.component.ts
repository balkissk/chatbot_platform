import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  ASSISTANT_CHANNEL_OPTIONS,
  ASSISTANT_LANGUAGE_OPTIONS,
  channelDescription,
  normalizeAssistantChannel,
  normalizeAssistantLanguage
} from '../../shared/assistant-options';

type WizardStep = 1 | 2 | 3;

@Component({
  selector: 'app-assistant-creation-wizard',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './assistant-creation-wizard.component.html',
  styleUrls: ['./assistant-creation-wizard.component.css']
})
export class AssistantCreationWizardComponent implements OnChanges {
  @Input() submitting = false;
  @Input() title = 'Create assistant';
  @Input() description = 'Choose the business purpose, starting method, and basic identity for this assistant.';
  @Input() finishLabel = 'Finish Wizard';
  @Input() submittingLabel = 'Creating...';
  @Input() editMode = false;
  @Input() creationModeReadonly = false;
  @Input() disableFinishWhenUnchanged = false;
  @Input() errorMessage = '';
  @Input() successMessage = '';
  @Input() templateName: string | null = null;
  @Input() sourceTemplateKey: string | null = null;
  @Input() templateUpdateAvailable = false;
  @Input() aiRegenerationAvailable = false;
  @Input() initialState: Partial<{
    assistant_type: string;
    creation_mode: string;
    name: string;
    description: string;
    language: string;
    channel: string;
    assistant_goal: string;
    business_context: string;
    knowledge_base_description: string;
  }> | null = null;
  @Output() closeWizard = new EventEmitter<void>();
  @Output() finishWizard = new EventEmitter<any>();
  @Output() stateChanged = new EventEmitter<any>();
  @Output() openFlowBuilder = new EventEmitter<void>();
  @Output() templateDraftRequested = new EventEmitter<void>();
  @Output() aiDraftRequested = new EventEmitter<any>();

  currentStep = signal<WizardStep>(1);
  state = {
    assistant_type: '',
    creation_mode: '',
    name: '',
    description: '',
    language: 'fr',
    channel: 'web_widget',
    assistant_goal: '',
    business_context: '',
    knowledge_base_description: ''
  };
  private originalState = { ...this.state };
  languageOptions = ASSISTANT_LANGUAGE_OPTIONS;
  channelOptions = ASSISTANT_CHANNEL_OPTIONS;

  steps = [
    'Assistant Purpose',
    'Creation Mode',
    'Basic Configuration'
  ];

  ngOnChanges(changes: SimpleChanges) {
    if (changes['initialState'] && this.initialState) {
      this.state = {
        assistant_type: this.initialState.assistant_type || '',
        creation_mode: this.initialState.creation_mode || '',
        name: this.initialState.name || '',
        description: this.initialState.description || '',
        language: normalizeAssistantLanguage(this.initialState.language),
        channel: normalizeAssistantChannel(this.initialState.channel),
        assistant_goal: this.initialState.assistant_goal || '',
        business_context: this.initialState.business_context || '',
        knowledge_base_description: this.initialState.knowledge_base_description || ''
      };
      this.originalState = { ...this.state };
      this.currentStep.set(1);
      this.emitState();
    }
  }

  goNext() {
    if (this.canContinue() && this.currentStep() < 3) {
      this.currentStep.update(step => (step + 1) as WizardStep);
    }
  }

  goBack() {
    if (this.currentStep() > 1) {
      this.currentStep.update(step => (step - 1) as WizardStep);
    }
  }

  selectAssistantType(value: string) {
    this.state.assistant_type = value;
    this.emitState();
  }

  selectCreationMode(value: string) {
    if (this.creationModeReadonly) return;
    this.state.creation_mode = value;
    this.emitState();
  }

  updateField(
    field: 'name' | 'description' | 'language' | 'channel' | 'assistant_goal' | 'business_context' | 'knowledge_base_description',
    value: string
  ) {
    this.state[field] = field === 'language'
      ? normalizeAssistantLanguage(value)
      : field === 'channel'
        ? normalizeAssistantChannel(value)
        : value;
    this.emitState();
  }

  canContinue() {
    if (this.currentStep() === 1) return Boolean(this.state.assistant_type);
    if (this.currentStep() === 2) return Boolean(this.state.creation_mode);
    return Boolean(this.state.name.trim() && this.state.language && this.state.channel);
  }

  isDirty() {
    return JSON.stringify(this.normalizedState(this.state)) !== JSON.stringify(this.normalizedState(this.originalState));
  }

  canFinish() {
    if (!this.canContinue()) return false;
    if (this.disableFinishWhenUnchanged && !this.isDirty()) return false;
    return true;
  }

  finish() {
    if (!this.canFinish()) return;
    this.finishWizard.emit(this.normalizedState(this.state));
  }

  requestOpenFlowBuilder() {
    this.openFlowBuilder.emit();
  }

  requestTemplateDraft() {
    this.templateDraftRequested.emit();
  }

  requestAiDraft() {
    if (!this.canRegenerateAi()) return;
    this.aiDraftRequested.emit(this.normalizedState(this.state));
  }

  close() {
    this.closeWizard.emit();
  }

  creationModeLabel() {
    const labels: Record<string, string> = {
      scratch: 'Start From Scratch',
      template: 'Use Template',
      ai: 'Build With AI'
    };
    return labels[this.state.creation_mode] || this.state.creation_mode || 'Not recorded';
  }

  canRegenerateAi() {
    return this.aiRegenerationAvailable
      && Boolean(this.state.assistant_goal.trim())
      && Boolean(this.state.business_context.trim())
      && !this.submitting;
  }

  templateStatusTitle() {
    if (this.templateName) return this.templateName;
    if (this.sourceTemplateKey) return 'Original template is no longer available';
    return 'Template provenance not available';
  }

  selectedChannelDescription() {
    return channelDescription(this.state.channel);
  }

  private emitState() {
    this.stateChanged.emit(this.normalizedState(this.state));
  }

  private normalizedState(value: typeof this.state) {
    return {
      assistant_type: (value.assistant_type || '').trim(),
      creation_mode: (value.creation_mode || '').trim(),
      name: (value.name || '').trim(),
      description: (value.description || '').trim(),
      language: normalizeAssistantLanguage(value.language),
      channel: normalizeAssistantChannel(value.channel),
      assistant_goal: (value.assistant_goal || '').trim(),
      business_context: (value.business_context || '').trim(),
      knowledge_base_description: (value.knowledge_base_description || '').trim()
    };
  }
}
