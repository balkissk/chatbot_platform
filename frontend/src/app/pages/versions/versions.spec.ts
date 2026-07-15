import { ComponentFixture, TestBed } from '@angular/core/testing';
import { PLATFORM_ID } from '@angular/core';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';

import { VersionsComponent } from './versions.component';

describe('Versions', () => {
  let component: VersionsComponent;
  let fixture: ComponentFixture<VersionsComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [VersionsComponent],
      providers: [
        provideHttpClient(),
        provideRouter([]),
        { provide: PLATFORM_ID, useValue: 'server' },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: convertToParamMap({ projectId: '1', chatbotId: '1' })
            }
          }
        }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(VersionsComponent);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
