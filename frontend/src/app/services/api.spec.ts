import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';

import { ApiService } from './api';

describe('Api', () => {
  let service: ApiService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient()]
    });
    service = TestBed.inject(ApiService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
