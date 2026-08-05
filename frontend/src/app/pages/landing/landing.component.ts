import { CommonModule, DOCUMENT } from '@angular/common';
import { Component, HostListener, Inject, OnInit, signal } from '@angular/core';
import { RouterModule } from '@angular/router';
import {
  LucideArrowRight,
  LucideBarChart3,
  LucideBookOpen,
  LucideBot,
  LucideBrainCircuit,
  LucideCheck,
  LucideDatabase,
  LucideGitBranch,
  LucideMenu,
  LucideMessageSquareText,
  LucideMoon,
  LucidePlay,
  LucideRocket,
  LucideShieldCheck,
  LucideSun,
  LucideUsers,
  LucideWorkflow,
  LucideX
} from '@lucide/angular';

@Component({
  selector: 'app-landing',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    LucideArrowRight,
    LucideBarChart3,
    LucideBookOpen,
    LucideBot,
    LucideBrainCircuit,
    LucideCheck,
    LucideDatabase,
    LucideGitBranch,
    LucideMenu,
    LucideMessageSquareText,
    LucideMoon,
    LucidePlay,
    LucideRocket,
    LucideShieldCheck,
    LucideSun,
    LucideUsers,
    LucideWorkflow,
    LucideX
  ],
  templateUrl: './landing.component.html',
  styleUrl: './landing.component.css'
})
export class LandingComponent implements OnInit {
  readonly mobileMenuOpen = signal(false);
  readonly darkMode = signal(false);
  readonly headerRaised = signal(false);

  private readonly themeStorageKey = 'chatbotFactoryLandingTheme';

  constructor(@Inject(DOCUMENT) private readonly document: Document) {}

  ngOnInit() {
    const savedTheme = this.safeLocalStorage()?.getItem(this.themeStorageKey);
    const prefersDark = this.safeWindow()?.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
    this.darkMode.set(savedTheme ? savedTheme === 'dark' : prefersDark);
    this.updateThemeClass();
    this.updateHeaderState();
  }

  toggleTheme() {
    this.darkMode.update(isDark => !isDark);
    this.safeLocalStorage()?.setItem(this.themeStorageKey, this.darkMode() ? 'dark' : 'light');
    this.updateThemeClass();
  }

  toggleMobileMenu() {
    this.mobileMenuOpen.update(open => !open);
  }

  closeMobileMenu() {
    this.mobileMenuOpen.set(false);
  }

  @HostListener('window:scroll')
  updateHeaderState() {
    this.headerRaised.set((this.safeWindow()?.scrollY ?? 0) > 8);
  }

  private updateThemeClass() {
    this.document.documentElement.classList.toggle('landing-dark-mode', this.darkMode());
    this.document.documentElement.classList.toggle('dark-mode', this.darkMode());
  }

  private safeWindow(): Window | null {
    return typeof window === 'undefined' ? null : window;
  }

  private safeLocalStorage(): Storage | null {
    if (typeof localStorage === 'undefined') return null;
    if (
      typeof localStorage.getItem !== 'function' ||
      typeof localStorage.setItem !== 'function'
    ) {
      return null;
    }
    return localStorage;
  }
}
