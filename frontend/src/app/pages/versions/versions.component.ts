import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../../services/api';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-versions',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './versions.component.html',
})
export class VersionsComponent implements OnInit {

  projectId!: number;
  chatbotId!: number;

  versions: any[] = [];

  constructor(
    private route: ActivatedRoute,
    private api: ApiService
  ) {}

  ngOnInit() {
    this.projectId = Number(this.route.snapshot.paramMap.get('projectId'));
    this.chatbotId = Number(this.route.snapshot.paramMap.get('chatbotId'));

    this.loadVersions();
  }

  loadVersions() {
    this.api.getVersionsByChatbot(this.chatbotId)
      .subscribe(res => {
        this.versions = res.sort((a: any, b: any) => b.version_number - a.version_number);
        console.log(res);
      });
  }
  createVersion() {
    const data = {
      chatbot_id: this.chatbotId
    };

    this.api.createVersion(data)
      .subscribe(() => {
        this.loadVersions(); // 🔥 refresh بعد create
      });
  }
  publish(versionId: number) {
    this.api.publishVersion(versionId)
      .subscribe(() => {
        this.loadVersions();
      });
  }

  archive(versionId: number) {
    this.api.archiveVersion(versionId)
      .subscribe(() => {
        this.loadVersions();
      });
  }
}
