import { CommonModule } from '@angular/common';
import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { ApiService } from '../../services/api';
import { normalizeAssistantChannel, normalizeAssistantLanguage } from '../../shared/assistant-options';

@Component({
  selector: 'app-ai-generator',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './ai-generator.component.html',
  styleUrls: ['./ai-generator.component.css']
})
export class AiGeneratorComponent {
  projectId: number;
  chatbotId: number;

  form = {
    assistant_goal: '',
    business_context: '',
    knowledge_base_description: ''
  };

  generated = signal<any | null>(null);
  loading = signal(false);
  error = signal('');

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private api: ApiService
  ) {
    this.projectId = Number(this.route.snapshot.paramMap.get('projectId'));
    this.chatbotId = Number(this.route.snapshot.paramMap.get('chatbotId'));
  }

  canGenerate() {
    return Boolean(this.form.assistant_goal.trim() && this.form.business_context.trim() && !this.loading());
  }

  async generateAssistant() {
    if (!this.canGenerate()) return;

    this.loading.set(true);
    this.error.set('');

    try {
      const chatbot = await firstValueFrom(this.api.getChatbot(this.chatbotId));
      const generated = await firstValueFrom(this.api.generateAssistantWithAi({
        ...this.form,
        assistant_type: chatbot?.assistant_type || chatbot?.purpose || 'custom',
        language: normalizeAssistantLanguage(chatbot?.language || 'en')
      }));
      this.generated.set(generated);

      const updatePayload = {
        name: this.textValue(generated.assistant_name, chatbot?.name || 'AI Assistant'),
        description: this.textValue(generated.assistant_description, chatbot?.description || ''),
        language: normalizeAssistantLanguage(chatbot?.language || 'en'),
        type: this.textValue(chatbot?.type, 'builder'),
        purpose: this.textValue(chatbot?.purpose || chatbot?.assistant_type, 'custom'),
        mode: this.textValue(chatbot?.mode, 'builder'),
        channel: normalizeAssistantChannel(chatbot?.channel),
        build_method: 'ai',
        creation_mode: 'ai',
        template_key: null
      };
      console.log('Update chatbot payload:', updatePayload);

      await firstValueFrom(this.api.updateChatbot(this.chatbotId, updatePayload));

      const context = await firstValueFrom(this.api.getChatbotBuilder(this.chatbotId));
      await firstValueFrom(this.api.applyGeneratedFlow(context.flow.id, {
        name: generated.assistant_name,
        nodes: generated.initial_flow_structure.nodes || [],
        transitions: generated.initial_flow_structure.transitions || []
      }));

      this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots', this.chatbotId, 'flow'], {
        queryParams: { generated: 'ai' }
      });
    } catch (err: any) {
      this.error.set(this.errorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  private textValue(value: any, fallback = '') {
    if (typeof value === 'string') return value.trim() || fallback;
    if (value === null || value === undefined) return fallback;
    return String(value).trim() || fallback;
  }

  private errorMessage(error: any) {
    const detail = error?.response?.data?.detail ?? error?.error?.detail ?? error?.message;
    if (!detail) return 'Could not generate the assistant.';
    if (typeof detail === 'string') return detail;
    try {
      return JSON.stringify(detail);
    } catch {
      return 'Could not generate the assistant.';
    }
  }

  goBack() {
    this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots']);
  }
}
