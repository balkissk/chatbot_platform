import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, of, shareReplay, tap } from 'rxjs';
import { apiBaseUrl } from '../config/app-config';

@Injectable({
  providedIn: 'root'
})
export class ApiService {

  baseUrl = apiBaseUrl();
  private projectsCache = new Map<string, Observable<any[]>>();
  private projectCache = new Map<number, Observable<any>>();
  private projectChatbotsCache = new Map<number, Observable<any[]>>();
  private projectChatbotsValueCache = new Map<number, any[]>();

  constructor(private http: HttpClient) {}

  getProjects(search = '', force = false, limit = 50, offset = 0) {
    const params: any = {};
    if (search.trim()) params.search = search.trim();
    params.limit = limit;
    params.offset = offset;
    const key = `${search.trim()}|${limit}|${offset}`;
    if (force || !this.projectsCache.has(key)) {
      this.projectsCache.set(
        key,
        this.http.get<any[]>(`${this.baseUrl}/projects`, { params }).pipe(
          tap(projects => projects.forEach(project => {
            this.projectCache.set(project.id, of(project).pipe(shareReplay(1)));
          })),
          shareReplay(1)
        )
      );
    }
    return this.projectsCache.get(key)!;
  }

  getProject(projectId: number, force = false) {
    if (force || !this.projectCache.has(projectId)) {
      this.projectCache.set(
        projectId,
        this.http.get<any>(`${this.baseUrl}/projects/${projectId}`).pipe(shareReplay(1))
      );
    }
    return this.projectCache.get(projectId)!;
  }

  createProject(data: any) {
    return this.http.post(`${this.baseUrl}/projects`, data).pipe(
      tap(() => this.clearProjectCaches())
    );
  }

  updateProject(projectId: number, data: any) {
    return this.http.put(`${this.baseUrl}/projects/${projectId}`, data).pipe(
      tap((project: any) => {
        this.clearProjectCaches(projectId);
        this.projectCache.set(projectId, of(project).pipe(shareReplay(1)));
      })
    );
  }

  deleteProject(projectId: number) {
    return this.http.delete(`${this.baseUrl}/projects/${projectId}`).pipe(
      tap(() => this.clearProjectCaches(projectId))
    );
  }

  // ===== CHATBOTS =====

  getChatbotsByProject(projectId: number, force = false) {
    if (force || !this.projectChatbotsCache.has(projectId)) {
      this.projectChatbotsCache.set(
        projectId,
        this.http.get<any[]>(`${this.baseUrl}/projects/${projectId}/chatbots`).pipe(
          tap(chatbots => this.projectChatbotsValueCache.set(projectId, chatbots)),
          shareReplay(1)
        )
      );
    }
    return this.projectChatbotsCache.get(projectId)!;
  }

  getCachedChatbotsByProject(projectId: number) {
    return this.projectChatbotsValueCache.get(projectId);
  }

  createChatbot(data: any) {
    return this.http.post(
      `${this.baseUrl}/chatbots`,
      data
    ).pipe(tap(() => this.clearChatbotCaches(data.project_id)));
  }

  getChatbot(chatbotId: number) {
    return this.http.get<any>(`${this.baseUrl}/chatbots/${chatbotId}`);
  }

  getChatbotAnalytics(chatbotId: number) {
    return this.http.get<any>(`${this.baseUrl}/chatbots/${chatbotId}/analytics`);
  }

  getChatbotConversations(chatbotId: number, filters: any = {}) {
    const params: any = {};
    if (filters.search?.trim()) params.search = filters.search.trim();
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.channel) params.channel = filters.channel;
    if (filters.feedback) params.feedback = filters.feedback;
    if (filters.response_type) params.response_type = filters.response_type;
    if (filters.limit) params.limit = filters.limit;
    if (filters.offset) params.offset = filters.offset;
    return this.http.get<any[]>(`${this.baseUrl}/chatbots/${chatbotId}/conversations`, { params });
  }

  getChatbotConversation(chatbotId: number, sessionId: number, messageLimit = 200) {
    return this.http.get<any>(`${this.baseUrl}/chatbots/${chatbotId}/conversations/${sessionId}`, {
      params: { message_limit: messageLimit }
    });
  }

  getChatbotUnansweredQuestions(chatbotId: number) {
    return this.http.get<any[]>(`${this.baseUrl}/chatbots/${chatbotId}/conversations/unanswered`);
  }

  updateChatbot(chatbotId: number, data: any) {
    return this.http.put<any>(`${this.baseUrl}/chatbots/${chatbotId}`, data).pipe(
      tap(() => this.clearChatbotCaches())
    );
  }

  updateChatbotStatus(chatbotId: number, isActive: boolean) {
    return this.http.put<any>(`${this.baseUrl}/chatbots/${chatbotId}/status`, {
      is_active: isActive
    }).pipe(tap(() => this.clearChatbotCaches()));
  }

  regenerateChatbotApiKey(chatbotId: number) {
    return this.http.put<any>(`${this.baseUrl}/chatbots/${chatbotId}/api-key/regenerate`, {});
  }

  getChatbotRagSettings(chatbotId: number) {
    return this.http.get<any>(`${this.baseUrl}/chatbots/${chatbotId}/rag-settings`);
  }

  updateChatbotRagSettings(chatbotId: number, data: any) {
    return this.http.put<any>(`${this.baseUrl}/chatbots/${chatbotId}/rag-settings`, data);
  }

  deleteChatbot(chatbotId: number) {
    return this.http.delete(`${this.baseUrl}/chatbots/${chatbotId}`).pipe(
      tap(() => this.clearChatbotCaches())
    );
  }
  // ===== VERSIONS =====

  getVersionsByChatbot(chatbotId: number) {
    return this.http.get<any[]>(
      `${this.baseUrl}/chatbots/${chatbotId}/versions`
    );
  }

  createVersion(data: any) {
    return this.http.post(
      `${this.baseUrl}/versions`,
      data
    );
  }
  publishVersion(versionId: number) {
    return this.http.put(
      `${this.baseUrl}/versions/${versionId}/publish`,
      {}
    );
  }

  archiveVersion(versionId: number) {
    return this.http.put(
      `${this.baseUrl}/versions/${versionId}/archive`,
      {}
    );
  }

  duplicateVersion(versionId: number) {
    return this.http.post(
      `${this.baseUrl}/versions/${versionId}/duplicate`,
      {}
    );
  }

  deleteVersion(versionId: number) {
    return this.http.delete(`${this.baseUrl}/versions/${versionId}`);
  }

  getLlmConfig(versionId: number) {
    return this.http.get<any>(`${this.baseUrl}/llm-config/${versionId}`);
  }

  saveLlmConfig(data: any) {
    return this.http.post<any>(`${this.baseUrl}/llm-config`, data);
  }

  getFlow(versionId: number) {
    return this.http.get<any>(`${this.baseUrl}/versions/${versionId}/flow`);
  }

  validateFlow(versionId: number) {
    return this.http.get<any>(`${this.baseUrl}/versions/${versionId}/flow/validate`);
  }

  getFlowTemplates() {
    return this.http.get<any[]>(`${this.baseUrl}/flow-templates`);
  }

  applyFlowTemplate(flowId: number, templateKey: string) {
    return this.http.post<any>(`${this.baseUrl}/flows/${flowId}/template`, { template_key: templateKey });
  }

  getChatbotBuilder(chatbotId: number) {
    return this.http.get<any>(`${this.baseUrl}/chatbots/${chatbotId}/builder`);
  }

  updateFlowNode(nodeId: number, data: any) {
    return this.http.put<any>(`${this.baseUrl}/flow-nodes/${nodeId}`, data);
  }

  createFlowNode(flowId: number, data: any) {
    return this.http.post<any>(`${this.baseUrl}/flows/${flowId}/nodes`, data);
  }

  deleteFlowNode(nodeId: number) {
    return this.http.delete(`${this.baseUrl}/flow-nodes/${nodeId}`);
  }

  createFlowTransition(flowId: number, data: any) {
    return this.http.post<any>(`${this.baseUrl}/flows/${flowId}/transitions`, data);
  }

  updateFlowTransition(transitionId: number, data: any) {
    return this.http.put<any>(`${this.baseUrl}/flow-transitions/${transitionId}`, data);
  }

  deleteFlowTransition(transitionId: number) {
    return this.http.delete(`${this.baseUrl}/flow-transitions/${transitionId}`);
  }

  getDocuments(versionId: number) {
    return this.http.get<any[]>(
      `${this.baseUrl}/versions/${versionId}/documents`
    );
  }

  getDocument(documentId: number) {
    return this.http.get<any>(`${this.baseUrl}/documents/${documentId}`);
  }

  updateDocument(documentId: number, data: any) {
    return this.http.put<any>(`${this.baseUrl}/documents/${documentId}`, data);
  }

  getDocumentChunks(documentId: number) {
    return this.http.get<any[]>(`${this.baseUrl}/documents/${documentId}/chunks`);
  }

  reprocessDocumentEmbeddings(documentId: number) {
    return this.http.post<any>(`${this.baseUrl}/documents/${documentId}/embeddings/reprocess`, {});
  }

  reprocessDocumentChunks(documentId: number) {
    return this.http.post<any>(`${this.baseUrl}/documents/${documentId}/chunks/reprocess`, {});
  }

  uploadDocument(versionId: number, data: any) {
    return this.http.post(
      `${this.baseUrl}/versions/${versionId}/documents`,
      data
    );
  }

  testRagRetrieval(versionId: number, data: any) {
    return this.http.post<any>(`${this.baseUrl}/versions/${versionId}/rag-test`, data);
  }

  deleteDocument(documentId: number) {
    return this.http.delete(`${this.baseUrl}/documents/${documentId}`);
  }

  chat(data: any) {
    return this.http.post<any>(
      `${this.baseUrl}/chat`,
      data
    );
  }

  startChatSession(data: any) {
    return this.http.post<any>(
      `${this.baseUrl}/chat/sessions`,
      data
    );
  }

  getPublicChatbot(chatbotId: number) {
    return this.http.get<any>(`${this.baseUrl}/public/chatbots/${chatbotId}`);
  }

  publicChat(data: any) {
    return this.http.post<any>(`${this.baseUrl}/public/chat`, data);
  }

  submitPublicFeedback(data: any) {
    return this.http.post<any>(`${this.baseUrl}/public/chat/feedback`, data);
  }

  async publicChatStream(data: any, onEvent: (event: any) => void) {
    const response = await fetch(`${this.baseUrl}/public/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });

    if (!response.ok || !response.body) {
      let detail = 'Chat failed';
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch {}
      throw new Error(detail);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.trim()) continue;
        onEvent(JSON.parse(line));
      }
    }

    if (buffer.trim()) {
      onEvent(JSON.parse(buffer));
    }
  }

  startPublicChatSession(data: any) {
    return this.http.post<any>(`${this.baseUrl}/public/chat/sessions`, data);
  }

  getAdminAnalyticsOverview() {
    return this.http.get<any>(`${this.baseUrl}/admin/analytics/overview`);
  }

  getAdminSessions(chatbotId?: number) {
    const params: any = {};
    if (chatbotId) params.chatbot_id = chatbotId;
    return this.http.get<any[]>(`${this.baseUrl}/admin/analytics/sessions`, { params });
  }

  getAdminSession(sessionId: number) {
    return this.http.get<any>(`${this.baseUrl}/admin/analytics/sessions/${sessionId}`);
  }

  private clearProjectCaches(projectId?: number) {
    this.projectsCache.clear();
    if (projectId) {
      this.projectCache.delete(projectId);
      this.projectChatbotsCache.delete(projectId);
      this.projectChatbotsValueCache.delete(projectId);
    } else {
      this.projectCache.clear();
      this.projectChatbotsCache.clear();
      this.projectChatbotsValueCache.clear();
    }
  }

  private clearChatbotCaches(projectId?: number) {
    if (projectId) {
      this.projectChatbotsCache.delete(projectId);
      this.projectChatbotsValueCache.delete(projectId);
    } else {
      this.projectChatbotsCache.clear();
      this.projectChatbotsValueCache.clear();
    }
  }

}
