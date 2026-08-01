import { ComponentFixture, TestBed } from '@angular/core/testing';
import { PLATFORM_ID } from '@angular/core';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ChatbotsComponent } from './chatbots.component';
import { ToastService } from '../../services/toast.service';

describe('Chatbots', () => {
  let component: ChatbotsComponent;
  let fixture: ComponentFixture<ChatbotsComponent>;
  let toast: ToastService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ChatbotsComponent],
      providers: [
        provideHttpClient(),
        provideRouter([]),
        { provide: PLATFORM_ID, useValue: 'server' },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: convertToParamMap({ projectId: '1' }),
              queryParamMap: convertToParamMap({})
            }
          }
        }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(ChatbotsComponent);
    component = fixture.componentInstance;
    toast = TestBed.inject(ToastService);
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('opens the app delete modal without native browser confirm', () => {
    const confirmSpy = vi.spyOn(window, 'confirm');

    component.deleteChatbot({ id: 7, name: 'Support Assistant' });
    fixture.detectChanges();

    expect(confirmSpy).not.toHaveBeenCalled();
    expect(component.pendingDeleteAssistant()?.id).toBe(7);
    expect(fixture.nativeElement.textContent).toContain('Delete assistant?');
    expect(fixture.nativeElement.textContent).toContain('Support Assistant');
  });

  it('cancels assistant deletion from the modal', () => {
    component.deleteChatbot({ id: 7, name: 'Support Assistant' });

    component.cancelDeleteAssistant();

    expect(component.pendingDeleteAssistant()).toBeNull();
  });

  it('deletes through the real API and shows a success toast', () => {
    const deleteSpy = vi.spyOn((component as any).api, 'deleteChatbot').mockReturnValue(of({}));
    const toastSpy = vi.spyOn(toast, 'success');
    vi.spyOn(component, 'loadChatbots');

    component.deleteChatbot({ id: 7, name: 'Support Assistant' });
    component.confirmDeleteAssistant();

    expect(deleteSpy).toHaveBeenCalledWith(7);
    expect(component.pendingDeleteAssistant()).toBeNull();
    expect(toastSpy).toHaveBeenCalledWith('Assistant deleted successfully');
  });

  it('keeps the delete modal open on API failure', () => {
    vi.spyOn((component as any).api, 'deleteChatbot').mockReturnValue(throwError(() => ({ error: { detail: 'backend failed' } })));
    const toastSpy = vi.spyOn(toast, 'error');

    component.deleteChatbot({ id: 7, name: 'Support Assistant' });
    component.confirmDeleteAssistant();

    expect(component.pendingDeleteAssistant()?.id).toBe(7);
    expect(component.deleteError()).toBe('Assistant could not be deleted. Please try again.');
    expect(toastSpy).toHaveBeenCalledWith('Assistant could not be deleted. Please try again.');
  });
});
