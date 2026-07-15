import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

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
  @Input() initialState: Partial<{
    assistant_type: string;
    creation_mode: string;
    name: string;
    description: string;
    language: string;
  }> | null = null;
  @Output() closeWizard = new EventEmitter<void>();
  @Output() finishWizard = new EventEmitter<any>();

  currentStep = signal<WizardStep>(1);
  state = {
    assistant_type: '',
    creation_mode: '',
    name: '',
    description: '',
    language: 'fr'
  };

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
        language: this.initialState.language || 'fr'
      };
      this.currentStep.set(1);
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
  }

  selectCreationMode(value: string) {
    this.state.creation_mode = value;
  }

  canContinue() {
    if (this.currentStep() === 1) return Boolean(this.state.assistant_type);
    if (this.currentStep() === 2) return Boolean(this.state.creation_mode);
    return Boolean(this.state.name.trim() && this.state.language);
  }

  finish() {
    if (!this.canContinue()) return;
    this.finishWizard.emit({ ...this.state });
  }

  close() {
    this.closeWizard.emit();
  }
}
