import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { AuthService } from '../../services/auth';
import { LoginComponent } from './login.component';

describe('LoginComponent validation UX', () => {
  let fixture: ComponentFixture<LoginComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [
        provideRouter([]),
        {
          provide: AuthService,
          useValue: {
            consumeSessionMessage: () => '',
            login: () => {
              throw new Error('login should not be called by invalid form tests');
            }
          }
        }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
  });

  function errors() {
    const elements = fixture.nativeElement.querySelectorAll('.field-error') as NodeListOf<Element>;
    return Array.from(elements)
      .map((element: Element) => element.textContent?.trim());
  }

  it('does not show required errors on initial load', () => {
    const email = fixture.nativeElement.querySelector('#login-email') as HTMLInputElement;
    const password = fixture.nativeElement.querySelector('#login-password') as HTMLInputElement;

    expect(email.getAttribute('aria-invalid')).toBeNull();
    expect(password.getAttribute('aria-invalid')).toBeNull();
    expect(errors()).toEqual([]);
  });

  it('keeps submit disabled when email format is invalid', async () => {
    const email = fixture.nativeElement.querySelector('#login-email') as HTMLInputElement;
    const password = fixture.nativeElement.querySelector('#login-password') as HTMLInputElement;
    email.value = 'not-an-email';
    email.dispatchEvent(new Event('input'));
    password.value = 'password123';
    password.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector('.auth-submit') as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it('shows a required error after an empty field is blurred', async () => {
    const email = fixture.nativeElement.querySelector('#login-email') as HTMLInputElement;

    email.dispatchEvent(new Event('blur'));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(errors()).toContain('Enter your email address.');
  });

  it('shows required errors after an invalid submit attempt', () => {
    fixture.componentInstance.login();
    fixture.detectChanges();

    expect(errors()).toContain('Enter your email address.');
    expect(errors()).toContain('Enter your password.');
  });

  it('removes required errors when values become valid', async () => {
    fixture.componentInstance.login();
    fixture.detectChanges();

    const email = fixture.nativeElement.querySelector('#login-email') as HTMLInputElement;
    const password = fixture.nativeElement.querySelector('#login-password') as HTMLInputElement;
    email.value = 'manager@example.com';
    email.dispatchEvent(new Event('input'));
    password.value = 'password123';
    password.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(errors()).toEqual([]);
  });
});
