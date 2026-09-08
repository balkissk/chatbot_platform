import { CommonModule, isPlatformBrowser } from '@angular/common';
import { AfterViewInit, Component, ElementRef, HostListener, Inject, OnDestroy, OnInit, PLATFORM_ID, ViewChild, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import {
  LucideCheck,
  LucideChevronDown,
  LucideChevronUp,
  LucideCircleHelp,
  LucideEye,
  LucideGoal,
  LucideMail,
  LucideMessageSquareText,
  LucideMousePointerClick,
  LucideCopy,
  LucidePencil,
  LucidePhone,
  LucidePower,
  LucidePlay,
  LucidePlus,
  LucideRocket,
  LucideSettings,
  LucideTarget,
  LucideWorkflow,
  LucideX
} from '@lucide/angular';
import { forkJoin } from 'rxjs';
import { ApiService } from '../../services/api';
import { AuthService } from '../../services/auth';

@Component({
  selector: 'app-evaluations',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    LucideCheck,
    LucideChevronDown,
    LucideChevronUp,
    LucideCircleHelp,
    LucideEye,
    LucideGoal,
    LucideMail,
    LucideMessageSquareText,
    LucideMousePointerClick,
    LucideCopy,
    LucidePencil,
    LucidePhone,
    LucidePower,
    LucidePlay,
    LucidePlus,
    LucideRocket,
    LucideSettings,
    LucideTarget,
    LucideWorkflow,
    LucideX
  ],
  templateUrl: './evaluations.component.html',
  styleUrls: ['./evaluations.component.css']
})
export class EvaluationsComponent implements OnInit, AfterViewInit, OnDestroy {
  readonly interactionTypes = [
    { key: 'TEXT', label: 'Text message' },
    { key: 'BUTTON_SELECTION', label: 'Button selection' }
  ] as const;
  readonly triStateOptions = [
    { label: 'Any', value: null },
    { label: 'Yes', value: true },
    { label: 'No', value: false }
  ] as const;
  readonly responseModeOptions = [
    { label: 'Any', value: null },
    { label: 'Flow', value: 'flow' },
    { label: 'Fallback', value: 'fallback' },
    { label: 'Knowledge retrieval', value: 'evaluation_rag' },
    { label: 'Flow error', value: 'flow_error' }
  ] as const;
  readonly failureCategoryOptions = [
    { label: 'Any', value: null },
    { label: 'No answer', value: 'NO_ANSWER' },
    { label: 'Low retrieval confidence', value: 'LOW_RETRIEVAL_CONFIDENCE' },
    { label: 'Invalid flow', value: 'INVALID_FLOW' },
    { label: 'Provider failure', value: 'PROVIDER_FAILURE' },
    { label: 'Provider timeout', value: 'PROVIDER_TIMEOUT' },
    { label: 'API block failure', value: 'API_BLOCK_FAILURE' },
    { label: 'Ingestion not ready', value: 'INGESTION_NOT_READY' },
    { label: 'Loop limit exceeded', value: 'LOOP_LIMIT_EXCEEDED' },
    { label: 'Configuration error', value: 'CONFIGURATION_ERROR' }
  ] as const;
  readonly flowSelectionModes = [
    { key: 'expected', label: 'Expected path', description: 'Mark one or more blocks that must be visited.' },
    { key: 'forbidden', label: 'Forbidden', description: 'Mark one or more blocks that must not be visited.' },
    { key: 'final', label: 'Final block', description: 'Pick the one block where the flow should end.' }
  ] as const;
  projectId = 0;
  chatbotId = 0;
  loading = signal(false);
  running = signal(false);
  saving = signal(false);
  readinessLoading = signal(false);
  publishing = signal(false);
  error = signal('');
  message = signal('');
  chatbot = signal<any | null>(null);
  datasets = signal<any[]>([]);
  versions = signal<any[]>([]);
  runs = signal<any[]>([]);
  selectedDataset = signal<any | null>(null);
  selectedRun = signal<any | null>(null);
  selectedResult = signal<any | null>(null);
  comparison = signal<any | null>(null);
  policy = signal<any | null>(null);
  readiness = signal<any | null>(null);
  flow = signal<any | null>(null);
  flowLoading = signal(false);
  interactionBlocksCache = signal<any[]>([]);
  interactionOptionsByBlock = signal<Record<string, string[]>>({});
  suggestedCases = signal<any[]>([]);
  selectedSuggestionIds = signal<Set<string>>(new Set());
  suggestedCasesExpanded = signal(false);
  comparisonExpanded = signal(false);
  comparisonLoading = signal(false);
  manualComparisonVisible = signal(false);
  policyExpanded = signal(false);
  readinessExpanded = signal(false);
  showAllRuns = signal(false);
  expandedRunId = signal<number | null>(null);
  caseEditorVisible = signal(false);
  caseEditorPageMode = signal(false);
  activeDrawer = signal<'case' | 'run' | null>(null);
  overviewWidth = signal(0);
  pendingPublishConfirm = signal<{
    type: 'warning' | 'ready';
    versionId: number;
    versionNumber: number;
    readiness: any;
    warnings: any[];
  } | null>(null);
  newDataset = { name: '', description: '' };
  selectedVersionId: number | null = null;
  editorRouteDatasetId: number | null = null;
  editorRouteCaseId: number | null = null;
  baselineRunId: number | null = null;
  candidateRunId: number | null = null;
  comparisonContext: { mode: 'automatic' | 'manual'; baselineRunId: number; candidateRunId: number } | null = null;
  flowSelectionMode: 'expected' | 'forbidden' | 'final' = 'expected';
  editingCaseId: number | null = null;
  editingCaseOriginal: any | null = null;
  caseForm: any = this.blankCase();
  private isBrowser: boolean;
  @ViewChild('caseNameInput') caseNameInput?: ElementRef<HTMLInputElement>;
  @ViewChild('flowOverviewHost') flowOverviewHost?: ElementRef<HTMLElement>;
  private overviewResizeObserver?: ResizeObserver;
  private automaticComparisonRequestKey: string | null = null;

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
    this.configureCaseEditorRoute();
    if (!this.isBrowser) return;
    if (this.caseEditorPageMode() && !this.canManageWorkspace()) {
      this.navigateToEvaluations();
      return;
    }
    this.loadAll();
  }

  ngAfterViewInit() {
    if (!this.isBrowser) return;
    this.setupOverviewResizeObserver();
  }

  ngOnDestroy() {
    this.overviewResizeObserver?.disconnect();
  }

  @HostListener('document:keydown.escape')
  onEscapeKey() {
    if (this.pendingPublishConfirm()) return;
    if (this.activeDrawer()) {
      this.closeActiveDrawer();
    }
  }

  blankCase() {
    return {
      name: '',
      description: '',
      order_index: null,
      input_message: '',
      turns: [],
      initial_variables: {},
      expected_response_mode: null,
      expected_intent: null,
      expected_keywords_text: '',
      forbidden_keywords_text: '',
      expected_source_document_ids: [],
      expected_source_patterns_text: '',
      expected_flow_node_ids_text: '',
      forbidden_flow_node_ids_text: '',
      expected_final_node_id: '',
      expected_variable_assertions: [],
      maximum_latency_ms: null,
      minimum_retrieval_score: null,
      minimum_answer_score: null,
      minimum_source_count: null,
      expected_fallback: null,
      expected_handoff: null,
      expected_failure_category: null,
      critical: false,
      enabled: true,
      tags_text: '',
      judge_config: { enabled: false }
    };
  }

  private configureCaseEditorRoute() {
    const params = this.route.snapshot.paramMap;
    const datasetId = Number(params.get('datasetId'));
    const caseId = Number(params.get('caseId'));
    this.editorRouteDatasetId = Number.isFinite(datasetId) && datasetId > 0 ? datasetId : null;
    this.editorRouteCaseId = Number.isFinite(caseId) && caseId > 0 ? caseId : null;
    this.caseEditorPageMode.set(!!this.editorRouteDatasetId);
  }

  private openCaseEditorPage(datasetId: number, caseId?: number) {
    const base = ['/dashboard/projects', this.projectId, 'chatbots', this.chatbotId, 'evaluations', 'datasets', datasetId, 'cases'];
    const target = caseId ? [...base, caseId, 'edit'] : [...base, 'new'];
    this.router.navigate(target);
  }

  private navigateToEvaluations() {
    this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots', this.chatbotId, 'evaluations']);
  }

  private openRouteCaseEditor(dataset: any) {
    if (!this.canManageWorkspace()) {
      this.navigateToEvaluations();
      return;
    }
    if (this.editorRouteCaseId) {
      const caseItem = (dataset.cases || []).find((item: any) => item.id === this.editorRouteCaseId);
      if (!caseItem) {
        this.error.set('Evaluation case is not available in the selected dataset.');
        return;
      }
      this.prepareCaseEdit(caseItem);
      return;
    }
    this.prepareCaseCreate();
  }

  private prepareCaseCreate() {
    this.editingCaseId = null;
    this.editingCaseOriginal = null;
    this.caseForm = this.blankCase();
    this.flowSelectionMode = 'expected';
    this.caseEditorVisible.set(true);
    this.activeDrawer.set('case');
    this.focusCaseEditor();
  }

  private prepareCaseEdit(item: any) {
    const clone = this.cloneValue(item);
    this.editingCaseId = item.id;
    this.editingCaseOriginal = clone;
    this.caseForm = this.caseToForm(clone);
    this.flowSelectionMode = 'expected';
    this.caseEditorVisible.set(true);
    this.activeDrawer.set('case');
    this.focusCaseEditor();
  }

  private resetCaseEditorState() {
    this.editingCaseId = null;
    this.editingCaseOriginal = null;
    this.caseForm = this.blankCase();
    this.flowSelectionMode = 'expected';
    this.caseEditorVisible.set(false);
  }

  loadAll() {
    this.loading.set(true);
    this.error.set('');
    this.loadChatbot();
    this.api.getEvaluationDatasets(this.chatbotId).subscribe({
      next: datasets => {
        this.datasets.set(datasets);
        const initialDatasetId = this.editorRouteDatasetId || datasets[0]?.id;
        if (initialDatasetId) this.openDataset(initialDatasetId);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load evaluation datasets');
        this.loading.set(false);
      }
    });
    this.loadVersions();
    this.loadRuns();
    this.loadPolicy();
  }

  loadChatbot() {
    this.api.getChatbot(this.chatbotId).subscribe({
      next: chatbot => this.chatbot.set(chatbot),
      error: () => this.chatbot.set(null)
    });
  }

  loadVersions(preferredVersionId: number | null = this.selectedVersionId) {
    this.api.getVersionsByChatbot(this.chatbotId).subscribe({
      next: versions => {
        const sorted = versions.sort((a: any, b: any) => b.version_number - a.version_number);
        const nextSelectedVersionId = sorted.some((version: any) => version.id === preferredVersionId)
          ? preferredVersionId
          : (sorted[0]?.id || null);
        this.versions.set(sorted);
        this.selectedVersionId = nextSelectedVersionId;
        if (nextSelectedVersionId) {
          this.loadFlow(nextSelectedVersionId);
          this.loadReadiness(nextSelectedVersionId);
        } else {
          this.flow.set(null);
          this.readiness.set(null);
        }
        this.refreshAutomaticComparison();
      },
      error: () => {
        this.versions.set([]);
        this.readiness.set(null);
        this.refreshAutomaticComparison();
      }
    });
  }

  loadRuns() {
    this.api.getEvaluationRuns(this.chatbotId).subscribe({
      next: runs => {
        this.runs.set(runs);
        this.refreshAutomaticComparison();
      },
      error: () => {
        this.runs.set([]);
        this.refreshAutomaticComparison();
      }
    });
  }

  loadPolicy() {
    this.api.getEvaluationPolicy(this.chatbotId).subscribe({
      next: policy => this.policy.set(policy),
      error: () => this.policy.set(null)
    });
  }

  createDataset() {
    if (!this.canManageWorkspace()) return;
    if (!this.newDataset.name.trim()) return;
    this.saving.set(true);
    this.api.createEvaluationDataset(this.chatbotId, this.newDataset).subscribe({
      next: dataset => {
        this.newDataset = { name: '', description: '' };
        this.datasets.update(items => [dataset, ...items]);
        this.openDataset(dataset.id);
        this.saving.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not create dataset');
        this.saving.set(false);
      }
    });
  }

  openDataset(datasetId: number) {
    this.api.getEvaluationDataset(datasetId).subscribe({
      next: dataset => {
        this.selectedDataset.set(dataset);
        if (this.caseEditorPageMode()) {
          this.openRouteCaseEditor(dataset);
          return;
        }
        this.caseEditorVisible.set(false);
        this.editingCaseId = null;
        this.editingCaseOriginal = null;
        if (this.activeDrawer()) this.activeDrawer.set(null);
        this.selectedRun.set(null);
        this.selectedResult.set(null);
        this.manualComparisonVisible.set(false);
        this.refreshAutomaticComparison();
      },
      error: err => this.error.set(err.error?.detail || 'Could not load dataset')
    });
  }

  startCaseCreate() {
    if (!this.canManageWorkspace()) return;
    const dataset = this.selectedDataset();
    if (!dataset) return;
    if (!this.caseEditorPageMode()) {
      this.openCaseEditorPage(dataset.id);
      return;
    }
    this.prepareCaseCreate();
  }

  saveCase() {
    if (!this.canManageWorkspace()) return;
    const dataset = this.selectedDataset();
    if (!dataset || !this.caseForm.name.trim() || (!this.effectiveInputMessage().trim() && !this.caseForm.turns?.length)) return;
    if (this.turnValidationErrors().length) {
      this.error.set('Resolve the invalid interaction turns before saving this case.');
      return;
    }
    const payload = this.buildCasePayload();
    const editingCaseId = this.editingCaseId;
    this.saving.set(true);
    const request = editingCaseId
      ? this.api.updateEvaluationCase(editingCaseId, payload)
      : this.api.createEvaluationCase(dataset.id, payload);
    request.subscribe({
      next: (savedCase: any) => {
        this.upsertCaseInSelectedDataset(savedCase);
        if (this.caseEditorPageMode()) {
          this.resetCaseEditorState();
          this.navigateToEvaluations();
        } else {
          this.cancelCaseEdit();
        }
        this.saving.set(false);
        this.message.set(editingCaseId ? 'Evaluation case updated.' : 'Evaluation case created.');
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not save evaluation case');
        this.saving.set(false);
      }
    });
  }

  duplicateCase(caseId: number) {
    if (!this.canManageWorkspace()) return;
    const dataset = this.selectedDataset();
    if (!dataset) return;
    this.api.duplicateEvaluationCase(caseId).subscribe({
      next: () => this.openDataset(dataset.id),
      error: err => this.error.set(err.error?.detail || 'Could not duplicate case')
    });
  }

  toggleCase(item: any) {
    if (!this.canManageWorkspace()) return;
    const dataset = this.selectedDataset();
    if (!dataset) return;
    this.api.setEvaluationCaseEnabled(item.id, !item.enabled).subscribe({
      next: () => this.openDataset(dataset.id),
      error: err => this.error.set(err.error?.detail || 'Could not update case')
    });
  }

  editCase(item: any) {
    if (!this.canManageWorkspace()) return;
    const dataset = this.selectedDataset();
    if (!dataset?.cases?.some((candidate: any) => candidate.id === item.id)) {
      this.error.set('Evaluation case is not available in the selected dataset.');
      return;
    }
    if (!this.caseEditorPageMode()) {
      this.openCaseEditorPage(dataset.id, item.id);
      return;
    }
    this.prepareCaseEdit(item);
  }

  cancelCaseEdit() {
    if (this.caseEditorPageMode()) {
      this.resetCaseEditorState();
      this.navigateToEvaluations();
      return;
    }
    this.resetCaseEditorState();
    if (this.activeDrawer() === 'case') {
      this.activeDrawer.set(null);
    }
  }

  runDataset() {
    if (!this.canManageWorkspace()) return;
    const dataset = this.selectedDataset();
    if (!dataset || !this.selectedVersionId) return;
    this.running.set(true);
    this.message.set('');
    this.api.runEvaluation({
      dataset_id: dataset.id,
      version_id: this.selectedVersionId,
      deterministic_only: true,
      judge_enabled: false,
      trigger_type: 'manual'
    }).subscribe({
      next: run => {
        this.running.set(false);
        this.message.set(`Evaluation run ${run.id} completed with score ${run.overall_score ?? 0}.`);
        this.loadRuns();
        this.loadReadiness(this.selectedVersionId!);
        this.expandedRunId.set(run.id);
        this.openRun(run.id, true, true);
      },
      error: err => {
        this.running.set(false);
        this.error.set(err.error?.detail || 'Could not run evaluation');
      }
    });
  }

  openRun(runId: number, syncSelectedVersion = false, openDrawer = true) {
    this.api.getEvaluationRun(runId).subscribe({
      next: run => {
        this.selectedRun.set(run);
        this.selectedResult.set(null);
        if (openDrawer) {
          this.caseEditorVisible.set(false);
          this.activeDrawer.set('run');
        }
        if (syncSelectedVersion && run.version_id && this.selectedVersionId !== run.version_id) {
          this.selectedVersionId = run.version_id;
          this.loadFlow(run.version_id);
          this.loadReadiness(run.version_id);
        }
      },
      error: err => this.error.set(err.error?.detail || 'Could not load run')
    });
  }

  onVersionChange() {
    if (!this.selectedVersionId) return;
    this.expandedRunId.set(null);
    this.manualComparisonVisible.set(false);
    this.loadFlow(this.selectedVersionId);
    this.loadReadiness(this.selectedVersionId);
    this.refreshAutomaticComparison();
  }

  loadFlow(versionId: number) {
    this.flowLoading.set(true);
    this.api.getFlow(versionId).subscribe({
      next: flow => {
        this.flow.set(flow);
        this.cacheFlowInteractionOptions(flow);
        this.generateFlowCaseSuggestions();
        this.flowLoading.set(false);
        if (this.isBrowser) setTimeout(() => this.setupOverviewResizeObserver());
      },
      error: () => {
        this.flow.set(null);
        this.interactionBlocksCache.set([]);
        this.interactionOptionsByBlock.set({});
        this.suggestedCases.set([]);
        this.flowLoading.set(false);
        if (this.isBrowser) setTimeout(() => this.setupOverviewResizeObserver());
      }
    });
  }

  compareRuns() {
    if (!this.baselineRunId || !this.candidateRunId) return;
    this.automaticComparisonRequestKey = null;
    this.comparisonLoading.set(true);
    this.api.compareEvaluationRuns(this.baselineRunId, this.candidateRunId).subscribe({
      next: comparison => {
        this.comparison.set(comparison);
        this.comparisonContext = {
          mode: 'manual',
          baselineRunId: this.baselineRunId!,
          candidateRunId: this.candidateRunId!,
        };
        this.comparisonExpanded.set(true);
        this.comparisonLoading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not compare runs');
        this.comparisonLoading.set(false);
      }
    });
  }

  comparisonStatusText() {
    if (this.comparisonLoading()) return 'Comparing...';
    if (this.comparisonContext?.mode === 'manual' && this.comparison()) {
      const baseline = this.comparisonBaselineRun();
      const candidate = this.comparisonCandidateRun();
      if (baseline && candidate) {
        return `v${this.versionNumber(baseline.version_id)} Baseline -> v${this.versionNumber(candidate.version_id)} Candidate`;
      }
    }
    const pair = this.automaticComparisonPair();
    if (!pair) return 'No comparable evaluation runs yet.';
    const baselineVersion = this.versionNumber(pair.baseline.version_id);
    const candidateVersion = this.versionNumber(pair.candidate.version_id);
    const comparison = this.comparison();
    if (!comparison || this.comparisonContext?.mode !== 'automatic') {
      return `v${baselineVersion} Production -> v${candidateVersion} Candidate`;
    }
    return `${comparison.regressions || 0} regression${comparison.regressions === 1 ? '' : 's'}`;
  }

  comparisonSummaryText() {
    if (this.comparisonContext?.mode === 'manual' && this.comparison()) {
      const baseline = this.comparisonBaselineRun();
      const candidate = this.comparisonCandidateRun();
      const comparison = this.comparison();
      if (baseline && candidate && comparison) {
        const scoreText = `Score ${baseline.overall_score ?? 0}% -> ${candidate.overall_score ?? 0}%`;
        return `${scoreText} · ${comparison.regressions || 0} regression${comparison.regressions === 1 ? '' : 's'}`;
      }
    }
    const pair = this.automaticComparisonPair();
    if (!pair) return 'Run the same dataset against the current production and candidate versions to compare them.';
    const comparison = this.comparisonContext?.mode === 'automatic' ? this.comparison() : null;
    const scoreText = `Score ${pair.baseline.overall_score ?? 0}% -> ${pair.candidate.overall_score ?? 0}%`;
    if (!comparison) return scoreText;
    return `${scoreText} · ${comparison.regressions || 0} regression${comparison.regressions === 1 ? '' : 's'}`;
  }

  comparisonHelperText() {
    if (this.comparisonContext?.mode === 'manual') {
      return 'Manual comparisons are for investigation; release readiness remains the source of truth for publication.';
    }
    return 'Regressions may block publication based on the current release policy.';
  }

  comparisonUnavailableReason() {
    const dataset = this.selectedDataset();
    const production = this.currentProductionVersion();
    const candidate = this.selectedVersion();
    if (!candidate) return 'Select a candidate version to compare.';
    if (!production) return 'No current production version is available yet.';
    if (production.id === candidate.id) return 'The selected version is already production.';
    if (!dataset) return 'Select an evaluation dataset to compare.';
    const baseline = this.latestCompletedRunForVersionAndDataset(production.id, dataset.id);
    const candidateRun = this.latestCompletedRunForVersionAndDataset(candidate.id, dataset.id);
    if (!baseline && !candidateRun) return 'Run this dataset against production and the candidate version first.';
    if (!baseline) return `Run this dataset against v${production.version_number} production first.`;
    if (!candidateRun) return `Run this dataset against v${candidate.version_number} candidate first.`;
    return 'No comparable evaluation runs yet.';
  }

  comparisonBaselineRun() {
    if (!this.comparisonContext) return this.automaticComparisonPair()?.baseline || null;
    return this.runs().find((run: any) => run.id === this.comparisonContext?.baselineRunId) || null;
  }

  comparisonCandidateRun() {
    if (!this.comparisonContext) return this.automaticComparisonPair()?.candidate || null;
    return this.runs().find((run: any) => run.id === this.comparisonContext?.candidateRunId) || null;
  }

  comparisonBaselineTitle() {
    const run = this.comparisonBaselineRun();
    if (!run) return 'Production';
    return this.comparisonContext?.mode === 'manual' ? 'Baseline' : 'Production';
  }

  comparisonCandidateTitle() {
    const run = this.comparisonCandidateRun();
    if (!run) return 'Candidate';
    return this.comparisonContext?.mode === 'manual' ? 'Candidate' : 'Candidate';
  }

  comparisonRunOptionLabel(run: any) {
    return `v${this.versionNumber(run.version_id)} · run-${run.id} · ${run.overall_score ?? 0}% · ${this.shortRunDate(run)}`;
  }

  comparisonChangeTone(item: any) {
    const state = String(item?.state || '').toLowerCase();
    if (state.includes('regression')) return 'regression';
    if (state.includes('fixed') || state.includes('improved')) return 'positive';
    return 'neutral';
  }

  comparisonScoreChange() {
    const value = this.comparison()?.overall_score_delta;
    if (value === null || value === undefined) return 'n/a';
    return value > 0 ? `+${value}` : String(value);
  }

  selectedSuggestionCount() {
    return this.selectedSuggestionIds().size;
  }

  addSelectedSuggestionsLabel() {
    const count = this.selectedSuggestionCount();
    if (!count) return 'Add selected';
    return `Add ${count} selected`;
  }

  suggestionTurnCount(item: any) {
    const count = item?.turns?.length || 0;
    return `${count} turn${count === 1 ? '' : 's'}`;
  }

  suggestionPathSummary(item: any) {
    if (item?.expected_final_node_id) return `Expected final: ${this.nodeName(item.expected_final_node_id)}`;
    const path = (item?.expected_flow_node_ids || []).map((nodeKey: string) => this.nodeName(nodeKey));
    return path.length ? `Expected path: ${path.join(' -> ')}` : 'Expected path: none';
  }

  policySummaryText(policy = this.policy()) {
    if (!policy) return 'Policy not available';
    const required = policy.required_before_publish ? 'Evaluation required' : 'Evaluation optional';
    const score = policy.minimum_score === null || policy.minimum_score === undefined ? 'No minimum score' : `Minimum ${policy.minimum_score}%`;
    const regressions = policy.block_on_regression ? 'Regression blocking ON' : 'Regression blocking OFF';
    return `${required} · ${score} · ${regressions}`;
  }

  policyDatasetLabel(policy = this.policy()) {
    if (!policy?.required_dataset_id) return 'Any completed dataset';
    return this.datasetName(policy.required_dataset_id);
  }

  savePolicy() {
    if (!this.canManageWorkspace()) return;
    const policy = this.policy();
    if (!policy) return;
    this.saving.set(true);
    this.api.updateEvaluationPolicy(this.chatbotId, policy).subscribe({
      next: saved => {
        this.policy.set(saved);
        this.saving.set(false);
        this.message.set('Evaluation publish policy saved.');
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not save evaluation policy');
        this.saving.set(false);
      }
    });
  }

  latestRun() {
    return this.runs()[0] || null;
  }

  selectedVersion() {
    return this.versions().find((version: any) => version.id === this.selectedVersionId) || null;
  }

  currentProductionVersion() {
    return this.versions().find((version: any) => version.is_active)
      || this.versions().find((version: any) => version.status === 'published')
      || null;
  }

  headerTitle() {
    const assistantName = this.chatbot()?.name || `Assistant ${this.chatbotId}`;
    const version = this.selectedVersion();
    if (!version) return assistantName;
    return `${assistantName} · v${version.version_number} ${this.selectedVersionStatusLabel()}`;
  }

  selectedVersionRun() {
    return this.latestRunForSelectedVersion();
  }

  selectedVersionScore() {
    return this.selectedVersionRun()?.overall_score ?? null;
  }

  selectedVersionCasesPassed() {
    const run = this.selectedVersionRun();
    if (!run?.total_cases) return 'No runs';
    return `${run.passed_cases || 0} / ${run.total_cases}`;
  }

  selectedVersionRegressionCount() {
    return this.evaluationCheck()?.metadata?.comparison_regressions ?? null;
  }

  regressionSummaryText() {
    const regressions = this.selectedVersionRegressionCount();
    if (regressions === null) return 'Not available';
    return String(regressions);
  }

  readinessHeadline(report = this.readiness()) {
    if (!report) return 'Checking release readiness';
    const blocked = this.blockedChecks(report);
    if (blocked.length) {
      return blocked.length === 1 ? 'Publication blocked · 1 blocker' : `Publication blocked · ${blocked.length} blockers`;
    }
    const warnings = this.warningChecks(report);
    if (warnings.length) {
      return `Ready with ${warnings.length} warning${warnings.length === 1 ? '' : 's'}`;
    }
    return 'Ready to publish';
  }

  readinessInlineIssue(report = this.readiness()) {
    const blocked = this.blockedChecks(report);
    if (blocked.length) {
      return this.condenseReadinessMessage(blocked[0].message);
    }
    const warnings = this.warningChecks(report);
    if (warnings.length) {
      return warnings[0].message || warnings[0].label;
    }
    return '';
  }

  loadReadiness(versionId = this.selectedVersionId) {
    if (!versionId) return;
    this.readinessLoading.set(true);
    this.api.getVersionReadiness(versionId).subscribe({
      next: readiness => {
        this.readiness.set(readiness);
        this.readinessLoading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load release readiness');
        this.readinessLoading.set(false);
      }
    });
  }

  publishSelectedVersion() {
    if (!this.canManageWorkspace()) return;
    const version = this.selectedVersion();
    if (!version || version.status === 'published') return;
    this.publishing.set(true);
    this.error.set('');
    this.api.getVersionReadiness(version.id).subscribe({
      next: readiness => {
        this.readiness.set(readiness);
        const blocked = this.blockedChecks(readiness);
        const warnings = this.warningChecks(readiness);
        if (blocked.length) {
          this.readinessExpanded.set(true);
          this.error.set(`Publication blocked: ${blocked.map((check: any) => check.message || check.label).join(' ')}`);
          this.publishing.set(false);
          return;
        }
        this.pendingPublishConfirm.set({
          type: warnings.length ? 'warning' : 'ready',
          versionId: version.id,
          versionNumber: version.version_number,
          readiness,
          warnings,
        });
        this.publishing.set(false);
      },
      error: err => {
        this.error.set(this.publishError(err));
        this.publishing.set(false);
      }
    });
  }

  confirmPublishSelectedVersion() {
    if (!this.canManageWorkspace()) return;
    const pending = this.pendingPublishConfirm();
    if (!pending) return;
    this.publishing.set(true);
    this.api.publishVersion(pending.versionId, pending.type === 'warning').subscribe({
      next: () => {
        this.pendingPublishConfirm.set(null);
        this.publishing.set(false);
        this.message.set(`Version v${pending.versionNumber} published.`);
        this.loadVersions(pending.versionId);
        this.loadRuns();
      },
      error: err => {
        const readiness = err?.error?.detail?.readiness;
        if (readiness) {
          this.readiness.set(readiness);
          this.readinessExpanded.set(true);
        }
        this.error.set(this.publishError(err));
        this.publishing.set(false);
      }
    });
  }

  cancelPublishConfirm() {
    if (this.publishing()) return;
    this.pendingPublishConfirm.set(null);
  }

  toggleSuggestedCases() {
    this.suggestedCasesExpanded.set(!this.suggestedCasesExpanded());
  }

  toggleComparison() {
    this.comparisonExpanded.set(!this.comparisonExpanded());
  }

  toggleManualComparison() {
    this.manualComparisonVisible.set(!this.manualComparisonVisible());
  }

  togglePolicy() {
    this.policyExpanded.set(!this.policyExpanded());
  }

  toggleReadiness() {
    this.readinessExpanded.set(!this.readinessExpanded());
  }

  toggleRunExpansion(run: any) {
    if (this.expandedRunId() === run.id) {
      this.expandedRunId.set(null);
      return;
    }
    this.expandedRunId.set(run.id);
  }

  toggleRunHistoryVisibility() {
    this.showAllRuns.set(!this.showAllRuns());
  }

  passedRate(run: any) {
    if (!run?.total_cases) return '0/0';
    return `${run.passed_cases || 0}/${run.total_cases}`;
  }

  visibleRuns() {
    const runs = this.runs();
    return this.showAllRuns() ? runs : runs.slice(0, 5);
  }

  latestRunForSelectedVersion() {
    return this.runs().find((run: any) => run.version_id === this.selectedVersionId) || null;
  }

  isLatestRunForSelectedVersion(run: any) {
    return this.latestRunForSelectedVersion()?.id === run.id;
  }

  datasetName(datasetId: number | null | undefined) {
    if (!datasetId) return 'Unknown dataset';
    return this.datasets().find((item: any) => item.id === datasetId)?.name || `Dataset ${datasetId}`;
  }

  runStatusTone(run: any) {
    if (run?.status === 'failed' || run?.status === 'error' || (run?.failed_cases || 0) > 0 || (run?.critical_failures || 0) > 0) {
      return 'failed';
    }
    if (run?.status === 'warning' || (run?.warning_cases || 0) > 0) {
      return 'warning';
    }
    if (run?.status === 'completed' && (run?.passed_cases || 0) > 0) {
      return 'passed';
    }
    return 'neutral';
  }

  runStatusLabel(run: any) {
    const status = String(run?.status || 'unknown');
    return status.charAt(0).toUpperCase() + status.slice(1);
  }

  runCasesSummary(run: any) {
    return `${this.passedRate(run)} passed`;
  }

  runCompletedAt(run: any) {
    return run?.completed_at || run?.created_at || run?.started_at || null;
  }

  shortRunDate(run: any) {
    const value = this.runCompletedAt(run);
    if (!value) return 'date unavailable';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'date unavailable';
    return date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  runDurationSeconds(run: any) {
    if (!run?.duration_ms) return 'n/a';
    return `${(run.duration_ms / 1000).toFixed(run.duration_ms >= 10000 ? 0 : 1)} s`;
  }

  versionNumber(versionId: number | null | undefined) {
    const version = this.versions().find((item: any) => item.id === versionId);
    return version?.version_number || versionId || 'unknown';
  }

  automaticComparisonPair() {
    const dataset = this.selectedDataset();
    const production = this.currentProductionVersion();
    const candidate = this.selectedVersion();
    if (!dataset || !production || !candidate || production.id === candidate.id) return null;
    const baseline = this.latestCompletedRunForVersionAndDataset(production.id, dataset.id);
    const candidateRun = this.latestCompletedRunForVersionAndDataset(candidate.id, dataset.id);
    return baseline && candidateRun ? { baseline, candidate: candidateRun } : null;
  }

  blockedChecks(report = this.readiness()) {
    return (report?.checks || []).filter((check: any) => check.status === 'BLOCKED');
  }

  warningChecks(report = this.readiness()) {
    return (report?.checks || []).filter((check: any) => check.status === 'WARNING');
  }

  evaluationCheck(report = this.readiness()) {
    return (report?.checks || []).find((check: any) => check.code === 'EVALUATION_REQUIRED') || null;
  }

  readinessStateLabel(report = this.readiness()) {
    if (!report) return 'Checking';
    if ((report.summary?.blocked || 0) > 0) return 'Blocked';
    if ((report.summary?.warnings || 0) > 0) return 'Warnings';
    return 'Ready';
  }

  readinessSummaryText(report = this.readiness()) {
    if (!report) return 'Checking release readiness';
    const blocked = this.blockedChecks(report);
    if (blocked.length) {
      if (blocked.length === 1) return `Blocked · ${this.condenseReadinessMessage(blocked[0].message)}`;
      return `Blocked · ${blocked.length} blockers`;
    }
    const warnings = this.warningChecks(report);
    if (warnings.length) {
      return `Warnings · ${warnings.length} item${warnings.length === 1 ? '' : 's'} to review`;
    }
    return 'Ready · All publish checks passed';
  }

  releaseStatusClass(report = this.readiness()) {
    const state = this.readinessStateLabel(report).toLowerCase();
    return `release-status-${state}`;
  }

  readinessStatusClass(status: string) {
    return `readiness-${String(status || '').toLowerCase()}`;
  }

  publishButtonDisabled() {
    const version = this.selectedVersion();
    return !this.canManageWorkspace()
      || !version
      || version.status === 'published'
      || this.publishing()
      || this.readinessLoading()
      || this.blockedChecks().length > 0;
  }

  publishButtonLabel() {
    const version = this.selectedVersion();
    if (!version) return 'Publish';
    if (this.publishing()) return 'Publishing...';
    return `Publish v${version.version_number}`;
  }

  readinessToggleLabel() {
    return this.readinessExpanded() ? 'Hide readiness' : 'View readiness';
  }

  selectedVersionStatusLabel() {
    const status = this.selectedVersion()?.status || 'draft';
    return status.charAt(0).toUpperCase() + status.slice(1);
  }

  publishDialogTitle() {
    const pending = this.pendingPublishConfirm();
    if (!pending) return '';
    return pending.type === 'warning'
      ? 'Publish with warnings?'
      : `Publish v${pending.versionNumber}?`;
  }

  publishDialogPrimaryMessage() {
    const pending = this.pendingPublishConfirm();
    if (!pending) return '';
    if (pending.type === 'warning') {
      return `This version has ${pending.warnings.length} warning${pending.warnings.length === 1 ? '' : 's'}. Publishing is allowed, but confirm that you reviewed them.`;
    }
    return '';
  }

  publishDialogActionLabel() {
    const pending = this.pendingPublishConfirm();
    if (!pending) return '';
    return pending.type === 'warning' ? 'Publish anyway' : `Publish v${pending.versionNumber}`;
  }

  publishDialogRegressions() {
    return this.evaluationCheck(this.pendingPublishConfirm()?.readiness)?.metadata?.comparison_regressions ?? 0;
  }

  publishDialogScore() {
    return this.evaluationCheck(this.pendingPublishConfirm()?.readiness)?.metadata?.score ?? this.latestRunForSelectedVersion()?.overall_score ?? 0;
  }

  publishDialogCriticalFailures() {
    return this.evaluationCheck(this.pendingPublishConfirm()?.readiness)?.metadata?.critical_failures ?? this.latestRunForSelectedVersion()?.critical_failures ?? 0;
  }

  publishError(err: any) {
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

  condenseReadinessMessage(message: string) {
    return String(message || '')
      .replace(/^Publication blocked:\s*/i, '')
      .replace(/\.$/, '');
  }

  failedAssertions(result: any) {
    return (result?.assertion_results || []).filter((item: any) => item.status !== 'passed');
  }

  flowNodes() {
    return this.flow()?.nodes || [];
  }

  flowTransitions() {
    return this.flow()?.transitions || [];
  }

  flowBounds() {
    const nodes = this.flowNodes();
    if (!nodes.length) return { width: 840, height: 360, minX: 0, minY: 0 };
    const minX = Math.min(...nodes.map((node: any) => node.position_x || 0));
    const minY = Math.min(...nodes.map((node: any) => node.position_y || 0));
    const maxX = Math.max(...nodes.map((node: any) => (node.position_x || 0) + 190));
    const maxY = Math.max(...nodes.map((node: any) => (node.position_y || 0) + 96));
    return {
      minX,
      minY,
      width: Math.max(840, maxX - minX + 80),
      height: Math.max(320, maxY - minY + 80)
    };
  }

  overviewScale() {
    const bounds = this.flowBounds();
    const availableWidth = this.overviewWidth();
    if (!availableWidth || !bounds.width || !bounds.height) return 1;
    const widthScale = Math.max(0.35, (availableWidth - 8) / bounds.width);
    const heightScale = 320 / bounds.height;
    return Math.min(1, widthScale, heightScale);
  }

  overviewHeight() {
    const bounds = this.flowBounds();
    const height = Math.round(bounds.height * this.overviewScale());
    return Math.max(180, Math.min(320, height || 220));
  }

  overviewTransform() {
    return `scale(${this.overviewScale()})`;
  }

  nodeLeft(node: any) {
    const bounds = this.flowBounds();
    return (node.position_x || 0) - bounds.minX + 28;
  }

  nodeTop(node: any) {
    const bounds = this.flowBounds();
    return (node.position_y || 0) - bounds.minY + 28;
  }

  transitionPath(transition: any) {
    const source = this.flowNodes().find((node: any) => node.node_key === transition.source_node_key);
    const target = this.flowNodes().find((node: any) => node.node_key === transition.target_node_key);
    if (!source || !target) return '';
    const bounds = this.flowBounds();
    const x1 = (source.position_x || 0) - bounds.minX + 208;
    const y1 = (source.position_y || 0) - bounds.minY + 76;
    const x2 = (target.position_x || 0) - bounds.minX + 28;
    const y2 = (target.position_y || 0) - bounds.minY + 76;
    const mid = Math.max(32, Math.abs(x2 - x1) / 2);
    return `M ${x1} ${y1} C ${x1 + mid} ${y1}, ${x2 - mid} ${y2}, ${x2} ${y2}`;
  }

  transitionLabelLeft(transition: any) {
    const source = this.flowNodes().find((node: any) => node.node_key === transition.source_node_key);
    const target = this.flowNodes().find((node: any) => node.node_key === transition.target_node_key);
    if (!source || !target) return 0;
    const bounds = this.flowBounds();
    const x1 = (source.position_x || 0) - bounds.minX + 208;
    const x2 = (target.position_x || 0) - bounds.minX + 28;
    return Math.round((x1 + x2) / 2 - 44);
  }

  transitionLabelTop(transition: any) {
    const source = this.flowNodes().find((node: any) => node.node_key === transition.source_node_key);
    const target = this.flowNodes().find((node: any) => node.node_key === transition.target_node_key);
    if (!source || !target) return 0;
    const bounds = this.flowBounds();
    const y1 = (source.position_y || 0) - bounds.minY + 76;
    const y2 = (target.position_y || 0) - bounds.minY + 76;
    return Math.round((y1 + y2) / 2 - 14);
  }

  actualVisitedKeys(result = this.selectedResult()) {
    return new Set((result?.actual_visited_nodes || []).map((node: any) => node.node_key).filter(Boolean));
  }

  expectedVisitedKeys(result = this.selectedResult()) {
    return new Set(result?.case_snapshot?.expected_flow_node_ids || []);
  }

  forbiddenVisitedKeys(result = this.selectedResult()) {
    return new Set(result?.case_snapshot?.forbidden_flow_node_ids || []);
  }

  missingExpectedKeys(result = this.selectedResult()) {
    const actual = this.actualVisitedKeys(result);
    return [...this.expectedVisitedKeys(result)].filter(key => !actual.has(key));
  }

  isActualNode(node: any, result = this.selectedResult()) {
    return this.actualVisitedKeys(result).has(node.node_key);
  }

  isExpectedNode(node: any, result = this.selectedResult()) {
    return this.expectedVisitedKeys(result).has(node.node_key);
  }

  isMissingNode(node: any, result = this.selectedResult()) {
    return this.missingExpectedKeys(result).includes(node.node_key);
  }

  isForbiddenHit(node: any, result = this.selectedResult()) {
    return this.actualVisitedKeys(result).has(node.node_key) && this.forbiddenVisitedKeys(result).has(node.node_key);
  }

  isFinalNode(node: any, result = this.selectedResult()) {
    const visited = result?.actual_visited_nodes || [];
    const lastVisited = visited[visited.length - 1]?.node_key;
    return result?.case_snapshot?.expected_final_node_id === node.node_key || lastVisited === node.node_key;
  }

  nodeClass(node: any, result = this.selectedResult()) {
    return {
      actual: this.isActualNode(node, result),
      expected: this.isExpectedNode(node, result),
      missing: this.isMissingNode(node, result),
      forbidden: this.isForbiddenHit(node, result),
      final: result?.case_snapshot?.expected_final_node_id === node.node_key
    };
  }

  transitionClass(transition: any, result = this.selectedResult()) {
    const actual = this.actualVisitedKeys(result);
    const expected = this.expectedVisitedKeys(result);
    return {
      actual: actual.has(transition.source_node_key) && actual.has(transition.target_node_key),
      expected: expected.has(transition.source_node_key) && expected.has(transition.target_node_key)
    };
  }

  selectResult(result: any) {
    this.selectedResult.set(result);
  }

  openCaseResults(result: any) {
    this.selectedResult.set(result);
  }

  backToRunResults() {
    this.selectedResult.set(null);
  }

  closeRunResults() {
    this.selectedRun.set(null);
    this.selectedResult.set(null);
    if (this.activeDrawer() === 'run') {
      this.activeDrawer.set(null);
    }
  }

  closeActiveDrawer() {
    if (this.activeDrawer() === 'case') {
      this.cancelCaseEdit();
      return;
    }
    if (this.activeDrawer() === 'run') {
      this.closeRunResults();
    }
  }

  isRunResultsDetailOpen() {
    return !!this.selectedResult();
  }

  runDrawerScore(run: any) {
    return run?.overall_score ?? 0;
  }

  runDrawerVersionLabel(run: any) {
    if (!run) return 'Unknown version';
    const version = this.versions().find((item: any) => item.id === run.version_id);
    return version ? `v${version.version_number}` : `v${run.version_id}`;
  }

  runSummaryCasesText(run: any) {
    const total = run?.total_cases || 0;
    const passed = run?.passed_cases || 0;
    return `${passed} / ${total} passed`;
  }

  resultTone(result: any) {
    const status = String(result?.status || '').toLowerCase();
    if (status === 'passed') return 'passed';
    if (status === 'warning') return 'warning';
    return 'failed';
  }

  resultStatusLabel(result: any) {
    const status = String(result?.status || 'unknown');
    return status.charAt(0).toUpperCase() + status.slice(1);
  }

  resultFailedAssertionsSummary(result: any) {
    const failed = this.failedAssertions(result).length;
    if (!failed) return 'No failed assertions.';
    return `${failed} failed assertion${failed === 1 ? '' : 's'}`;
  }

  editorTitle() {
    return this.editingCaseId ? 'Edit evaluation case' : 'New evaluation case';
  }

  editorPrimaryAction() {
    if (this.saving()) return 'Saving...';
    return 'Save case';
  }

  showExpectedHandoffControl() {
    return this.flowNodes().some((node: any) => node.type === 'handoff') || this.caseForm.expected_handoff !== null;
  }

  selectedFlowLabels(value: string) {
    return this.list(value).map(nodeKey => this.nodeName(nodeKey));
  }

  finalBlockLabel() {
    return this.caseForm.expected_final_node_id ? this.nodeName(this.caseForm.expected_final_node_id) : 'Any end point';
  }

  blockTypeLabel(type: string) {
    const labels: Record<string, string> = {
      message: 'Message',
      buttons: 'Buttons',
      question: 'Question',
      collect_name: 'Collect name',
      collect_email: 'Collect email',
      collect_phone: 'Collect phone',
      meeting_scheduler: 'Meeting scheduler',
      handoff: 'Handoff',
      end: 'End'
    };
    return labels[type] || String(type || 'block').replace(/_/g, ' ');
  }

  nodeTooltip(node: any) {
    return `${node.label || node.node_key} • ${this.blockTypeLabel(node.type)} • ${node.node_key}`;
  }

  caseAssertionSummary(item: any) {
    const parts: string[] = [];
    if ((item.expected_keywords || []).length) parts.push(`${item.expected_keywords.length} keyword`);
    if ((item.forbidden_keywords || []).length) parts.push(`${item.forbidden_keywords.length} forbidden`);
    if ((item.expected_flow_node_ids || []).length || item.expected_final_node_id) parts.push('flow');
    if ((item.expected_source_patterns || []).length || (item.expected_source_document_ids || []).length) parts.push('sources');
    if (item.maximum_latency_ms) parts.push('latency');
    if (item.expected_handoff !== null || item.expected_fallback !== null) parts.push('runtime');
    return parts.length ? parts.join(' · ') : 'basic assertions';
  }

  caseTypeLabel(item: any) {
    if ((item.expected_source_patterns?.length || 0) || (item.expected_source_document_ids?.length || 0)) return 'RAG';
    if ((item.expected_flow_node_ids?.length || 0) || item.expected_final_node_id) return 'Flow';
    return 'Answer';
  }

  responsePreview(result: any) {
    return result.actual_response || 'No response captured.';
  }

  interactionBlocks() {
    return this.interactionBlocksCache();
  }

  interactionBlockLabel(node: any) {
    return `${node.label || node.node_key} (${node.node_key})`;
  }

  interactionTurnOptions(blockId: string) {
    return this.interactionOptionsByBlock()[blockId] || [];
  }

  hasInteractionBlock(blockId: string) {
    return this.flowNodes().some((item: any) => item.type === 'buttons' && item.node_key === blockId);
  }

  hasInteractionOption(blockId: string, value: string) {
    return this.interactionTurnOptions(blockId).includes(value);
  }

  addInteractionTurn() {
    this.caseForm.turns = [...(this.caseForm.turns || []), this.blankTurn('TEXT')];
  }

  removeInteractionTurn(index: number) {
    this.caseForm.turns = (this.caseForm.turns || []).filter((_: any, itemIndex: number) => itemIndex !== index);
  }

  moveInteractionTurn(index: number, delta: number) {
    const turns = [...(this.caseForm.turns || [])];
    const targetIndex = index + delta;
    if (targetIndex < 0 || targetIndex >= turns.length) return;
    const [item] = turns.splice(index, 1);
    turns.splice(targetIndex, 0, item);
    this.caseForm.turns = turns;
  }

  setInteractionTurnType(index: number, type: 'TEXT' | 'BUTTON_SELECTION') {
    this.caseForm.turns = (this.caseForm.turns || []).map((turn: any, itemIndex: number) => {
      if (itemIndex !== index) return turn;
      if (type === 'BUTTON_SELECTION') return { type, block_id: '', value: '' };
      return { type, value: turn?.value || '' };
    });
  }

  onInteractionBlockChange(index: number) {
    const turns = [...(this.caseForm.turns || [])];
    const turn = turns[index];
    if (!turn) return;
    const options = this.interactionTurnOptions(turn.block_id);
    if (!options.includes(turn.value)) {
      turn.value = '';
    }
    this.caseForm.turns = turns;
  }

  interactionTurnError(turn: any) {
    if (!turn) return null;
    const type = String(turn.type || 'TEXT').toUpperCase();
    if (type === 'TEXT') {
      return String(turn.value || '').trim() ? null : 'Enter a text message.';
    }
    if (type === 'BUTTON_SELECTION') {
      if (!String(turn.block_id || '').trim()) return 'Choose a buttons block.';
      if (!this.hasInteractionBlock(turn.block_id)) return 'Selected buttons block is not available in the chosen version.';
      if (!String(turn.value || '').trim()) return 'Choose an option.';
      if (!this.currentInteractionTurnOptions(turn.block_id).includes(turn.value)) return 'Selected option no longer belongs to this block.';
      return null;
    }
    return 'Choose a supported interaction type.';
  }

  turnValidationErrors() {
    return (this.caseForm.turns || [])
      .map((turn: any, index: number) => ({ index, error: this.interactionTurnError(turn) }))
      .filter((item: any) => item.error);
  }

  turnsContainStaleSelections() {
    return this.turnValidationErrors().some((item: any) => item.error?.includes('chosen version') || item.error?.includes('no longer belongs'));
  }

  expectedNodeSelections() {
    return this.list(this.caseForm.expected_flow_node_ids_text);
  }

  forbiddenNodeSelections() {
    return this.list(this.caseForm.forbidden_flow_node_ids_text);
  }

  isPickerExpectedNode(node: any) {
    return this.expectedNodeSelections().includes(node.node_key);
  }

  isPickerForbiddenNode(node: any) {
    return this.forbiddenNodeSelections().includes(node.node_key);
  }

  isPickerFinalNode(node: any) {
    return this.caseForm.expected_final_node_id === node.node_key;
  }

  setFlowSelectionMode(mode: 'expected' | 'forbidden' | 'final') {
    this.flowSelectionMode = mode;
  }

  onPickerNodeClick(node: any) {
    if (this.flowSelectionMode === 'expected') {
      this.toggleExpectedNode(node);
      return;
    }
    if (this.flowSelectionMode === 'forbidden') {
      this.toggleForbiddenNode(node);
      return;
    }
    this.setExpectedFinalNode(node);
  }

  toggleExpectedNode(node: any) {
    const current = new Set(this.list(this.caseForm.expected_flow_node_ids_text));
    current.has(node.node_key) ? current.delete(node.node_key) : current.add(node.node_key);
    this.caseForm.expected_flow_node_ids_text = [...current].join('|');
  }

  toggleForbiddenNode(node: any) {
    const current = new Set(this.list(this.caseForm.forbidden_flow_node_ids_text));
    current.has(node.node_key) ? current.delete(node.node_key) : current.add(node.node_key);
    this.caseForm.forbidden_flow_node_ids_text = [...current].join('|');
  }

  setExpectedFinalNode(node: any) {
    this.caseForm.expected_final_node_id = node.node_key;
  }

  nodeCoverage(node: any) {
    const cases = this.selectedDataset()?.cases || [];
    const covered = cases.filter((item: any) => (item.expected_flow_node_ids || []).includes(node.node_key));
    const critical = covered.filter((item: any) => item.critical);
    return { total: covered.length, critical: critical.length };
  }

  generateFlowCaseSuggestions() {
    const nodes = this.flowNodes();
    const transitions = this.flowTransitions();
    if (!nodes.length) {
      this.suggestedCases.set([]);
      return;
    }
    const byKey = new Map(nodes.map((node: any) => [node.node_key, node]));
    const start: any = byKey.get('start') || nodes[0];
    const suggestions: any[] = [];
    const addSuggestion = (item: any) => {
      if (!suggestions.some(existing => existing.id === item.id)) {
        suggestions.push({ critical: true, enabled: true, ...item });
      }
    };

    const firstTarget = transitions.find((item: any) => item.source_node_key === start.node_key)?.target_node_key;
    addSuggestion({
      id: `start-${start.node_key}`,
      type: 'Start',
      name: 'Start shows first assistant step',
      description: 'Checks that the assistant opens the flow and waits at the first actionable block.',
      turns: [{ type: 'TEXT', value: '' }],
      input_message: '',
      expected_flow_node_ids: [start.node_key],
      expected_final_node_id: firstTarget || start.node_key,
      tags: ['flow', 'start']
    });

    for (const node of nodes) {
      if (node.type === 'buttons') {
        for (const transition of transitions.filter((item: any) => item.source_node_key === node.node_key)) {
          const label = transition.label || 'next';
          const path = this.messagesToNode(node.node_key);
          addSuggestion({
            id: `button-${node.node_key}-${label}`,
            type: 'Button path',
            name: `${label} path reaches ${this.nodeName(transition.target_node_key)}`,
            description: `Selects "${label}" and verifies the flow reaches the expected branch.`,
            turns: [...path.messages, { type: 'BUTTON_SELECTION', block_id: node.node_key, value: label }],
            input_message: path.input_message || label,
            expected_flow_node_ids: [...path.nodes, node.node_key, transition.target_node_key],
            expected_final_node_id: transition.target_node_key,
            tags: ['flow', 'button']
          });
        }
      }

      if (node.type === 'collect_email') {
        const path = this.messagesToNode(node.node_key);
        addSuggestion({
          id: `invalid-email-${node.node_key}`,
          type: 'Invalid input',
          name: `${node.label || node.node_key} rejects invalid email`,
          description: 'Sends an invalid email and expects the flow to stay on the email block.',
          turns: [...path.messages, { type: 'TEXT', value: 'not-an-email' }],
          input_message: path.input_message || 'not-an-email',
          expected_keywords: ['valid email'],
          expected_flow_node_ids: [...path.nodes, node.node_key],
          expected_final_node_id: node.node_key,
          tags: ['flow', 'validation']
        });
      }

      if (node.type === 'collect_phone') {
        const path = this.messagesToNode(node.node_key);
        addSuggestion({
          id: `invalid-phone-${node.node_key}`,
          type: 'Invalid input',
          name: `${node.label || node.node_key} rejects invalid phone`,
          description: 'Sends an invalid phone number and expects the flow to stay on the phone block.',
          turns: [...path.messages, { type: 'TEXT', value: 'abc' }],
          input_message: path.input_message || 'abc',
          expected_keywords: ['valid phone'],
          expected_flow_node_ids: [...path.nodes, node.node_key],
          expected_final_node_id: node.node_key,
          tags: ['flow', 'validation']
        });
      }

      if (node.type === 'handoff') {
        const path = this.messagesToNode(node.node_key);
        addSuggestion({
          id: `handoff-${node.node_key}`,
          type: 'Handoff',
          name: `${node.label || node.node_key} handoff path`,
          description: 'Verifies that a route reaches the handoff block.',
          turns: path.messages,
          input_message: path.input_message || '',
          expected_flow_node_ids: [...path.nodes, node.node_key],
          expected_final_node_id: node.node_key,
          expected_handoff: true,
          tags: ['flow', 'handoff']
        });
      }
    }

    for (const terminal of nodes.filter((node: any) => node.type === 'end')) {
      const path = this.messagesToNode(terminal.node_key);
      if (path.messages.length) {
        addSuggestion({
          id: `terminal-${terminal.node_key}`,
          type: 'Complete path',
          name: `Path reaches ${terminal.label || terminal.node_key}`,
          description: 'Runs the shortest discovered path to this terminal block.',
          turns: path.messages,
          input_message: path.input_message || '',
          expected_flow_node_ids: path.nodes.filter((key: string) => key !== terminal.node_key),
          expected_final_node_id: terminal.node_key,
          tags: ['flow', 'complete-path']
        });
      }
    }

    this.suggestedCases.set(suggestions.slice(0, 24));
    this.selectedSuggestionIds.set(new Set(suggestions.slice(0, 6).map(item => item.id)));
  }

  messagesToNode(targetKey: string) {
    const nodes = this.flowNodes();
    const transitions = this.flowTransitions();
    const byKey = new Map(nodes.map((node: any) => [node.node_key, node]));
    const start: any = byKey.get('start') || nodes[0];
    const queue: any[] = [{
      key: start?.node_key,
      messages: start?.type === 'message' ? [{ type: 'TEXT', value: '' }] : [],
      nodes: start ? [start.node_key] : [],
      input_message: ''
    }];
    const seen = new Set<string>();
    while (queue.length) {
      const item = queue.shift();
      if (!item || seen.has(item.key)) continue;
      seen.add(item.key);
      if (item.key === targetKey) return { messages: item.messages, nodes: item.nodes, input_message: item.input_message || '' };
      const source: any = byKey.get(item.key);
      for (const transition of transitions.filter((edge: any) => edge.source_node_key === item.key)) {
        const target: any = byKey.get(transition.target_node_key);
        if (!target) continue;
        const messages: any[] = [...item.messages];
        let inputMessage = item.input_message;
        if (source?.type === 'buttons') messages.push({ type: 'BUTTON_SELECTION', block_id: source.node_key, value: transition.label || 'next' });
        if (source?.type === 'question') messages.push({ type: 'TEXT', value: 'Test answer' });
        if (source?.type === 'collect_name') messages.push({ type: 'TEXT', value: 'Alex Morgan' });
        if (source?.type === 'collect_email') messages.push({ type: 'TEXT', value: 'alex@example.com' });
        if (source?.type === 'collect_phone') messages.push({ type: 'TEXT', value: '+21612345678' });
        if (source?.type === 'meeting_scheduler') messages.push({ type: 'TEXT', value: 'Tomorrow at 10:00' });
        if (source?.type === 'message' && target.type === 'end') messages.push({ type: 'TEXT', value: '' });
        if (!inputMessage) {
          inputMessage = messages.find((turn: any) => turn.type === 'TEXT' && turn.value?.trim())?.value || '';
        }
        queue.push({ key: target.node_key, messages, nodes: [...item.nodes, target.node_key], input_message: inputMessage });
      }
    }
    return { messages: [], nodes: [], input_message: '' };
  }

  nodeName(nodeKey: string) {
    const node = this.flowNodes().find((item: any) => item.node_key === nodeKey);
    return node?.label || nodeKey;
  }

  toggleSuggestedCase(id: string) {
    const next = new Set(this.selectedSuggestionIds());
    next.has(id) ? next.delete(id) : next.add(id);
    this.selectedSuggestionIds.set(next);
  }

  createSelectedSuggestedCases() {
    if (!this.canManageWorkspace()) return;
    const dataset = this.selectedDataset();
    const selected = this.suggestedCases().filter(item => this.selectedSuggestionIds().has(item.id));
    if (!dataset || !selected.length) return;
    this.saving.set(true);
    const requests = selected.map(item => this.api.createEvaluationCase(dataset.id, {
      name: item.name,
      description: item.description,
      input_message: item.input_message || '',
      turns: item.turns || [],
      expected_keywords: item.expected_keywords || [],
      forbidden_keywords: item.forbidden_keywords || [],
      expected_flow_node_ids: item.expected_flow_node_ids || [],
      forbidden_flow_node_ids: item.forbidden_flow_node_ids || [],
      expected_final_node_id: item.expected_final_node_id || null,
      expected_handoff: item.expected_handoff ?? null,
      expected_fallback: item.expected_fallback ?? null,
      critical: item.critical,
      enabled: item.enabled,
      tags: item.tags || ['flow'],
      judge_config: { enabled: false }
    }));
    forkJoin(requests).subscribe({
      next: () => {
        this.message.set(`${selected.length} flow evaluation case${selected.length === 1 ? '' : 's'} added.`);
        this.selectedSuggestionIds.set(new Set());
        this.openDataset(dataset.id);
        this.saving.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not create suggested cases');
        this.saving.set(false);
      }
    });
  }

  actualPathText(result: any) {
    return (result?.actual_visited_nodes || []).map((node: any) => this.nodeName(node.node_key)).filter(Boolean).join(' -> ') || 'none';
  }

  expectedPathText(result: any) {
    return (result?.case_snapshot?.expected_flow_node_ids || []).map((nodeKey: any) => this.nodeName(String(nodeKey || ''))).join(' -> ') || 'none';
  }

  missingExpectedText(result: any) {
    return this.missingExpectedKeys(result).map((nodeKey: any) => this.nodeName(String(nodeKey || ''))).join(', ') || 'none';
  }

  forbiddenHitsText(result: any) {
    const forbidden = this.forbiddenVisitedKeys(result);
    return (result?.actual_visited_nodes || [])
      .map((node: any) => node?.node_key)
      .filter((nodeKey: string) => forbidden.has(nodeKey))
      .map((nodeKey: string) => this.nodeName(nodeKey))
      .join(', ') || 'none';
  }

  expectedVisitedText(result: any) {
    return (result?.case_snapshot?.expected_flow_node_ids || [])
      .map((nodeKey: string) => this.nodeName(nodeKey))
      .join(', ') || 'none';
  }

  list(value: string) {
    return (value || '').split('|').map(item => item.trim()).filter(Boolean);
  }

  private buildCasePayload() {
    const base = this.editingCaseOriginal ? this.casePayloadFromCase(this.editingCaseOriginal) : this.casePayloadFromCase(this.blankCase());
    return {
      ...base,
      name: this.caseForm.name,
      description: this.caseForm.description,
      order_index: this.caseForm.order_index,
      input_message: this.effectiveInputMessage(),
      turns: this.normalizedFormTurns(),
      initial_variables: this.caseForm.initial_variables || {},
      expected_response_mode: this.caseForm.expected_response_mode || null,
      expected_intent: this.caseForm.expected_intent || null,
      expected_keywords: this.list(this.caseForm.expected_keywords_text),
      forbidden_keywords: this.list(this.caseForm.forbidden_keywords_text),
      expected_source_document_ids: this.caseForm.expected_source_document_ids || [],
      expected_source_patterns: this.list(this.caseForm.expected_source_patterns_text),
      expected_flow_node_ids: this.list(this.caseForm.expected_flow_node_ids_text),
      forbidden_flow_node_ids: this.list(this.caseForm.forbidden_flow_node_ids_text),
      expected_final_node_id: this.caseForm.expected_final_node_id || null,
      expected_variable_assertions: this.caseForm.expected_variable_assertions || [],
      maximum_latency_ms: this.caseForm.maximum_latency_ms,
      minimum_retrieval_score: this.caseForm.minimum_retrieval_score,
      minimum_answer_score: this.caseForm.minimum_answer_score,
      minimum_source_count: this.caseForm.minimum_source_count,
      expected_fallback: this.caseForm.expected_fallback === '' ? null : this.caseForm.expected_fallback,
      expected_handoff: this.caseForm.expected_handoff === '' ? null : this.caseForm.expected_handoff,
      expected_failure_category: this.caseForm.expected_failure_category || null,
      critical: this.caseForm.critical,
      enabled: this.caseForm.enabled,
      tags: this.list(this.caseForm.tags_text),
      judge_config: this.caseForm.judge_config || { enabled: false }
    };
  }

  private caseToForm(caseItem: any) {
    return {
      ...this.blankCase(),
      ...this.cloneValue(caseItem),
      turns: this.normalizeCaseTurnsForForm(caseItem.turns || [], caseItem.input_message),
      expected_keywords_text: (caseItem.expected_keywords || []).join('|'),
      forbidden_keywords_text: (caseItem.forbidden_keywords || []).join('|'),
      expected_source_patterns_text: (caseItem.expected_source_patterns || []).join('|'),
      expected_flow_node_ids_text: (caseItem.expected_flow_node_ids || []).join('|'),
      forbidden_flow_node_ids_text: (caseItem.forbidden_flow_node_ids || []).join('|'),
      expected_final_node_id: caseItem.expected_final_node_id || '',
      tags_text: (caseItem.tags || []).join('|')
    };
  }

  private casePayloadFromCase(source: any) {
    return {
      name: source.name || '',
      description: source.description ?? null,
      order_index: source.order_index ?? null,
      input_message: source.input_message || '',
      turns: source.turns || [],
      initial_variables: source.initial_variables || {},
      expected_response_mode: source.expected_response_mode ?? null,
      expected_intent: source.expected_intent ?? null,
      expected_keywords: source.expected_keywords || [],
      forbidden_keywords: source.forbidden_keywords || [],
      expected_source_document_ids: source.expected_source_document_ids || [],
      expected_source_patterns: source.expected_source_patterns || [],
      expected_flow_node_ids: source.expected_flow_node_ids || [],
      forbidden_flow_node_ids: source.forbidden_flow_node_ids || [],
      expected_final_node_id: source.expected_final_node_id ?? null,
      expected_variable_assertions: source.expected_variable_assertions || [],
      maximum_latency_ms: source.maximum_latency_ms ?? null,
      minimum_retrieval_score: source.minimum_retrieval_score ?? null,
      minimum_answer_score: source.minimum_answer_score ?? null,
      minimum_source_count: source.minimum_source_count ?? null,
      expected_fallback: source.expected_fallback ?? null,
      expected_handoff: source.expected_handoff ?? null,
      expected_failure_category: source.expected_failure_category ?? null,
      critical: !!source.critical,
      enabled: source.enabled ?? true,
      tags: source.tags || [],
      judge_config: source.judge_config || { enabled: false }
    };
  }

  private upsertCaseInSelectedDataset(savedCase: any) {
    this.selectedDataset.update(dataset => {
      if (!dataset) return dataset;
      const cases = dataset.cases || [];
      const existingIndex = cases.findIndex((item: any) => item.id === savedCase.id);
      const nextCases = existingIndex >= 0
        ? cases.map((item: any) => item.id === savedCase.id ? savedCase : item)
        : [savedCase, ...cases];
      return { ...dataset, cases: nextCases };
    });
  }

  private focusCaseEditor() {
    if (!this.isBrowser) return;
    setTimeout(() => {
      this.caseNameInput?.nativeElement.focus();
      this.caseNameInput?.nativeElement.select();
    });
  }

  private setupOverviewResizeObserver() {
    const host = this.flowOverviewHost?.nativeElement;
    if (!host || typeof ResizeObserver === 'undefined') return;
    this.overviewResizeObserver?.disconnect();
    this.overviewResizeObserver = new ResizeObserver(entries => {
      const entry = entries[0];
      const width = entry?.contentRect?.width || host.clientWidth || 0;
      this.overviewWidth.set(width);
    });
    this.overviewResizeObserver.observe(host);
    this.overviewWidth.set(host.clientWidth || 0);
  }

  private refreshAutomaticComparison() {
    const pair = this.automaticComparisonPair();
    if (!pair) {
      this.automaticComparisonRequestKey = null;
      this.comparisonLoading.set(false);
      if (!this.comparisonContext || this.comparisonContext.mode === 'automatic') {
        this.comparison.set(null);
        this.comparisonContext = null;
      }
      return;
    }

    this.baselineRunId = pair.baseline.id;
    this.candidateRunId = pair.candidate.id;
    const requestKey = `${pair.baseline.id}:${pair.candidate.id}`;

    if (this.manualComparisonVisible() && this.comparisonContext?.mode === 'manual') return;
    if (this.automaticComparisonRequestKey === requestKey) return;
    if (
      this.comparisonContext?.mode === 'automatic'
      && this.comparisonContext.baselineRunId === pair.baseline.id
      && this.comparisonContext.candidateRunId === pair.candidate.id
    ) {
      return;
    }

    this.automaticComparisonRequestKey = requestKey;
    this.comparisonLoading.set(true);
    this.api.compareEvaluationRuns(pair.baseline.id, pair.candidate.id).subscribe({
      next: comparison => {
        if (this.automaticComparisonRequestKey !== requestKey) return;
        this.comparison.set(comparison);
        this.comparisonContext = {
          mode: 'automatic',
          baselineRunId: pair.baseline.id,
          candidateRunId: pair.candidate.id,
        };
        this.automaticComparisonRequestKey = null;
        this.comparisonLoading.set(false);
      },
      error: err => {
        if (this.automaticComparisonRequestKey !== requestKey) return;
        this.error.set(err.error?.detail || 'Could not compare runs');
        this.comparison.set(null);
        this.comparisonContext = null;
        this.automaticComparisonRequestKey = null;
        this.comparisonLoading.set(false);
      }
    });
  }

  private latestCompletedRunForVersionAndDataset(versionId: number, datasetId: number) {
    return this.runs()
      .filter((run: any) => run.version_id === versionId && run.dataset_id === datasetId && this.isCompletedRun(run))
      .sort((a: any, b: any) => this.runSortValue(b) - this.runSortValue(a))[0] || null;
  }

  private isCompletedRun(run: any) {
    return String(run?.status || '').toLowerCase() === 'completed';
  }

  private runSortValue(run: any) {
    const timestamp = new Date(this.runCompletedAt(run) || 0).getTime();
    return Number.isNaN(timestamp) ? Number(run?.id || 0) : timestamp;
  }

  canManageWorkspace() {
    return this.auth.canManageWorkspace();
  }

  private cacheFlowInteractionOptions(flow: any) {
    const nodes = flow?.nodes || [];
    const transitions = flow?.transitions || [];
    const buttonBlocks = nodes.filter((node: any) => node.type === 'buttons');
    const optionsByBlock = buttonBlocks.reduce((acc: Record<string, string[]>, node: any) => {
      const configOptions = Array.isArray(node.config?.buttons) ? node.config.buttons : [];
      const transitionOptions = transitions
        .filter((transition: any) => transition.source_node_key === node.node_key && transition.label)
        .map((transition: any) => transition.label);
      const options = (configOptions.length ? configOptions : transitionOptions)
        .map((item: any) => String(item || '').trim())
        .filter(Boolean);
      acc[node.node_key] = [...new Set<string>(options)];
      return acc;
    }, {});
    this.interactionBlocksCache.set(buttonBlocks);
    this.interactionOptionsByBlock.set(optionsByBlock);
  }

  private currentInteractionTurnOptions(blockId: string) {
    const node = this.flowNodes().find((item: any) => item.type === 'buttons' && item.node_key === blockId);
    if (!node) return [];
    const configOptions = Array.isArray(node.config?.buttons) ? node.config.buttons : [];
    const transitionOptions = this.flowTransitions()
      .filter((transition: any) => transition.source_node_key === blockId && transition.label)
      .map((transition: any) => transition.label);
    return [...new Set<string>((configOptions.length ? configOptions : transitionOptions)
      .map((item: any) => String(item || '').trim())
      .filter(Boolean))];
  }

  private cloneValue<T>(value: T): T {
    return value == null ? value : JSON.parse(JSON.stringify(value));
  }

  private blankTurn(type: 'TEXT' | 'BUTTON_SELECTION') {
    return type === 'BUTTON_SELECTION'
      ? { type, block_id: '', value: '' }
      : { type, value: '' };
  }

  private normalizeCaseTurnsForForm(turns: any[], inputMessage: string) {
    if (!Array.isArray(turns) || !turns.length) {
      return inputMessage ? [{ type: 'TEXT', value: inputMessage }] : [];
    }
    return turns.map(turn => {
      if (typeof turn === 'string') return { type: 'TEXT', value: turn };
      if (turn?.type === 'BUTTON_SELECTION') {
        return {
          type: 'BUTTON_SELECTION',
          block_id: turn.block_id || turn.node_key || '',
          value: turn.value || turn.message || ''
        };
      }
      return {
        type: 'TEXT',
        value: turn?.value || turn?.message || ''
      };
    });
  }

  private normalizedFormTurns() {
    return (this.caseForm.turns || []).map((turn: any) => {
      if (String(turn?.type || '').toUpperCase() === 'BUTTON_SELECTION') {
        return {
          type: 'BUTTON_SELECTION',
          block_id: String(turn.block_id || '').trim(),
          value: String(turn.value || '').trim()
        };
      }
      return {
        type: 'TEXT',
        value: String(turn?.value || '').trim()
      };
    });
  }

  private effectiveInputMessage() {
    const explicit = String(this.caseForm.input_message || '').trim();
    if (explicit) return explicit;
    return this.normalizedFormTurns().find((turn: any) => turn.type === 'TEXT' && turn.value)?.value || '';
  }
}
