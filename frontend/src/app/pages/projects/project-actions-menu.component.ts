import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { RouterModule } from '@angular/router';
import {
  LucideArchive,
  LucideCopy,
  LucidePencil,
  LucideTrash2
} from '@lucide/angular';

@Component({
  selector: 'app-project-actions-menu',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    LucideArchive,
    LucideCopy,
    LucidePencil,
    LucideTrash2
  ],
  templateUrl: './project-actions-menu.component.html',
  styleUrls: ['./project-actions-menu.component.css']
})
export class ProjectActionsMenuComponent {
  @Input({ required: true }) project!: any;
  @Input() position = { top: 0, left: 0 };
  @Input() deleting = false;
  @Input() duplicating = false;
  @Input() archiving = false;
  @Input() restoring = false;
  @Input() archived = false;

  @Output() closeMenu = new EventEmitter<void>();
  @Output() renameProject = new EventEmitter<any>();
  @Output() duplicateProject = new EventEmitter<any>();
  @Output() archiveProject = new EventEmitter<any>();
  @Output() restoreProject = new EventEmitter<any>();
  @Output() deleteProject = new EventEmitter<any>();
}
