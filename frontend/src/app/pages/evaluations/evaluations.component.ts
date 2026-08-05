import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { forkJoin } from 'rxjs';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-evaluations',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './evaluations.component.html',
  styleUrls: ['./evaluations.component.css']
})
export class EvaluationsComponent implements OnInit {
  projectId = 0;
  chatbotId = 0;
  loading = signal(false);
  running = signal(false);
  saving = signal(false);
  error = signal('');
  message = signal('');
  datasets = signal<any[]>([]);
  versions = signal<any[]>([]);
  runs = signal<any[]>([]);
  selectedDataset = signal<any | null>(null);
  selectedRun = signal<any | null>(null);
  selectedResult = signal<any | null>(null);
  comparison = signal<any | null>(null);
  policy = signal<any | null>(null);
  flow = signal<any | null>(null);
  flowLoading = signal(false);
  suggestedCases = signal<any[]>([]);
  selectedSuggestionIds = signal<Set<string>>(new Set());
  newDataset = { name: '', description: '' };
  selectedVersionId: number | null = null;
  baselineRunId: number | null = null;
  candidateRunId: number | null = null;
  caseForm: any = this.blankCase();
  private isBrowser: boolean;

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    this.projectId = Number(this.route.snapshot.paramMap.get('projectId'));
    this.chatbotId = Number(this.route.snapshot.paramMap.get('chatbotId'));
    if (!this.isBrowser) return;
    this.loadAll();
  }

  blankCase() {
    return {
      name: '',
      description: '',
      input_message: '',
      expected_keywords_text: '',
      forbidden_keywords_text: '',
      expected_source_patterns_text: '',
      expected_flow_node_ids_text: '',
      forbidden_flow_node_ids_text: '',
      expected_final_node_id: '',
      maximum_latency_ms: null,
      minimum_retrieval_score: null,
      minimum_source_count: null,
      expected_fallback: null,
      expected_handoff: null,
      critical: false,
      enabled: true,
      tags_text: ''
    };
  }

  loadAll() {
    this.loading.set(true);
    this.error.set('');
    this.api.getEvaluationDatasets(this.chatbotId).subscribe({
      next: datasets => {
        this.datasets.set(datasets);
        if (datasets[0]) this.openDataset(datasets[0].id);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load evaluation datasets');
        this.loading.set(false);
      }
    });
    this.api.getVersionsByChatbot(this.chatbotId).subscribe({
      next: versions => {
        const sorted = versions.sort((a: any, b: any) => b.version_number - a.version_number);
        this.versions.set(sorted);
        this.selectedVersionId = sorted[0]?.id || null;
        if (this.selectedVersionId) this.loadFlow(this.selectedVersionId);
      }
    });
    this.loadRuns();
    this.loadPolicy();
  }

  loadRuns() {
    this.api.getEvaluationRuns(this.chatbotId).subscribe({
      next: runs => this.runs.set(runs),
      error: () => this.runs.set([])
    });
  }

  loadPolicy() {
    this.api.getEvaluationPolicy(this.chatbotId).subscribe({
      next: policy => this.policy.set(policy),
      error: () => this.policy.set(null)
    });
  }

  createDataset() {
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
      next: dataset => this.selectedDataset.set(dataset),
      error: err => this.error.set(err.error?.detail || 'Could not load dataset')
    });
  }

  saveCase() {
    const dataset = this.selectedDataset();
    if (!dataset || !this.caseForm.name.trim() || (!this.caseForm.input_message.trim() && !this.caseForm.turns?.length)) return;
    const payload = {
      name: this.caseForm.name,
      description: this.caseForm.description,
      input_message: this.caseForm.input_message,
      turns: this.caseForm.turns || [],
      expected_keywords: this.list(this.caseForm.expected_keywords_text),
      forbidden_keywords: this.list(this.caseForm.forbidden_keywords_text),
      expected_source_patterns: this.list(this.caseForm.expected_source_patterns_text),
      expected_flow_node_ids: this.list(this.caseForm.expected_flow_node_ids_text),
      forbidden_flow_node_ids: this.list(this.caseForm.forbidden_flow_node_ids_text),
      expected_final_node_id: this.caseForm.expected_final_node_id || null,
      maximum_latency_ms: this.caseForm.maximum_latency_ms,
      minimum_retrieval_score: this.caseForm.minimum_retrieval_score,
      minimum_source_count: this.caseForm.minimum_source_count,
      expected_fallback: this.caseForm.expected_fallback === '' ? null : this.caseForm.expected_fallback,
      expected_handoff: this.caseForm.expected_handoff === '' ? null : this.caseForm.expected_handoff,
      critical: this.caseForm.critical,
      enabled: this.caseForm.enabled,
      tags: this.list(this.caseForm.tags_text),
      judge_config: { enabled: false }
    };
    this.saving.set(true);
    this.api.createEvaluationCase(dataset.id, payload).subscribe({
      next: () => {
        this.caseForm = this.blankCase();
        this.openDataset(dataset.id);
        this.saving.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not save evaluation case');
        this.saving.set(false);
      }
    });
  }

  duplicateCase(caseId: number) {
    const dataset = this.selectedDataset();
    if (!dataset) return;
    this.api.duplicateEvaluationCase(caseId).subscribe({
      next: () => this.openDataset(dataset.id),
      error: err => this.error.set(err.error?.detail || 'Could not duplicate case')
    });
  }

  toggleCase(item: any) {
    const dataset = this.selectedDataset();
    if (!dataset) return;
    this.api.setEvaluationCaseEnabled(item.id, !item.enabled).subscribe({
      next: () => this.openDataset(dataset.id),
      error: err => this.error.set(err.error?.detail || 'Could not update case')
    });
  }

  runDataset() {
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
        this.openRun(run.id);
      },
      error: err => {
        this.running.set(false);
        this.error.set(err.error?.detail || 'Could not run evaluation');
      }
    });
  }

  openRun(runId: number) {
    this.api.getEvaluationRun(runId).subscribe({
      next: run => {
        this.selectedRun.set(run);
        this.selectedResult.set(run.results?.[0] || null);
        if (run.version_id) {
          this.selectedVersionId = run.version_id;
          this.loadFlow(run.version_id);
        }
      },
      error: err => this.error.set(err.error?.detail || 'Could not load run')
    });
  }

  onVersionChange() {
    if (this.selectedVersionId) this.loadFlow(this.selectedVersionId);
  }

  loadFlow(versionId: number) {
    this.flowLoading.set(true);
    this.api.getFlow(versionId).subscribe({
      next: flow => {
        this.flow.set(flow);
        this.generateFlowCaseSuggestions();
        this.flowLoading.set(false);
      },
      error: () => {
        this.flow.set(null);
        this.suggestedCases.set([]);
        this.flowLoading.set(false);
      }
    });
  }

  compareRuns() {
    if (!this.baselineRunId || !this.candidateRunId) return;
    this.api.compareEvaluationRuns(this.baselineRunId, this.candidateRunId).subscribe({
      next: comparison => this.comparison.set(comparison),
      error: err => this.error.set(err.error?.detail || 'Could not compare runs')
    });
  }

  savePolicy() {
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

  passedRate(run: any) {
    if (!run?.total_cases) return '0/0';
    return `${run.passed_cases || 0}/${run.total_cases}`;
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

  nodeStyle(node: any) {
    const bounds = this.flowBounds();
    return {
      left: `${(node.position_x || 0) - bounds.minX + 28}px`,
      top: `${(node.position_y || 0) - bounds.minY + 28}px`
    };
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

  toggleExpectedNode(node: any) {
    const current = new Set(this.list(this.caseForm.expected_flow_node_ids_text));
    current.has(node.node_key) ? current.delete(node.node_key) : current.add(node.node_key);
    this.caseForm.expected_flow_node_ids_text = [...current].join('|');
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
      turns: [{ message: '' }],
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
            turns: [...path.messages, { message: label }],
            input_message: label,
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
          turns: [...path.messages, { message: 'not-an-email' }],
          input_message: 'not-an-email',
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
          turns: [...path.messages, { message: 'abc' }],
          input_message: 'abc',
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
          input_message: path.messages[path.messages.length - 1]?.message || '',
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
          input_message: path.messages[path.messages.length - 1]?.message || '',
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
    const queue = [{
      key: start?.node_key,
      messages: start?.type === 'message' ? [{ message: '' }] : [],
      nodes: start ? [start.node_key] : []
    }];
    const seen = new Set<string>();
    while (queue.length) {
      const item = queue.shift();
      if (!item || seen.has(item.key)) continue;
      seen.add(item.key);
      if (item.key === targetKey) return { messages: item.messages, nodes: item.nodes };
      const source: any = byKey.get(item.key);
      for (const transition of transitions.filter((edge: any) => edge.source_node_key === item.key)) {
        const target: any = byKey.get(transition.target_node_key);
        if (!target) continue;
        const messages = [...item.messages];
        if (source?.type === 'buttons') messages.push({ message: transition.label || 'next' });
        if (source?.type === 'question') messages.push({ message: 'Test answer' });
        if (source?.type === 'collect_name') messages.push({ message: 'Alex Morgan' });
        if (source?.type === 'collect_email') messages.push({ message: 'alex@example.com' });
        if (source?.type === 'collect_phone') messages.push({ message: '+21612345678' });
        if (source?.type === 'meeting_scheduler') messages.push({ message: 'Tomorrow at 10:00' });
        if (source?.type === 'message' && target.type === 'end') messages.push({ message: '' });
        queue.push({ key: target.node_key, messages, nodes: [...item.nodes, target.node_key] });
      }
    }
    return { messages: [], nodes: [] };
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
    return (result?.actual_visited_nodes || []).map((node: any) => node.node_key).filter(Boolean).join(' -> ') || 'none';
  }

  expectedPathText(result: any) {
    return (result?.case_snapshot?.expected_flow_node_ids || []).join(' -> ') || 'none';
  }

  missingExpectedText(result: any) {
    return this.missingExpectedKeys(result).join(', ') || 'none';
  }

  list(value: string) {
    return (value || '').split('|').map(item => item.trim()).filter(Boolean);
  }
}
