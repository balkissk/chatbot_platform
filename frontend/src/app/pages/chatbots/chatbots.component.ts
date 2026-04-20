import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../../services/api';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { RouterModule } from '@angular/router';

@Component({
  selector: 'app-chatbots',
  standalone: true,
  imports: [CommonModule, FormsModule , RouterModule],
  templateUrl: './chatbots.component.html',
})
export class ChatbotsComponent implements OnInit {

  projectId!: number;
  chatbots: any[] = [];
  newChatbotName: string = '';
  projectName: string = '';

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private router: Router
  ) {}

  ngOnInit() {
    this.projectId = Number(this.route.snapshot.paramMap.get('projectId'));
    this.loadChatbots();

  }


  loadChatbots() {
    this.api.getChatbotsByProject(this.projectId)
      .subscribe(res => {
        this.chatbots = res;
        console.log(this.chatbots);

        if (res.length > 0) {
          this.projectName = "Project " + this.projectId;
        }

      });
  }

  createChatbot() {
    const chatbot = {
      name: this.newChatbotName,
      project_id: this.projectId,
      language: "fr",
      type: "basic"
    };

    this.api.createChatbot(chatbot)
      .subscribe(() => {
        this.newChatbotName = '';
        this.loadChatbots();
      });

  }
  goBack() {
    this.router.navigate(['/projects']);
  }


}
