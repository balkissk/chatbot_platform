import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class ApiService {

  baseUrl = 'http://127.0.0.1:8000';

  constructor(private http: HttpClient) {}

  getProjects() {
    return this.http.get(`${this.baseUrl}/projects`);
  }

  createProject(data: any) {
    return this.http.post(`${this.baseUrl}/projects`, data);
  }

  // ===== CHATBOTS =====

  getChatbotsByProject(projectId: number) {
    return this.http.get<any[]>(
      `http://localhost:8000/chatbots?project_id=${projectId}`
    );
  }

  createChatbot(data: any) {
    return this.http.post(
      `http://localhost:8000/chatbots`,
      data
    );
  }
  // ===== VERSIONS =====

  getVersionsByChatbot(chatbotId: number) {
    return this.http.get<any[]>(
      `http://localhost:8000/chatbots/${chatbotId}/versions`
    );
  }

  createVersion(data: any) {
    return this.http.post(
      `http://localhost:8000/versions`,
      data
    );
  }
  publishVersion(versionId: number) {
    return this.http.put(
      `http://localhost:8000/versions/${versionId}/publish`,
      {}
    );
  }

  archiveVersion(versionId: number) {
    return this.http.put(
      `http://localhost:8000/versions/${versionId}/archive`,
      {}
    );
  }

}
