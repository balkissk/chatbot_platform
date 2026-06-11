import { CommonModule, isPlatformBrowser } from '@angular/common';
import { AfterViewInit, Component, ElementRef, HostListener, Inject, OnInit, PLATFORM_ID, ViewChild, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';

type FlowNode = {
  id: number;
  node_key: string;
  type: string;
  label: string;
  config: Record<string, any>;
  position_x: number;
  position_y: number;
};

type FlowTransition = {
  id: number;
  source_node_key: string;
  target_node_key: string;
  label?: string;
  condition?: string;
};

@Component({
  selector: 'app-flow-builder',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './flow-builder.component.html',
  styleUrls: ['./flow-builder.component.css']
})
export class FlowBuilderComponent implements OnInit, AfterViewInit {
  @ViewChild('canvasViewport') canvasViewport?: ElementRef<HTMLElement>;
  projectId!: number;
  chatbotId!: number;

  context = signal<any | null>(null);
  nodes = signal<FlowNode[]>([]);
  transitions = signal<FlowTransition[]>([]);
  selectedNode = signal<FlowNode | null>(null);
  editorOpen = signal(false);
  sidebarCollapsed = signal(false);
  inspectorCollapsed = signal(false);
  inspectorTab = signal<'settings' | 'variables' | 'validation' | 'preview'>('settings');
  deleteConfirm = signal<{ type: 'node' | 'transition'; item: FlowNode | FlowTransition; title: string; message: string } | null>(null);
  loading = signal(false);
  saving = signal(false);
  error = signal('');
  message = signal('');

  nodeType = 'message';
  selectedTemplate = '';
  templates = signal<any[]>([]);
  applyingTemplate = signal(false);
  blockCategories = ['Basic', 'AI', 'Data Collection', 'Logic', 'Integration'];
  blockTypes = [
    { value: 'message', label: 'Message', icon: 'M', category: 'Basic', description: 'Send text and continue.', iconBg: '#ccfbf1', iconColor: '#0f766e' },
    { value: 'question', label: 'Question', icon: 'Q', category: 'Basic', description: 'Ask and save a response.', iconBg: '#dbeafe', iconColor: '#2563eb' },
    { value: 'buttons', label: 'Buttons', icon: 'B', category: 'Basic', description: 'Offer button choices.', iconBg: '#fef3c7', iconColor: '#b45309' },
    { value: 'end', label: 'End', icon: 'E', category: 'Basic', description: 'Close the conversation.', iconBg: '#f1f5f9', iconColor: '#475569' },
    { value: 'rag_answer', label: 'AI/RAG Answer', icon: 'AI', category: 'AI', description: 'Answer from AI and documents.', iconBg: '#ede9fe', iconColor: '#7c3aed' },
    { value: 'collect_name', label: 'Collect Name', icon: 'N', category: 'Data Collection', description: 'Capture visitor name.', iconBg: '#e0f2fe', iconColor: '#0369a1' },
    { value: 'collect_email', label: 'Collect Email', icon: '@', category: 'Data Collection', description: 'Capture and validate email.', iconBg: '#ecfccb', iconColor: '#4d7c0f' },
    { value: 'collect_phone', label: 'Collect Phone', icon: 'P', category: 'Data Collection', description: 'Capture and validate phone.', iconBg: '#fae8ff', iconColor: '#a21caf' },
    { value: 'condition', label: 'Condition', icon: 'IF', category: 'Logic', description: 'Route by variable value.', iconBg: '#ffedd5', iconColor: '#c2410c' },
    { value: 'set_variable', label: 'Set Variable', icon: 'V', category: 'Logic', description: 'Set a value manually.', iconBg: '#dcfce7', iconColor: '#15803d' },
    { value: 'api_request', label: 'API Request', icon: 'API', category: 'Integration', description: 'Call a webhook at runtime.', iconBg: '#ffe4e6', iconColor: '#e11d48' },
    { value: 'handoff', label: 'Handoff', icon: 'H', category: 'Integration', description: 'Route to a human team.', iconBg: '#cffafe', iconColor: '#0e7490' }
  ];
  conditionOperators = [
    { value: 'equals', label: 'equals' },
    { value: 'not_equals', label: 'does not equal' },
    { value: 'contains', label: 'contains' },
    { value: 'not_contains', label: 'does not contain' },
    { value: 'exists', label: 'exists' },
    { value: 'not_exists', label: 'does not exist' },
    { value: 'greater_than', label: 'greater than' },
    { value: 'greater_or_equal', label: 'greater or equal' },
    { value: 'less_than', label: 'less than' },
    { value: 'less_or_equal', label: 'less or equal' }
  ];
  actionTypes = [
    { value: 'set_variable', label: 'Set variable' },
    { value: 'handoff', label: 'Request handoff' },
    { value: 'end', label: 'End conversation' }
  ];
  responseLengths = [
    { value: 'short', label: 'Short' },
    { value: 'medium', label: 'Medium' },
    { value: 'long', label: 'Long' }
  ];

  documents = signal<any[]>([]);
  knowledgeLoading = signal(false);
  uploadLoading = signal(false);
  uploadError = signal('');
  selectedFileName = '';

  previewInput = '';
  validationErrors = signal<string[]>([]);
  previewMessages = signal<{ role: 'user' | 'bot'; text: string; options?: string[]; mode?: string; retrievalMode?: string; sources?: any[] }[]>([]);
  previewSessionId = signal<number | undefined>(undefined);
  previewLoading = signal(false);
  previewError = signal('');
  variableRows = computed(() => this.collectVariableRows());

  dragging = signal<number | undefined>(undefined);
  zoom = signal(1);
  private viewReady = false;
  private dragState: {
    nodeId: number;
    startPointerX: number;
    startPointerY: number;
    startNodeX: number;
    startNodeY: number;
  } | null = null;
  private panState: {
    startPointerX: number;
    startPointerY: number;
    startScrollLeft: number;
    startScrollTop: number;
  } | null = null;
  private isBrowser: boolean;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private api: ApiService,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    this.projectId = Number(this.route.snapshot.paramMap.get('projectId'));
    this.chatbotId = Number(this.route.snapshot.paramMap.get('chatbotId'));
    if (!this.isBrowser) return;
    this.loadBuilder();
  }

  ngAfterViewInit() {
    this.viewReady = true;
    setTimeout(() => this.fitToScreen(), 0);
  }

  loadBuilder() {
    this.loading.set(true);
    this.error.set('');

    this.api.getChatbotBuilder(this.chatbotId).subscribe({
      next: context => {
        this.context.set(context);
        this.nodes.set([...context.flow.nodes].sort((a, b) => a.position_y - b.position_y || a.position_x - b.position_x));
        this.transitions.set(context.flow.transitions || []);
        this.selectedNode.set(null);
        this.loading.set(false);
        this.loadTemplates();
        this.loadDocuments();
        setTimeout(() => this.fitToScreen(), 0);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load flow');
        this.loading.set(false);
      }
    });
  }

  loadTemplates() {
    this.api.getFlowTemplates().subscribe({
      next: templates => this.templates.set(templates.filter(template => template.key !== 'blank')),
      error: () => this.templates.set([])
    });
  }

  versionId() {
    return this.context()?.version?.id;
  }

  loadDocuments() {
    const versionId = this.versionId();
    if (!versionId) return;

    this.knowledgeLoading.set(true);
    this.uploadError.set('');

    this.api.getDocuments(versionId).subscribe({
      next: documents => {
        this.documents.set(documents);
        this.knowledgeLoading.set(false);
      },
      error: err => {
        this.uploadError.set(err.error?.detail || 'Could not load documents');
        this.knowledgeLoading.set(false);
      }
    });
  }

  onKnowledgeFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    const versionId = this.versionId();

    this.uploadError.set('');
    this.selectedFileName = file?.name || '';

    if (!file || !versionId) return;

    this.uploadLoading.set(true);
    const reader = new FileReader();

    reader.onload = () => {
      this.api.uploadDocument(versionId, {
        filename: file.name,
        content_type: file.type || 'text/plain',
        content: String(reader.result || '')
      }).subscribe({
        next: () => {
          input.value = '';
          this.selectedFileName = '';
          this.uploadLoading.set(false);
          this.loadDocuments();
          this.message.set('Document uploaded');
        },
        error: err => {
          this.uploadError.set(err.error?.detail || 'Upload failed');
          this.uploadLoading.set(false);
        }
      });
    };

    reader.onerror = () => {
      this.uploadError.set('Could not read file');
      this.uploadLoading.set(false);
    };

    reader.readAsText(file);
  }

  deleteDocument(document: any) {
    if (!confirm(`Delete document "${document.filename}"?`)) return;

    this.api.deleteDocument(document.id).subscribe({
      next: () => {
        this.documents.update(documents => documents.filter(item => item.id !== document.id));
        this.message.set('Document deleted');
      },
      error: err => this.uploadError.set(err.error?.detail || 'Could not delete document')
    });
  }

  selectNode(node: FlowNode) {
    this.selectedNode.set({ ...node, config: { ...(node.config || {}) } });
    this.editorOpen.set(true);
    this.inspectorCollapsed.set(false);
    this.inspectorTab.set('settings');
    this.message.set('');
    setTimeout(() => this.focusNode(node), 0);
  }

  closeEditor() {
    this.inspectorTab.set('settings');
  }

  toggleSidebar() {
    this.sidebarCollapsed.update(value => !value);
    setTimeout(() => this.fitToScreen(), 80);
  }

  toggleInspector() {
    this.inspectorCollapsed.update(value => !value);
    setTimeout(() => this.fitToScreen(), 80);
  }

  nodeText(node: FlowNode | null) {
    if (!node) return '';
    return node.config?.['text'] || node.config?.['prompt'] || node.config?.['message'] || '';
  }

  nodeConfigValue(node: FlowNode | null, key: string) {
    return node?.config?.[key] || '';
  }

  nodeButtons(node: FlowNode | null) {
    const buttons = node?.config?.['buttons'] || [];
    if (Array.isArray(buttons)) return buttons;
    return this.parseButtonLabels(String(buttons));
  }

  setNodeText(value: string) {
    const node = this.selectedNode();
    if (!node) return;

    const key = ['question', 'collect_name', 'collect_email', 'collect_phone'].includes(node.type)
      ? 'prompt'
      : ['handoff', 'end', 'action', 'set_variable', 'api_request'].includes(node.type)
        ? 'message'
        : 'text';
    this.selectedNode.set({
      ...node,
      config: {
        ...(node.config || {}),
        [key]: value
      }
    });
  }

  buttonText(node: FlowNode | null) {
    return this.nodeButtons(node).join('\n');
  }

  setButtonText(value: string) {
    const node = this.selectedNode();
    if (!node) return;
    this.selectedNode.set({
      ...node,
      config: {
        ...(node.config || {}),
        buttons: this.parseButtonLabels(value)
      }
    });
  }

  private parseButtonLabels(value: string) {
    const seen = new Set<string>();
    return value
      .split(/[\n,]+/)
      .map(item => item.trim())
      .filter(Boolean)
      .filter(item => {
        const key = item.toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
  }

  updateNodeField(field: 'label' | 'type', value: string) {
    const node = this.selectedNode();
    if (!node) return;
    this.selectedNode.set({ ...node, [field]: value });
  }

  updateNodeConfig(field: string, value: any) {
    const node = this.selectedNode();
    if (!node) return;
    this.selectedNode.set({
      ...node,
      config: {
        ...(node.config || {}),
        [field]: value
      }
    });
  }

  updateNodeJsonConfig(field: string, value: string) {
    try {
      this.updateNodeConfig(field, value.trim() ? JSON.parse(value) : {});
    } catch {
      this.updateNodeConfig(field, value);
    }
  }

  jsonConfigValue(node: FlowNode | null, field: string) {
    const value = node?.config?.[field];
    if (typeof value === 'string') return value;
    return JSON.stringify(value || {}, null, 2);
  }

  blockMeta(type: string) {
    return this.blockTypes.find(item => item.value === type) || this.blockTypes[0];
  }

  blockTypeClass(type: string) {
    return `type-${type.replace(/_/g, '-')}`;
  }

  blockTypesByCategory(category: string) {
    return this.blockTypes.filter(item => item.category === category);
  }

  selectBlockType(type: string) {
    this.nodeType = type;
    this.addNode();
  }

  saveNode() {
    const node = this.selectedNode();
    if (!node) return;

    this.saving.set(true);
    this.error.set('');
    this.message.set('');

    this.api.updateFlowNode(node.id, {
      label: node.label,
      config: node.config,
      position_x: node.position_x,
      position_y: node.position_y
    }).subscribe({
      next: saved => {
        this.nodes.update(nodes => nodes.map(item => item.id === saved.id ? saved : item));
        this.selectedNode.set(saved);
        if (saved.type === 'buttons') {
          const labels = new Set(this.nodeButtons(saved));
          this.outgoing(saved)
            .filter(transition => !labels.has(transition.label || ''))
            .forEach(transition => this.deleteTransitionNow(transition));
        }
        this.message.set('Block saved');
        this.saving.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not save block');
        this.saving.set(false);
      }
    });
  }

  zoomPercent() {
    return `${Math.round(this.zoom() * 100)}%`;
  }

  stageTransform() {
    return `scale(${this.zoom()})`;
  }

  zoomIn() {
    this.setZoom(this.zoom() + 0.05);
  }

  zoomOut() {
    this.setZoom(this.zoom() - 0.05);
  }

  private setZoom(value: number) {
    const viewport = this.canvasViewport?.nativeElement;
    const previousZoom = this.zoom();
    const nextZoom = Math.min(1.5, Math.max(0.5, Math.round(value * 100) / 100));
    if (!viewport || previousZoom === nextZoom) {
      this.zoom.set(nextZoom);
      return;
    }

    const centerX = (viewport.scrollLeft + viewport.clientWidth / 2) / previousZoom;
    const centerY = (viewport.scrollTop + viewport.clientHeight / 2) / previousZoom;
    this.zoom.set(nextZoom);
    requestAnimationFrame(() => {
      viewport.scrollLeft = Math.max(0, centerX * nextZoom - viewport.clientWidth / 2);
      viewport.scrollTop = Math.max(0, centerY * nextZoom - viewport.clientHeight / 2);
    });
  }

  private nodeBounds() {
    const nodes = this.nodes();
    if (!nodes.length) return { minX: 0, minY: 0, width: 900, height: 520 };
    const minX = Math.min(...nodes.map(node => node.position_x));
    const minY = Math.min(...nodes.map(node => node.position_y));
    const maxX = Math.max(...nodes.map(node => node.position_x + 260));
    const maxY = Math.max(...nodes.map(node => node.position_y + 150));
    return {
      minX,
      minY,
      width: Math.max(maxX - minX, 260),
      height: Math.max(maxY - minY, 150)
    };
  }

  fitToScreen() {
    if (!this.viewReady || !this.canvasViewport?.nativeElement || !this.nodes().length) return;
    const viewport = this.canvasViewport.nativeElement;
    const bounds = this.nodeBounds();
    const padding = 110;
    const nextZoom = Math.min(
      1,
      Math.max(
        0.6,
        Math.min(
          (viewport.clientWidth - padding) / bounds.width,
          (viewport.clientHeight - padding) / bounds.height
        )
      )
    );
    this.zoom.set(Math.round(nextZoom * 100) / 100);
    requestAnimationFrame(() => {
      viewport.scrollLeft = Math.max(0, ((bounds.minX + bounds.width / 2) * this.zoom()) - viewport.clientWidth / 2);
      viewport.scrollTop = Math.max(0, ((bounds.minY + bounds.height / 2) * this.zoom()) - viewport.clientHeight / 2);
    });
  }

  focusSelectedNode() {
    const node = this.selectedNode();
    if (node) this.focusNode(node);
  }

  private focusNode(node: FlowNode) {
    if (!this.canvasViewport?.nativeElement) return;
    const viewport = this.canvasViewport.nativeElement;
    const zoom = this.zoom();
    viewport.scrollTo({
      left: Math.max(0, (node.position_x + 130) * zoom - viewport.clientWidth / 2),
      top: Math.max(0, (node.position_y + 75) * zoom - viewport.clientHeight / 2),
      behavior: 'smooth'
    });
  }

  addNode() {
    const flowId = this.context()?.flow?.id;
    if (!flowId) return;

    const previousNode = this.selectedNode();
    const index = this.nodes().length + 1;
    const type = this.nodeType;
    const config = type === 'question'
      ? { prompt: 'What should we ask?', field: `answer_${index}` }
      : type === 'buttons'
        ? { text: 'Choose an option', buttons: ['Yes', 'No'], field: `choice_${index}` }
      : type === 'rag_answer'
        ? {
            prompt: 'Answer clearly and stay helpful.',
            use_knowledge_base: true,
            answer_only_from_documents: true,
            show_sources: true,
            response_length: 'medium',
            fallback: 'I could not find this in the uploaded documents.',
            continue_rag: true
          }
        : type === 'condition'
          ? { field: '__last_input', operator: 'equals', value: 'Yes', message: 'Checking condition' }
          : type === 'set_variable'
            ? { action_type: 'set_variable', field: 'status', value: 'qualified', message: 'Saved.' }
          : type === 'collect_name'
            ? { prompt: 'What is your name?', field: 'user_name' }
          : type === 'collect_email'
            ? { prompt: 'What is your email address?', field: 'user_email', invalid_message: 'Please enter a valid email address.' }
          : type === 'collect_phone'
            ? { prompt: 'What phone number can we use?', field: 'user_phone', invalid_message: 'Please enter a valid phone number.' }
          : type === 'api_request'
            ? { method: 'POST', url: '', headers: {}, body: {}, response_field: 'api_response', success_message: 'Request completed.', error_message: 'The request failed.' }
          : type === 'handoff'
            ? { message: 'A teammate will review this conversation.', department: 'Support', email_field: 'user_email', phone_field: 'user_phone', collect_email_if_missing: true }
          : type === 'end'
            ? { message: 'Thanks. The conversation is now closed.' }
          : { text: 'New message' };

    this.api.createFlowNode(flowId, {
      type,
      label: `${this.blockMeta(type).label} ${index}`,
      config,
      position_x: Math.max((previousNode?.position_x || 90) + 290, 60),
      position_y: previousNode?.position_y || 90 + index * 130
    }).subscribe({
      next: node => {
        this.nodes.update(nodes => [...nodes, node]);
        this.selectedNode.set(node);
        this.inspectorTab.set('settings');
        setTimeout(() => this.focusNode(node), 80);
        if (previousNode && previousNode.type !== 'buttons' && previousNode.type !== 'condition' && !this.isTerminalNode(previousNode)) {
          this.createOrUpdateTransition(previousNode.node_key, node.node_key, 'next');
        }
      },
      error: err => this.error.set(err.error?.detail || 'Could not create block')
    });
  }

  requestDeleteNode(node: FlowNode) {
    if (node.node_key === 'start') {
      this.error.set('The start block cannot be deleted');
      return;
    }

    this.deleteConfirm.set({
      type: 'node',
      item: node,
      title: 'Delete block',
      message: `Delete "${node.label}" and its connectors?`
    });
  }

  confirmDelete() {
    const pending = this.deleteConfirm();
    if (!pending) return;

    if (pending.type === 'transition') {
      this.deleteTransitionNow(pending.item as FlowTransition);
      this.deleteConfirm.set(null);
      return;
    }

    this.deleteNodeNow(pending.item as FlowNode);
    this.deleteConfirm.set(null);
  }

  cancelDelete() {
    this.deleteConfirm.set(null);
  }

  private deleteNodeNow(node: FlowNode) {

    this.api.deleteFlowNode(node.id).subscribe({
      next: () => {
        this.nodes.update(nodes => nodes.filter(item => item.id !== node.id));
        this.transitions.update(transitions => transitions.filter(
          transition => transition.source_node_key !== node.node_key && transition.target_node_key !== node.node_key
        ));
        this.selectedNode.set(null);
      },
      error: err => this.error.set(err.error?.detail || 'Could not delete block')
    });
  }

  private createOrUpdateTransition(sourceKey: string, targetKey: string, label: string) {
    const flowId = this.context()?.flow?.id;
    if (!flowId || !sourceKey || !targetKey) return;

    const existing = this.transitions().find(transition =>
      transition.source_node_key === sourceKey && (transition.label || 'next') === label
    );

    if (existing) {
      this.api.updateFlowTransition(existing.id, {
        target_node_key: targetKey,
        label
      }).subscribe({
        next: transition => {
          this.transitions.update(transitions => transitions.map(item => item.id === transition.id ? transition : item));
          this.message.set('Next block updated');
        },
        error: err => this.error.set(err.error?.detail || 'Could not update next block')
      });
      return;
    }

    this.api.createFlowTransition(flowId, {
      source_node_key: sourceKey,
      target_node_key: targetKey,
      label
    }).subscribe({
      next: transition => {
        this.transitions.update(transitions => [...transitions, transition]);
        this.message.set('Next block connected');
      },
      error: err => this.error.set(err.error?.detail || 'Could not connect next block')
    });
  }

  deleteTransition(transition: FlowTransition) {
    this.deleteConfirm.set({
      type: 'transition',
      item: transition,
      title: 'Delete connector',
      message: `Remove the path "${transition.label || 'next'}" to "${this.nodeLabel(transition.target_node_key)}"?`
    });
  }

  private deleteTransitionNow(transition: FlowTransition) {
    this.api.deleteFlowTransition(transition.id).subscribe({
      next: () => this.transitions.update(items => items.filter(item => item.id !== transition.id)),
      error: err => this.error.set(err.error?.detail || 'Could not delete connector')
    });
  }

  outgoing(node: FlowNode) {
    return this.transitions().filter(transition => transition.source_node_key === node.node_key);
  }

  canvasWidth() {
    const maxX = Math.max(...this.nodes().map(node => node.position_x), 1200);
    return Math.max(1600, maxX + 760);
  }

  canvasHeight() {
    const maxY = Math.max(...this.nodes().map(node => node.position_y), 760);
    return Math.max(1000, maxY + 520);
  }

  scaledCanvasWidth() {
    return this.canvasWidth() * this.zoom();
  }

  scaledCanvasHeight() {
    return this.canvasHeight() * this.zoom();
  }

  nodeStyle(node: FlowNode) {
    return {
      left: `${node.position_x}px`,
      top: `${node.position_y}px`
    };
  }

  transitionPath(transition: FlowTransition) {
    const source = this.nodes().find(node => node.node_key === transition.source_node_key);
    const target = this.nodes().find(node => node.node_key === transition.target_node_key);
    if (!source || !target) return '';

    const startX = source.position_x + 210;
    const startY = source.position_y + 52;
    const endX = target.position_x;
    const endY = target.position_y + 52;
    const curve = Math.max(Math.abs(endX - startX) / 2, 80);
    return `M ${startX} ${startY} C ${startX + curve} ${startY}, ${endX - curve} ${endY}, ${endX} ${endY}`;
  }

  transitionClass(transition: FlowTransition) {
    const label = (transition.label || 'next').toLowerCase();
    if (['true', 'yes', 'matched', 'helpful'].includes(label)) return 'line-positive';
    if (['false', 'no', 'else', 'not helpful'].includes(label)) return 'line-negative';
    if (label === 'next') return 'line-next';
    return 'line-choice';
  }

  startDrag(event: PointerEvent, node: FlowNode) {
    if ((event.target as HTMLElement).closest('button, input, select, textarea')) return;
    event.preventDefault();
    event.stopPropagation();
    this.selectedNode.set({ ...node, config: { ...(node.config || {}) } });
    this.dragging.set(node.id);
    this.dragState = {
      nodeId: node.id,
      startPointerX: event.clientX,
      startPointerY: event.clientY,
      startNodeX: node.position_x,
      startNodeY: node.position_y
    };
  }

  @HostListener('document:pointermove', ['$event'])
  onPointerMove(event: PointerEvent) {
    if (this.panState && !this.dragState) {
      const viewport = this.canvasViewport?.nativeElement;
      if (!viewport) return;
      viewport.scrollLeft = this.panState.startScrollLeft - (event.clientX - this.panState.startPointerX);
      viewport.scrollTop = this.panState.startScrollTop - (event.clientY - this.panState.startPointerY);
      return;
    }

    if (!this.dragState) return;
    const nextX = Math.max(32, this.dragState.startNodeX + (event.clientX - this.dragState.startPointerX) / this.zoom());
    const nextY = Math.max(32, this.dragState.startNodeY + (event.clientY - this.dragState.startPointerY) / this.zoom());

    this.nodes.update(nodes => nodes.map(node =>
      node.id === this.dragState?.nodeId
        ? { ...node, position_x: nextX, position_y: nextY }
        : node
    ));
    if (this.selectedNode()?.id === this.dragState.nodeId) {
      this.selectedNode.update(node => node ? { ...node, position_x: nextX, position_y: nextY } : node);
    }
  }

  @HostListener('document:pointerup')
  onPointerUp() {
    if (this.panState && !this.dragState) {
      this.panState = null;
      return;
    }

    if (!this.dragState) return;
    const node = this.nodes().find(item => item.id === this.dragState?.nodeId);
    this.dragState = null;
    this.dragging.set(undefined);
    if (!node) return;

    this.api.updateFlowNode(node.id, {
      label: node.label,
      config: node.config,
      position_x: Math.round(node.position_x),
      position_y: Math.round(node.position_y)
    }).subscribe({
      next: saved => {
        this.nodes.update(nodes => nodes.map(item => item.id === saved.id ? saved : item));
        if (this.selectedNode()?.id === saved.id) this.selectedNode.set(saved);
      },
      error: err => this.error.set(err.error?.detail || 'Could not save block position')
    });
  }

  startPan(event: PointerEvent) {
    if ((event.target as HTMLElement).closest('.flow-block, button, input, select, textarea')) return;
    const viewport = this.canvasViewport?.nativeElement;
    if (!viewport) return;
    this.panState = {
      startPointerX: event.clientX,
      startPointerY: event.clientY,
      startScrollLeft: viewport.scrollLeft,
      startScrollTop: viewport.scrollTop
    };
  }

  nextBlockKey(node: FlowNode | null) {
    if (!node || node.type === 'buttons' || node.type === 'condition' || this.isTerminalNode(node)) return '';
    return this.outgoing(node)[0]?.target_node_key || '';
  }

  isTerminalNode(node: FlowNode | null) {
    if (!node) return false;
    if (node.type === 'end' || node.type === 'handoff') return true;
    return node.type === 'action' && ['handoff', 'end'].includes(node.config?.['action_type']);
  }

  setNextBlock(targetKey: string) {
    const node = this.selectedNode();
    if (!node) return;

    const existing = this.outgoing(node)[0];
    if (!targetKey) {
      if (existing) this.deleteTransition(existing);
      return;
    }

    this.createOrUpdateTransition(node.node_key, targetKey, existing?.label || 'next');
  }

  buttonTarget(buttonLabel: string) {
    const node = this.selectedNode();
    if (!node) return '';

    return this.transitions().find(transition =>
      transition.source_node_key === node.node_key && transition.label === buttonLabel
    )?.target_node_key || '';
  }

  setButtonTarget(buttonLabel: string, targetKey: string) {
    const node = this.selectedNode();
    if (!node) return;

    const existing = this.transitions().find(transition =>
      transition.source_node_key === node.node_key && transition.label === buttonLabel
    );

    if (!targetKey) {
      if (existing) this.deleteTransition(existing);
      return;
    }

    this.createOrUpdateTransition(node.node_key, targetKey, buttonLabel);
  }

  conditionTarget(label: 'true' | 'false') {
    const node = this.selectedNode();
    if (!node) return '';

    return this.transitions().find(transition =>
      transition.source_node_key === node.node_key && (transition.label || '').toLowerCase() === label
    )?.target_node_key || '';
  }

  setConditionTarget(label: 'true' | 'false', targetKey: string) {
    const node = this.selectedNode();
    if (!node) return;

    const existing = this.transitions().find(transition =>
      transition.source_node_key === node.node_key && (transition.label || '').toLowerCase() === label
    );

    if (!targetKey) {
      if (existing) this.deleteTransition(existing);
      return;
    }

    this.createOrUpdateTransition(node.node_key, targetKey, label);
  }

  nodeLabel(nodeKey: string) {
    return this.nodes().find(node => node.node_key === nodeKey)?.label || nodeKey;
  }

  helperText(node: FlowNode | null) {
    if (!node) return '';
    const helpers: Record<string, string> = {
      message: 'Shows a message, then moves to the next step.',
      question: 'Asks the visitor for information and saves the answer.',
      buttons: 'Shows clear choices. Each button needs a next step.',
      condition: 'Routes the conversation based on a saved answer.',
      rag_answer: 'Uses AI and optional uploaded documents to answer the visitor.',
      action: 'Updates saved conversation data or hands off the conversation.',
      collect_name: 'Asks for the visitor name and saves it to a variable.',
      collect_email: 'Asks for an email address and validates the format before continuing.',
      collect_phone: 'Asks for a phone number and validates a basic phone format.',
      set_variable: 'Sets a variable value without asking the visitor.',
      api_request: 'Calls an external webhook only when the live conversation reaches this block.',
      handoff: 'Stops the flow and marks the conversation for human follow-up.',
      end: 'Ends the conversation.'
    };
    return helpers[node.type] || 'Configure how this block behaves in the conversation.';
  }

  validateCurrentFlow() {
    const versionId = this.versionId();
    this.validationErrors.set([]);
    if (!versionId) {
      this.validationErrors.set(['No draft version is available for this chatbot.']);
      return;
    }

    this.api.validateFlow(versionId).subscribe({
      next: result => {
        const errors = result?.errors || [];
        this.validationErrors.set(errors);
        if (!errors.length) this.message.set('Flow validation passed');
      },
      error: err => this.validationErrors.set(this.extractValidationErrors(err, 'Could not validate this flow.'))
    });
  }

  validationForNode(node: FlowNode) {
    const label = node.label || node.node_key;
    return this.validationErrors().filter(item => item.includes(`'${label}'`) || item.includes(`"${label}"`) || item.includes(label));
  }

  hasNodeWarning(node: FlowNode) {
    return this.validationForNode(node).length > 0 || this.localNodeWarnings(node).length > 0;
  }

  localNodeWarnings(node: FlowNode) {
    const warnings: string[] = [];
    const outgoing = this.outgoing(node);
    if (!this.isTerminalNode(node) && !['buttons', 'condition', 'rag_answer'].includes(node.type) && !outgoing.length) {
      warnings.push('Missing next step');
    }
    if (node.type === 'buttons') {
      for (const button of this.nodeButtons(node)) {
        if (!outgoing.some(transition => transition.label === button)) warnings.push(`Missing path for ${button}`);
      }
    }
    if (node.type === 'condition') {
      const labels = outgoing.map(item => (item.label || '').toLowerCase());
      if (!labels.includes('true')) warnings.push('Missing true path');
      if (!labels.includes('false')) warnings.push('Missing false path');
    }
    if (node.type === 'rag_answer' && !String(node.config?.['fallback'] || '').trim()) warnings.push('Missing fallback');
    if (node.type === 'collect_email' && !String(node.config?.['field'] || '').trim()) warnings.push('Missing email variable');
    if (node.type === 'api_request' && !String(node.config?.['url'] || '').trim()) warnings.push('Missing URL');
    return warnings;
  }

  applyTemplate() {
    const flowId = this.context()?.flow?.id;
    if (!flowId || !this.selectedTemplate) return;
    if (!confirm('Replace the current draft flow with this template? Existing blocks and connectors will be removed.')) return;

    this.applyingTemplate.set(true);
    this.error.set('');
    this.api.applyFlowTemplate(flowId, this.selectedTemplate).subscribe({
      next: flow => {
        this.context.update(context => context ? { ...context, flow } : context);
        this.nodes.set([...flow.nodes].sort((a: FlowNode, b: FlowNode) => a.position_y - b.position_y || a.position_x - b.position_x));
        this.transitions.set(flow.transitions || []);
        this.selectedNode.set(null);
        this.validationErrors.set([]);
        this.message.set('Template applied');
        this.applyingTemplate.set(false);
        setTimeout(() => this.fitToScreen(), 0);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not apply template');
        this.applyingTemplate.set(false);
      }
    });
  }

  goTestFlow() {
    const versionId = this.versionId();
    this.validationErrors.set([]);
    if (!versionId) {
      this.validationErrors.set(['No draft version is available for this chatbot.']);
      return;
    }

    this.api.validateFlow(versionId).subscribe({
      next: result => {
        const errors = result?.errors || [];
        this.validationErrors.set(errors);
        if (!errors.length) {
          this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots', this.chatbotId, 'flow', 'test']);
        }
      },
      error: err => this.validationErrors.set(this.extractValidationErrors(err, 'Could not validate this flow.'))
    });
  }

  startPreview() {
    this.validationErrors.set([]);
    this.previewSessionId.set(undefined);
    this.previewMessages.set([]);
    this.previewLoading.set(true);
    this.previewError.set('');

    this.api.startChatSession({
      chatbot_id: this.chatbotId,
      version_id: this.versionId()
    }).subscribe({
      next: session => {
        this.previewSessionId.set(session.session_id);
        this.previewLoading.set(false);
        this.sendPreview('__start__');
      },
      error: err => {
        this.previewError.set(this.friendlyError(err));
        this.previewLoading.set(false);
      }
    });
  }

  sendPreview(option?: string) {
    const text = option || this.previewInput.trim();
    if (!text) return;

    if (text !== '__start__') {
      this.previewMessages.update(messages => [...messages, { role: 'user', text }]);
    }
    this.previewInput = '';
    this.previewLoading.set(true);
    this.previewError.set('');

    this.api.chat({
      chatbot_id: this.chatbotId,
      version_id: this.context()?.version?.id,
      session_id: this.previewSessionId(),
      message: text === '__start__' ? '' : text,
    }).subscribe({
      next: result => {
        this.previewSessionId.set(result.session_id);
        const botMessages = this.toBotMessages(result);
        this.previewMessages.update(messages => [...messages, ...botMessages]);
        this.previewLoading.set(false);
      },
      error: err => {
        this.previewError.set(this.friendlyError(err));
        this.previewLoading.set(false);
      }
    });
  }

  private toBotMessages(result: any) {
    const mode = result.mode_used || 'flow';
    const retrievalMode = result.retrieval_mode || '';
    const sources = result.sources || [];
    if (Array.isArray(result.messages) && result.messages.length > 0) {
      return result.messages.map((item: any) => ({
        role: 'bot' as const,
        text: item.text || '',
        options: item.options || [],
        mode,
        retrievalMode,
        sources
      }));
    }

    return [{
      role: 'bot' as const,
      text: result.response || '',
      options: result.options || [],
      mode,
      retrievalMode,
      sources
    }];
  }

  private extractValidationErrors(err: any, fallback: string) {
    const detail = err?.error?.detail;
    if (Array.isArray(detail?.errors)) return detail.errors;
    if (Array.isArray(detail)) return detail.map((item: any) => item?.msg || String(item));
    if (typeof detail === 'string') return [detail];
    return [fallback];
  }

  private friendlyError(err: any) {
    const detail = err?.error?.detail || err?.message || '';
    if (typeof detail === 'object' && detail?.message) return detail.message;
    const text = String(detail || '');
    if (text.includes('LLM service') || text.includes('OpenAI') || text.includes('Azure')) {
      return 'The AI service could not answer right now. Check the AI configuration or try again.';
    }
    if (text.includes('knowledge') || text.includes('embedding') || text.includes('chunk')) {
      return 'The knowledge base could not be used for this answer. Check document processing status.';
    }
    if (text.includes('session') || text.includes('database') || text.includes('connection')) {
      return 'The test session could not be saved. Check the backend database connection.';
    }
    return text || 'Preview failed.';
  }

  private collectVariableRows() {
    const rows = new Map<string, any>();
    const upsert = (name: string, node: FlowNode, type = 'text') => {
      const clean = String(name || '').trim();
      if (!clean || clean.startsWith('__')) return;
      rows.set(clean, {
        name: clean,
        source: node.label || node.node_key,
        type,
        updated: `Created from ${this.blockMeta(node.type).label}`
      });
    };

    for (const node of this.nodes()) {
      const config = node.config || {};
      if (['question', 'buttons', 'collect_name', 'collect_email', 'collect_phone', 'set_variable'].includes(node.type)) {
        const type = node.type === 'collect_email' ? 'email' : node.type === 'collect_phone' ? 'phone' : 'text';
        upsert(config['field'], node, type);
      }
      if (node.type === 'api_request') {
        upsert(config['response_field'], node, 'object');
      }
      if (node.type === 'handoff') {
        upsert(config['email_field'], node, 'email');
        upsert(config['phone_field'], node, 'phone');
      }
      if (node.type === 'condition') {
        upsert(config['field'], node, 'condition input');
      }
    }

    return Array.from(rows.values()).sort((a, b) => a.name.localeCompare(b.name));
  }

  goBack() {
    this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots']);
  }
}
