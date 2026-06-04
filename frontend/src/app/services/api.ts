import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { apiBaseUrl } from '../config/app-config';

@Injectable({
  providedIn: 'root'
})
export class ApiService {

  baseUrl = apiBaseUrl();

  constructor(private http: HttpClient) {}

  getProjects(search = '') {
    const params: any = {};
    if (search.trim()) params.search = search.trim();
    return this.http.get<any[]>(`${this.baseUrl}/projects`, { params });
  }

  getProject(projectId: number) {
    return this.http.get<any>(`${this.baseUrl}/projects/${projectId}`);
  }

  createProject(data: any) {
    return this.http.post(`${this.baseUrl}/projects`, data);
  }

  updateProject(projectId: number, data: any) {
    return this.http.put(`${this.baseUrl}/projects/${projectId}`, data);
  }

  deleteProject(projectId: number) {
    return this.http.delete(`${this.baseUrl}/projects/${projectId}`);
  }

  // ===== CHATBOTS =====

  getChatbotsByProject(projectId: number) {
    return this.http.get<any[]>(
      `${this.baseUrl}/projects/${projectId}/chatbots`
    );
  }

  createChatbot(data: any) {
    return this.http.post(
      `${this.baseUrl}/chatbots`,
      data
    );
  }

  getChatbot(chatbotId: number) {
    return this.http.get<any>(`${this.baseUrl}/chatbots/${chatbotId}`);
  }

  updateChatbot(chatbotId: number, data: any) {
    return this.http.put<any>(`${this.baseUrl}/chatbots/${chatbotId}`, data);
  }

  updateChatbotStatus(chatbotId: number, isActive: boolean) {
    return this.http.put<any>(`${this.baseUrl}/chatbots/${chatbotId}/status`, {
      is_active: isActive
    });
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
    return this.http.delete(`${this.baseUrl}/chatbots/${chatbotId}`);
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

  getFlow(versionId: number) {
    return this.http.get<any>(`${this.baseUrl}/versions/${versionId}/flow`);
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

}
