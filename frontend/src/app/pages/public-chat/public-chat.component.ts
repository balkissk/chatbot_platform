import { CommonModule } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-public-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './public-chat.component.html',
  styleUrls: ['./public-chat.component.css']
})
export class PublicChatComponent implements OnInit {
  chatbotId: number;
  chatbot = signal<any | null>(null);
  message = '';
  messages = signal<{ role: 'user' | 'bot'; text: string; options?: string[]; feedback?: string }[]>([]);
  sources = signal<any[]>([]);
  loading = signal(false);
  error = signal('');
  sessionId = signal<number | undefined>(undefined);

  constructor(
    private route: ActivatedRoute,
    private api: ApiService
  ) {
    this.chatbotId = Number(this.route.snapshot.paramMap.get('chatbotId'));
  }

  ngOnInit() {
    this.api.getPublicChatbot(this.chatbotId).subscribe({
      next: chatbot => this.chatbot.set(chatbot),
      error: err => this.error.set(err.error?.detail || 'Chatbot is not available')
    });
  }

  async send(option?: string) {
    const text = option || this.message.trim();
    if (!text || this.loading()) return;

    this.messages.update(messages => [...messages, { role: 'user', text }]);
    this.message = '';
    this.loading.set(true);
    this.error.set('');
    this.sources.set([]);

    let streamingIndex: number | undefined;
    let streamedText = '';

    try {
      await this.api.publicChatStream({
        chatbot_id: this.chatbotId,
        message: text,
        session_id: this.sessionId()
      }, event => {
        if (event.type === 'start') {
          this.sessionId.set(event.session_id);
          return;
        }

        if (event.type === 'token') {
          streamedText += event.text || '';
          this.messages.update(messages => {
            const next = [...messages];
            if (streamingIndex === undefined) {
              streamingIndex = next.length;
              next.push({ role: 'bot', text: streamedText });
            } else {
              next[streamingIndex] = { ...next[streamingIndex], text: streamedText };
            }
            return next;
          });
          return;
        }

        if (event.type === 'final') {
          this.sessionId.set(event.session_id);
          this.sources.set(event.sources || []);
          const botMessages = this.toBotMessages(event);

          if (streamingIndex === undefined) {
            this.messages.update(messages => [...messages, ...botMessages]);
            return;
          }

          this.messages.update(messages => {
            const next = [...messages];
            const first = botMessages[0] || { role: 'bot' as const, text: streamedText, options: [] };
            next[streamingIndex!] = {
              role: 'bot',
              text: streamedText || first.text,
              options: first.options || []
            };
            return [...next, ...botMessages.slice(1)];
          });
          return;
        }

        if (event.type === 'error') {
          throw new Error(event.detail || 'Chat failed');
        }
      });
    } catch (err: any) {
      this.error.set(err?.message || 'Chat failed');
    } finally {
      this.loading.set(false);
    }
  }

  private toBotMessages(response: any) {
    if (Array.isArray(response.messages) && response.messages.length > 0) {
      return response.messages.map((item: any) => ({
        role: 'bot' as const,
        text: item.text || '',
        options: item.options || []
      }));
    }

    return [{
      role: 'bot' as const,
      text: response.response || '',
      options: response.options || []
    }];
  }

  submitFeedback(index: number, rating: 'helpful' | 'not_helpful') {
    const sessionId = this.sessionId();
    if (!sessionId || this.messages()[index]?.feedback) return;

    this.api.submitPublicFeedback({
      chatbot_id: this.chatbotId,
      session_id: sessionId,
      rating
    }).subscribe({
      next: () => {
        this.messages.update(messages => messages.map((item, itemIndex) => (
          itemIndex === index ? { ...item, feedback: rating } : item
        )));
      },
      error: err => this.error.set(err.error?.detail || 'Could not save feedback')
    });
  }
}
