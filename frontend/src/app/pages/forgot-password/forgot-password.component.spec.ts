import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Subject } from 'rxjs';

import { AuthService } from '../../services/auth';
import { ForgotPasswordComponent } from './forgot-password.component';

describe('ForgotPasswordComponent validation UX', () => {
  let fixture: ComponentFixture<ForgotPasswordComponent>;
  let forgotPasswordResponse: Subject<{ message: string }>;
  let forgotPassword: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    forgotPasswordResponse = new Subject<{ message: string }>();
    forgotPassword = vi.fn(() => forgotPasswordResponse.asObservable());

    await TestBed.configureTestingModule({
      imports: [ForgotPasswordComponent],
      providers: [
        provideRouter([]),
        {
          provide: AuthService,
          useValue: {
            forgotPassword
          }
        }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(ForgotPasswordComponent);
    fixture.detectChanges();
  });

  function errors() {
    const elements = fixture.nativeElement.querySelectorAll('.field-error') as NodeListOf<Element>;
    return Array.from(elements)
      .map((element: Element) => element.textContent?.trim());
  }

  it('does not show required errors on initial load', () => {
    expect(errors()).toEqual([]);
  });

  it('shows a required error after the empty email field is blurred', async () => {
    const email = fixture.nativeElement.querySelector('#forgot-email') as HTMLInputElement;

    email.dispatchEvent(new Event('blur'));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(errors()).toContain('Enter your email address.');
  });

  it('shows a required error after an invalid submit attempt', () => {
    fixture.componentInstance.submit();
    fixture.detectChanges();

    expect(errors()).toContain('Enter your email address.');
  });

  it('removes the required error when the email becomes valid', async () => {
    fixture.componentInstance.submit();
    fixture.detectChanges();

    const email = fixture.nativeElement.querySelector('#forgot-email') as HTMLInputElement;
    email.value = 'manager@example.com';
    email.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(errors()).toEqual([]);
  });

  it('shows a loading state and prevents double submission while sending', async () => {
    const component = fixture.componentInstance;
    const email = fixture.nativeElement.querySelector('#forgot-email') as HTMLInputElement;
    email.value = 'manager@example.com';
    email.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    await fixture.whenStable();

    component.submit();
    component.submit();
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector('.auth-submit') as HTMLButtonElement;
    expect(button.textContent?.trim()).toBe('Sending...');
    expect(button.disabled).toBe(true);
    expect(forgotPassword).toHaveBeenCalledTimes(1);
  });

  it('shows the success state without revealing whether the account exists', async () => {
    const component = fixture.componentInstance;
    const email = fixture.nativeElement.querySelector('#forgot-email') as HTMLInputElement;
    email.value = 'unknown@example.com';
    email.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    await fixture.whenStable();

    component.submit();
    forgotPasswordResponse.next({
      message: 'If an account exists for this email, a password reset link has been sent.'
    });
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.querySelector('#forgot-email')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Check your inbox');
    expect(fixture.nativeElement.textContent).toContain('If an account exists for this email, a password reset link has been sent.');
    expect(fixture.nativeElement.textContent).toContain('Back to sign in');
  });
});
