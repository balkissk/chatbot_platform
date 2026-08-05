import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';
import { ASSISTANT_PURPOSE_OPTIONS, purposeLabel } from '../../shared/assistant-options';

type TemplateStatus = '' | 'valid' | 'warning' | 'invalid';
type TemplateOwnershipView = '' | 'mine' | 'shared' | 'builtin';

@Component({
  selector: 'app-template-qa',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './template-qa.component.html',
  styleUrls: ['./template-qa.component.css']
})
export class TemplateQaComponent implements OnInit {
  items = signal<any[]>([]);
  summary = signal<any>({});
  loading = signal(false);
  error = signal('');
  detail = signal<any | null>(null);
  detailLoading = signal(false);
  detailSaving = signal(false);
  detailError = signal('');
  detailSuccess = signal('');
  detailForm = {
    name: '',
    description: '',
    purpose: 'custom',
    is_exposed: false,
    is_shared: false,
    test_scenarios: [] as any[]
  };
  scenarioMessages = '';
  scenarioName = 'Smoke test';
  expectedVariables = '';
  expectedFinalNode = '';
  testLoading = signal(false);
  testResult = signal<any | null>(null);
  testError = signal('');
  purposeOptions = ASSISTANT_PURPOSE_OPTIONS;
  search = '';
  status: TemplateStatus = '';
  exposure = '';
  ownershipView: TemplateOwnershipView = '';
  appliedFilters = signal<{ search: string; status: TemplateStatus; exposure: string; ownershipView: TemplateOwnershipView }>({
    search: '',
    status: '',
    exposure: '',
    ownershipView: ''
  });

  filteredItems = computed(() => {
    const filters = this.appliedFilters();
    const query = filters.search.trim().toLowerCase();
    return this.items().filter(item => {
      const exposed = Boolean(item.exposed);
      const matchesSearch = !query
        || item.key.toLowerCase().includes(query)
        || item.name.toLowerCase().includes(query)
        || (item.block_types || []).some((block: any) => block.type.toLowerCase().includes(query));
      const matchesStatus = !filters.status || item.status === filters.status;
      const matchesExposure = !filters.exposure
        || (filters.exposure === 'exposed' && exposed)
        || (filters.exposure === 'hidden' && !exposed);
      const ownershipScope = item.ownership_scope || (item.source === 'custom' ? 'shared' : 'builtin');
      const matchesOwnership = !filters.ownershipView || ownershipScope === filters.ownershipView;
      return matchesSearch && matchesStatus && matchesExposure && matchesOwnership;
    });
  });

  private isBrowser: boolean;

  constructor(
    private api: ApiService,
    private route: ActivatedRoute,
    private router: Router,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    if (!this.isBrowser) return;
    this.load();
    const templateKey = this.route.snapshot.paramMap.get('templateKey');
    if (templateKey) {
      const revision = Number(this.route.snapshot.queryParamMap.get('revision') || '');
      this.openTemplate(templateKey, false, revision || undefined);
    }
  }

  load() {
    this.loading.set(true);
    this.error.set('');
    this.api.getFlowTemplateQa().subscribe({
      next: payload => {
        this.items.set(payload.items || []);
        this.summary.set(payload.summary || {});
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load template QA report');
        this.loading.set(false);
      }
    });
  }

  resetFilters() {
    this.search = '';
    this.status = '';
    this.exposure = '';
    this.ownershipView = '';
    this.applyFilters();
  }

  applyFilters() {
    this.appliedFilters.set({
      search: this.search,
      status: this.status,
      exposure: this.exposure,
      ownershipView: this.ownershipView
    });
  }

  statusLabel(value: string) {
    const labels: Record<string, string> = {
      valid: 'Valid',
      warning: 'Warning',
      invalid: 'Invalid'
    };
    return labels[value] || 'Unknown';
  }

  purposeLabel(value: unknown) {
    return purposeLabel(value);
  }

  issueCount(item: any, severity: string) {
    return (item.issues || []).filter((issue: any) => issue.severity === severity).length;
  }

  exposedLabel(template: any) {
    if (!template.exposed) return 'Backend only';
    const purposes = template.purposes || [];
    return purposes.length
      ? `${purposes.map((purpose: string) => purposeLabel(purpose)).join(', ')} creation`
      : 'Shown in creation';
  }

  ownershipLabel(template: any) {
    const scope = template?.ownership_scope || (template?.source === 'custom' ? 'shared' : 'builtin');
    if (scope === 'mine') return 'My template';
    if (scope === 'shared') return 'Shared template';
    return 'Built-in template';
  }

  openTemplate(templateKey: string, updateUrl = true, revision?: number) {
    this.detailLoading.set(true);
    this.detailError.set('');
    this.detailSuccess.set('');
    this.api.getFlowTemplate(templateKey, revision).subscribe({
      next: detail => {
        this.detail.set(detail);
        this.detailForm = {
          name: detail.name || '',
          description: detail.description || '',
          purpose: detail.primary_purpose || 'custom',
          is_exposed: Boolean(detail.exposed),
          is_shared: Boolean(detail.shared),
          test_scenarios: detail.test_scenarios || []
        };
        const firstScenario = this.detailForm.test_scenarios[0] || {};
        this.scenarioName = firstScenario.name || 'Smoke test';
        this.scenarioMessages = (firstScenario.messages || []).join('\n');
        this.expectedVariables = JSON.stringify(firstScenario.expected_variables || {}, null, 2);
        this.expectedFinalNode = firstScenario.expected_final_node_key || '';
        this.testResult.set(null);
        this.testError.set('');
        this.detailLoading.set(false);
        if (updateUrl) {
          this.router.navigate(['/dashboard/template-qa', templateKey], {
            queryParams: revision ? { revision } : {}
          });
        }
      },
      error: err => {
        this.detailError.set(err.error?.detail || 'Could not load template detail');
        this.detailLoading.set(false);
      }
    });
  }

  closeDetail() {
    this.detail.set(null);
    this.detailError.set('');
    this.detailSuccess.set('');
    this.testResult.set(null);
    this.testError.set('');
    this.router.navigate(['/dashboard/template-qa']);
  }

  saveDetail() {
    const detail = this.detail();
    if (!detail?.key || !detail.can_edit) return;
    this.detailSaving.set(true);
    this.detailError.set('');
    this.detailSuccess.set('');
    this.api.updateFlowTemplate(detail.key, this.detailForm).subscribe({
      next: updated => {
        this.detail.set(updated);
        this.detailSuccess.set('Template updated');
        this.detailSaving.set(false);
        this.load();
      },
      error: err => {
        this.detailError.set(err.error?.detail || 'Could not update template');
        this.detailSaving.set(false);
      }
    });
  }

  nodeTypeSummary(detail: any) {
    return (detail?.block_types || []).map((block: any) => `${block.type} x${block.count}`).join(' · ');
  }

  latestRevision(detail: any) {
    return detail?.current_revision_number || detail?.selected_revision_number || 1;
  }

  selectedRevision(detail: any) {
    return detail?.selected_revision_number || this.latestRevision(detail);
  }

  firstResultPath(result: any) {
    return result?.results?.[0]?.path || [];
  }

  runTemplateTest(saveScenario = false) {
    const detail = this.detail();
    if (!detail?.key) return;
    const scenario = this.currentScenarioPayload();
    if (!scenario) return;
    if (saveScenario && detail.can_edit) {
      this.detailForm.test_scenarios = [scenario];
      this.saveDetail();
    }
    this.testLoading.set(true);
    this.testError.set('');
    this.testResult.set(null);
    this.api.runFlowTemplateTest(detail.key, scenario).subscribe({
      next: result => {
        this.testResult.set(result);
        this.testLoading.set(false);
      },
      error: err => {
        this.testError.set(err.error?.detail || 'Template test failed');
        this.testLoading.set(false);
      }
    });
  }

  runSavedTemplateTest() {
    const detail = this.detail();
    if (!detail?.key) return;
    this.testLoading.set(true);
    this.testError.set('');
    this.testResult.set(null);
    this.api.runFlowTemplateTest(detail.key, {}).subscribe({
      next: result => {
        this.testResult.set(result);
        this.testLoading.set(false);
      },
      error: err => {
        this.testError.set(err.error?.detail || 'Template test failed');
        this.testLoading.set(false);
      }
    });
  }

  private currentScenarioPayload() {
    let expectedVariables = {};
    try {
      expectedVariables = this.expectedVariables.trim() ? JSON.parse(this.expectedVariables) : {};
    } catch {
      this.testError.set('Expected variables must be valid JSON.');
      return null;
    }
    return {
      name: this.scenarioName.trim() || 'Smoke test',
      messages: this.scenarioMessages.split('\n').map(item => item.trim()).filter(Boolean),
      expected_variables: expectedVariables,
      expected_final_node_key: this.expectedFinalNode.trim() || null
    };
  }
}
