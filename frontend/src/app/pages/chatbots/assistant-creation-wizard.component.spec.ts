import { ComponentFixture, TestBed } from '@angular/core/testing';

import { AssistantCreationWizardComponent } from './assistant-creation-wizard.component';

describe('AssistantCreationWizardComponent', () => {
  let component: AssistantCreationWizardComponent;
  let fixture: ComponentFixture<AssistantCreationWizardComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AssistantCreationWizardComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(AssistantCreationWizardComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('exposes only English and French language options', () => {
    expect(component.languageOptions.map(option => option.label)).toEqual(['English', 'French']);
    expect(component.languageOptions.map(option => String(option.value)).includes('ar')).toBe(false);
  });

  it('normalizes emitted language and channel values', () => {
    const emitted: any[] = [];
    component.finishWizard.subscribe(value => emitted.push(value));

    component.selectAssistantType('custom');
    component.selectCreationMode('scratch');
    component.updateField('name', 'Demo assistant');
    component.updateField('language', 'English');
    component.updateField('channel', 'REST Public API');
    component.currentStep.set(3);

    component.finish();

    expect(emitted[0].language).toBe('en');
    expect(emitted[0].channel).toBe('rest_public_api');
  });
});
