import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
import { of, throwError } from 'rxjs';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EvaluationsComponent } from './evaluations.component';
import { ApiService } from '../../services/api';

describe('EvaluationsComponent edit mode', () => {
  let fixture: ComponentFixture<EvaluationsComponent>;
  let component: EvaluationsComponent;
  let api: any;
  let router: any;
  let datasetResponse: any;
  let runResponse: any[];

  const flowResponse = {
    nodes: [
      { node_key: 'start', type: 'message', label: 'Start', position_x: 0, position_y: 0 },
      { node_key: 'branch', type: 'buttons', label: 'Branch', position_x: 240, position_y: 0 },
      { node_key: 'help', type: 'buttons', label: 'Help', position_x: 240, position_y: 140, config: { buttons: ['Support', 'Sales'] } },
      { node_key: 'end', type: 'end', label: 'End', position_x: 480, position_y: 0 },
    ],
    transitions: [
      { source_node_key: 'start', target_node_key: 'branch', label: 'next' },
      { source_node_key: 'branch', target_node_key: 'end', label: 'Done' },
    ]
  };

  const existingCase = {
    id: 101,
    dataset_id: 1,
    name: 'Existing case',
    description: 'Original description',
    order_index: 0,
    input_message: 'Original prompt',
    turns: [
      { type: 'TEXT', value: 'Original prompt' },
      { type: 'BUTTON_SELECTION', block_id: 'branch', value: 'Done' }
    ],
    initial_variables: { locale: 'en' },
    expected_response_mode: 'flow',
    expected_intent: 'refund_policy',
    expected_keywords: ['refund', '30 days'],
    forbidden_keywords: ['guaranteed'],
    expected_source_document_ids: ['doc-1'],
    expected_source_patterns: ['policy'],
    expected_flow_node_ids: ['start', 'branch'],
    forbidden_flow_node_ids: ['forbidden-node'],
    expected_final_node_id: 'end',
    expected_variable_assertions: [{ field: 'ticket_id', operator: 'exists' }],
    maximum_latency_ms: 4000,
    minimum_retrieval_score: 0.8,
    minimum_answer_score: 0.75,
    minimum_source_count: 1,
    expected_fallback: false,
    expected_handoff: null,
    expected_failure_category: 'policy_gap',
    critical: true,
    enabled: true,
    tags: ['billing', 'critical'],
    judge_config: { enabled: true, rubric: 'strict' },
    created_at: '2026-08-28T00:00:00Z',
    updated_at: '2026-08-28T00:00:00Z'
  };

  beforeEach(async () => {
    datasetResponse = {
      id: 1,
      name: 'Dataset',
      description: 'Suite',
      status: 'active',
      cases: [JSON.parse(JSON.stringify(existingCase))]
    };
    runResponse = [{
      id: 55,
      dataset_id: 1,
      version_id: 22,
      status: 'completed',
      failed_cases: 0,
      critical_failures: 0,
      overall_score: 100,
      total_cases: 1,
      passed_cases: 1,
      results: [{
        id: 801,
        case_id: 101,
        status: 'passed',
        case_snapshot: {
          name: 'Existing case',
          expected_keywords: ['refund', '30 days']
        }
      }]
    }];
    api = {
      getChatbot: vi.fn(() => of({ id: 2, name: 'Customer Support Assistant' })),
      getEvaluationDatasets: vi.fn(() => of([{ id: 1, name: 'Dataset', status: 'active' }])),
      getEvaluationDataset: vi.fn(() => of(JSON.parse(JSON.stringify(datasetResponse)))),
      getVersionsByChatbot: vi.fn(() => of([{ id: 22, version_number: 1, status: 'draft' }])),
      getFlow: vi.fn(() => of(flowResponse)),
      getEvaluationRuns: vi.fn(() => of(runResponse)),
      getVersionReadiness: vi.fn(() => of({ summary: { passed: 3, warnings: 0, blocked: 0 }, checks: [] })),
      getEvaluationPolicy: vi.fn(() => of({})),
      publishVersion: vi.fn(() => of({})),
      createEvaluationCase: vi.fn(),
      updateEvaluationCase: vi.fn(),
      duplicateEvaluationCase: vi.fn(() => of({})),
      setEvaluationCaseEnabled: vi.fn(() => of({}))
    };
    router = {
      navigate: vi.fn()
    };

    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn()
    });
    Object.defineProperty(HTMLInputElement.prototype, 'select', {
      configurable: true,
      value: vi.fn()
    });

    await TestBed.configureTestingModule({
      imports: [EvaluationsComponent],
      providers: [
        { provide: ApiService, useValue: api },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: convertToParamMap({ projectId: '1', chatbotId: '2' })
            }
          }
        },
        { provide: Router, useValue: router }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(EvaluationsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  });

  function clickEdit() {
    const button = fixture.nativeElement.querySelector('button[aria-label="Edit evaluation case"]') as HTMLButtonElement;
    button.click();
    fixture.detectChanges();
  }

  function openEditorRoute() {
    component.caseEditorPageMode.set(true);
    component.editCase(component.selectedDataset()?.cases?.[0]);
    fixture.detectChanges();
  }

  it('clicking Edit navigates to the full-page case editor', () => {
    clickEdit();

    expect(router.navigate).toHaveBeenCalledWith([
      '/dashboard/projects',
      1,
      'chatbots',
      2,
      'evaluations',
      'datasets',
      1,
      'cases',
      101,
      'edit'
    ]);
  });

  it('the editor route populates the form and restores flow selections', () => {
    openEditorRoute();

    expect(component.editingCaseId).toBe(101);
    expect(component.caseForm.name).toBe('Existing case');
    expect(component.caseForm.input_message).toBe('Original prompt');
    expect(component.caseForm.turns).toEqual([
      { type: 'TEXT', value: 'Original prompt' },
      { type: 'BUTTON_SELECTION', block_id: 'branch', value: 'Done' }
    ]);
    expect(component.caseForm.expected_keywords_text).toBe('refund|30 days');
    expect(component.caseForm.forbidden_keywords_text).toBe('guaranteed');
    expect(component.caseForm.expected_flow_node_ids_text).toBe('start|branch');
    expect(component.caseForm.forbidden_flow_node_ids_text).toBe('forbidden-node');
    expect(component.caseForm.expected_final_node_id).toBe('end');

    const nodeLabels = [...fixture.nativeElement.querySelectorAll('.flow-map.picker .flow-node')].map((node: any) => ({
      key: node.querySelector('small')?.textContent?.trim(),
      expected: node.classList.contains('expected'),
      forbidden: node.classList.contains('forbidden'),
      final: node.classList.contains('final')
    }));

    expect(nodeLabels).toEqual([
      { key: 'start', expected: true, forbidden: false, final: false },
      { key: 'branch', expected: true, forbidden: false, final: false },
      { key: 'help', expected: false, forbidden: false, final: false },
      { key: 'end', expected: false, forbidden: false, final: true }
    ]);
  });

  it('saving edit mode calls the update endpoint with merged advanced fields and updates the list', async () => {
    openEditorRoute();
    component.caseForm.name = 'Updated case';
    component.caseForm.expected_keywords_text = 'refund|45 days';

    api.updateEvaluationCase.mockImplementation((caseId: number, payload: any) => {
      expect(caseId).toBe(101);
      expect(payload.expected_keywords).toEqual(['refund', '45 days']);
      expect(payload.turns).toEqual([
        { type: 'TEXT', value: 'Original prompt' },
        { type: 'BUTTON_SELECTION', block_id: 'branch', value: 'Done' }
      ]);
      expect(payload.initial_variables).toEqual({ locale: 'en' });
      expect(payload.expected_intent).toBe('refund_policy');
      expect(payload.minimum_answer_score).toBe(0.75);
      expect(payload.judge_config).toEqual({ enabled: true, rubric: 'strict' });

      datasetResponse = {
        ...datasetResponse,
        cases: [{ ...existingCase, name: 'Updated case', expected_keywords: ['refund', '45 days'] }]
      };
      return of(datasetResponse.cases[0]);
    });

    component.saveCase();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.updateEvaluationCase).toHaveBeenCalledTimes(1);
    expect(component.editingCaseId).toBeNull();
    expect(component.selectedDataset()?.cases?.[0]?.name).toBe('Updated case');
    expect(component.message()).toBe('Evaluation case updated.');
  });

  it('cancel exits edit mode without sending an update and clears transient state', async () => {
    openEditorRoute();
    await fixture.whenStable();
    component.flowSelectionMode = 'forbidden';
    component.caseForm.name = 'Unsaved name';

    component.cancelCaseEdit();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.updateEvaluationCase).not.toHaveBeenCalled();
    expect(component.editingCaseId).toBeNull();
    expect(component.flowSelectionMode).toBe('expected');
    expect(component.caseForm.name).toBe('');
    expect(component.caseForm.expected_flow_node_ids_text).toBe('');
    expect(component.caseForm.forbidden_flow_node_ids_text).toBe('');
    expect(component.caseForm.expected_final_node_id).toBe('');
  });

  it('update failure preserves form content and edit state', async () => {
    openEditorRoute();
    component.caseForm.name = 'Still editing';
    api.updateEvaluationCase.mockReturnValue(throwError(() => ({ error: { detail: 'Update failed' } })));

    component.saveCase();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(component.editingCaseId).toBe(101);
    expect(component.caseForm.name).toBe('Still editing');
    expect(component.error()).toBe('Update failed');
  });

  it('saving an edit does not alter historical run snapshots already loaded in the UI', async () => {
    component.selectedResult.set(runResponse[0].results[0]);
    openEditorRoute();
    component.caseForm.expected_keywords_text = 'refund|updated';
    api.updateEvaluationCase.mockReturnValue(of({ ...existingCase, expected_keywords: ['refund', 'updated'] }));

    component.saveCase();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(component.selectedResult()?.case_snapshot?.name).toBe('Existing case');
    expect(component.selectedResult()?.case_snapshot?.expected_keywords).toEqual(['refund', '30 days']);
  });

  it('changing interaction type switches the correct controls and block dropdown only shows button blocks', () => {
    component.addInteractionTurn();
    expect(component.caseForm.turns[0]).toEqual({ type: 'TEXT', value: '' });

    component.setInteractionTurnType(0, 'BUTTON_SELECTION');
    expect(component.caseForm.turns[0]).toEqual({ type: 'BUTTON_SELECTION', block_id: '', value: '' });
    expect(component.interactionBlocks().map((block: any) => component.interactionBlockLabel(block))).toEqual([
      'Branch (branch)',
      'Help (help)'
    ]);
  });

  it('selecting a button block loads its options and saving a new case includes interaction metadata', async () => {
    component.caseForm.name = 'New case';
    component.caseForm.input_message = '';
    component.caseForm.turns = [
      { type: 'TEXT', value: 'Hello' },
      { type: 'BUTTON_SELECTION', block_id: 'help', value: 'Support' }
    ];

    expect(component.interactionTurnOptions('help')).toEqual(['Support', 'Sales']);

    api.createEvaluationCase.mockReturnValue(of({ id: 202, name: 'New case' }));
    component.saveCase();
    await fixture.whenStable();

    expect(api.createEvaluationCase).toHaveBeenCalledWith(1, expect.objectContaining({
      input_message: 'Hello',
      turns: [
        { type: 'TEXT', value: 'Hello' },
        { type: 'BUTTON_SELECTION', block_id: 'help', value: 'Support' }
      ]
    }));
  });

  it('changing version detects stale button selections from another flow version', () => {
    openEditorRoute();
    component.flow.set({
      nodes: [
        { node_key: 'start', type: 'message', label: 'Start', position_x: 0, position_y: 0 },
        { node_key: 'other', type: 'buttons', label: 'Other', position_x: 240, position_y: 0, config: { buttons: ['Other option'] } },
      ],
      transitions: [{ source_node_key: 'start', target_node_key: 'other', label: 'next' }]
    });
    fixture.detectChanges();

    expect(component.interactionTurnError(component.caseForm.turns[1])).toBe('Selected buttons block is not available in the chosen version.');
    expect(component.turnsContainStaleSelections()).toBe(true);
  });
});
