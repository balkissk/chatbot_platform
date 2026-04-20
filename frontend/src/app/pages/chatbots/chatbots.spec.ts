import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Chatbots } from './chatbots';

describe('Chatbots', () => {
  let component: Chatbots;
  let fixture: ComponentFixture<Chatbots>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Chatbots],
    }).compileComponents();

    fixture = TestBed.createComponent(Chatbots);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
