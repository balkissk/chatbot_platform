import { ComponentFixture, TestBed } from '@angular/core/testing';
import { PLATFORM_ID } from '@angular/core';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';

import { ChatbotsComponent } from './chatbots.component';

describe('Chatbots', () => {
  let component: ChatbotsComponent;
  let fixture: ComponentFixture<ChatbotsComponent>;

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
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
