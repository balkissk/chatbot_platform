import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
import { of } from 'rxjs';

import { ApiService } from '../../services/api';
import { TemplateSelectionComponent } from './template-selection.component';

describe('TemplateSelectionComponent', () => {
  let fixture: ComponentFixture<TemplateSelectionComponent>;
  let component: TemplateSelectionComponent;

  function createComponent(currentPurpose: string, persistedPurpose = 'employee_knowledge') {
    TestBed.configureTestingModule({
      imports: [TemplateSelectionComponent],
      providers: [
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: convertToParamMap({ projectId: '7', chatbotId: '9' }),
              queryParamMap: convertToParamMap({ source: 'setup', purpose: currentPurpose })
            }
          }
        },
        {
          provide: Router,
          useValue: {
            navigate: () => Promise.resolve(true)
          }
        },
        {
          provide: ApiService,
          useValue: {
            getChatbot: () => of({
              id: 9,
              name: 'Assistant',
              assistant_type: persistedPurpose,
              purpose: persistedPurpose
            }),
            getChatbotBuilder: () => of({}),
            applyFlowTemplate: () => of({})
          }
        }
      ]
    });

    fixture = TestBed.createComponent(TemplateSelectionComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  afterEach(() => TestBed.resetTestingModule());

  it('uses the current Assistant Setup purpose instead of the persisted assistant purpose', () => {
    createComponent('lead_generation', 'employee_knowledge');

    expect(component.assistantTypeLabel()).toBe('Lead Generation');
    expect(component.templates().map(template => template.name)).toContain('Contact Capture');
    expect(component.templates().map(template => template.name)).not.toContain('HR Knowledge Bot');
  });

  it('shows customer support templates when current purpose is customer support', () => {
    createComponent('customer_support', 'employee_knowledge');

    expect(component.templates().map(template => template.key)).toEqual([
      'customer_support_basic',
      'customer_support_rag',
      'customer_support_handoff',
      'customer_support_ticket_creation'
    ]);
  });
});
