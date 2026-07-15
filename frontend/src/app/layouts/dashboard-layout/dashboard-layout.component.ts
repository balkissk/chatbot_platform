import { CommonModule } from '@angular/common';
import { Component, HostListener } from '@angular/core';
import { RouterModule } from '@angular/router';
import {
  LucideBell,
  LucideChevronDown,
  LucideLogOut,
  LucideUser
} from '@lucide/angular';
import { AuthService } from '../../services/auth';

@Component({
  selector: 'app-dashboard-layout',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideBell, LucideChevronDown, LucideLogOut, LucideUser],
  templateUrl: './dashboard-layout.component.html',
  styleUrls: ['./dashboard-layout.component.css']
})
export class DashboardLayoutComponent {
  constructor(public auth: AuthService) {}

  navCollapsed = false;
  userMenuOpen = false;

  toggleNav() {
    this.navCollapsed = !this.navCollapsed;
  }

  toggleUserMenu() {
    this.userMenuOpen = !this.userMenuOpen;
  }

  closeUserMenu() {
    this.userMenuOpen = false;
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent) {
    if (!this.userMenuOpen) return;
    const target = event.target;
    if (target instanceof Element && !target.closest('.profile-menu')) {
      this.closeUserMenu();
    }
  }

  greeting() {
    const hour = new Date().getHours();
    if (hour >= 5 && hour < 12) return 'Good morning';
    if (hour >= 12 && hour < 18) return 'Good afternoon';
    return 'Good evening';
  }

  displayName() {
    return this.auth.currentUser()?.name || 'Workspace user';
  }

  displayRole() {
    const role = this.auth.currentUser()?.role || 'member';
    return role === 'admin' ? 'Platform Admin' : 'Workspace Manager';
  }

  initials() {
    return this.displayName()
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map(part => part[0]?.toUpperCase())
      .join('') || 'U';
  }
}
