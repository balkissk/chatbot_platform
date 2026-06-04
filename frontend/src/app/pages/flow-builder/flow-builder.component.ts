import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, HostListener, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
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
export class FlowBuilderComponent implements OnInit {
  projectId!: number;
  chatbotId!: number;

  context = signal<any | null>(null);
  nodes = signal<FlowNode[]>([]);
  transitions = signal<FlowTransition[]>([]);
  selectedNode = signal<FlowNode | null>(null);
  editorOpen = signal(false);
  sidebarCollapsed = signal(false);
  deleteConfirm = signal<{ type: 'node' | 'transition'; item: FlowNode | FlowTransition; title: string; message: string } | null>(null);
  loading = signal(false);
  saving = signal(false);
  error = signal('');
  message = signal('');

  nodeType = 'message';
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

  documents = signal<any[]>([]);
  knowledgeLoading = signal(false);
  uploadLoading = signal(false);
  uploadError = signal('');
  selectedFileName = '';

  previewInput = '';
  previewMessages = signal<{ role: 'user' | 'bot'; text: string; options?: string[] }[]>([]);
  previewSessionId = signal<number | undefined>(undefined);
  previewLoading = signal(false);
  previewError = signal('');

  dragging = signal<number | undefined>(undefined);
  private dragState: {
    nodeId: number;
    startPointerX: number;
    startPointerY: number;
    startNodeX: number;
    startNodeY: number;
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

  loadBuilder() {
    this.loading.set(true);
    this.error.set('');

    this.api.getChatbotBuilder(this.chatbotId).subscribe({
      next: context => {
        this.context.set(context);
        this.nodes.set([...context.flow.nodes].sort((a, b) => a.position_y - b.position_y || a.position_x - b.position_x));
        this.transitions.set(context.flow.transitions || []);
        this.selectedNode.set(this.nodes()[0] || null);
        this.loading.set(false);
        this.loadDocuments();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load flow');
        this.loading.set(false);
      }
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
    this.message.set('');
  }

  closeEditor() {
    this.editorOpen.set(false);
  }

  toggleSidebar() {
    this.sidebarCollapsed.update(value => !value);
  }

  nodeText(node: FlowNode | null) {
    if (!node) return '';
    return node.config?.['text'] || node.config?.['prompt'] || node.config?.['message'] || '';
  }

  nodeConfigValue(node: FlowNode | null, key: string) {
    return node?.config?.[key] || '';
  }

  nodeButtons(node: FlowNode | null) {
    return node?.config?.['buttons'] || [];
  }

  setNodeText(value: string) {
    const node = this.selectedNode();
    if (!node) return;

    const key = node.type === 'question' ? 'prompt' : node.type === 'handoff' || node.type === 'end' || node.type === 'action' ? 'message' : 'text';
    this.selectedNode.set({
      ...node,
      config: {
        ...(node.config || {}),
        [key]: value
      }
    });
  }

  buttonText(node: FlowNode | null) {
    return this.nodeButtons(node).join(', ');
  }

  setButtonText(value: string) {
    const node = this.selectedNode();
    if (!node) return;
    this.selectedNode.set({
      ...node,
      config: {
        ...(node.config || {}),
        buttons: value.split(',').map(item => item.trim()).filter(Boolean)
      }
    });
  }

  updateNodeField(field: 'label' | 'type', value: string) {
    const node = this.selectedNode();
    if (!node) return;
    this.selectedNode.set({ ...node, [field]: value });
  }

  updateNodeConfig(field: string, value: string) {
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
        ? { fallback: 'I could not find this in the knowledge base.' }
        : type === 'condition'
          ? { field: '__last_input', operator: 'equals', value: 'Yes', message: 'Checking condition' }
          : type === 'action'
            ? { action_type: 'set_variable', field: 'status', value: 'qualified', message: 'Saved.' }
          : { text: 'New message' };

    this.api.createFlowNode(flowId, {
      type,
      label: `${type.replace('_', ' ')} ${index}`,
      config,
      position_x: Math.max((previousNode?.position_x || 90) + 290, 60),
      position_y: previousNode?.position_y || 90 + index * 130
    }).subscribe({
      next: node => {
        this.nodes.update(nodes => [...nodes, node]);
        this.selectedNode.set(node);
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
        this.selectedNode.set(this.nodes()[0] || null);
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
    return maxX + 520;
  }

  canvasHeight() {
    const maxY = Math.max(...this.nodes().map(node => node.position_y), 760);
    return maxY + 320;
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

  startDrag(event: PointerEvent, node: FlowNode) {
    if ((event.target as HTMLElement).closest('button, input, select, textarea')) return;
    event.preventDefault();
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
    if (!this.dragState) return;
    const nextX = Math.max(32, this.dragState.startNodeX + event.clientX - this.dragState.startPointerX);
    const nextY = Math.max(32, this.dragState.startNodeY + event.clientY - this.dragState.startPointerY);

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

  startPreview() {
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
        this.previewError.set(err.error?.detail || 'Could not start preview');
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
        this.previewError.set(err.error?.detail || 'Preview failed. Publish a version first.');
        this.previewLoading.set(false);
      }
    });
  }

  private toBotMessages(result: any) {
    if (Array.isArray(result.messages) && result.messages.length > 0) {
      return result.messages.map((item: any) => ({
        role: 'bot' as const,
        text: item.text || '',
        options: item.options || []
      }));
    }

    return [{
      role: 'bot' as const,
      text: result.response || '',
      options: result.options || []
    }];
  }

  goBack() {
    this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots']);
  }
}
