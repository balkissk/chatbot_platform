import {
  isTemplateCompatibleWithPurpose,
  normalizeAssistantPurpose,
  purposeLabel,
  templatesForPurpose
} from './assistant-options';

describe('assistant purpose and template options', () => {
  it('normalizes purpose labels and aliases consistently', () => {
    expect(normalizeAssistantPurpose('Customer Support')).toBe('customer_support');
    expect(normalizeAssistantPurpose('Employee Knowledge')).toBe('employee_knowledge');
    expect(normalizeAssistantPurpose('Training & Certification')).toBe('training_certification');
    expect(normalizeAssistantPurpose('Lead Generation')).toBe('lead_generation');
    expect(purposeLabel('lead_generation')).toBe('Lead Generation');
  });

  it('returns only customer support templates for customer support', () => {
    const keys = templatesForPurpose('customer_support').map(template => template.key);
    expect(keys).toEqual([
      'customer_support_basic',
      'customer_support_rag',
      'customer_support_handoff',
      'customer_support_ticket_creation'
    ]);
  });

  it('returns only training templates for training and certification', () => {
    const keys = templatesForPurpose('Training & Certification').map(template => template.key);
    expect(keys).toContain('microsoft_certification_advisor');
    expect(keys).toContain('azure_training_assistant');
    expect(keys).not.toContain('company_policies_bot');
  });

  it('returns lead generation templates when the current purpose is lead generation', () => {
    const names = templatesForPurpose('Lead Generation').map(template => template.name);
    expect(names).toContain('Contact Capture');
    expect(names).toContain('Qualification Bot');
    expect(names).toContain('Meeting Preference');
    expect(names).not.toContain('HR Knowledge Bot');
  });

  it('detects purpose and current template incompatibility', () => {
    expect(isTemplateCompatibleWithPurpose('company_policies_bot', 'employee_knowledge')).toBe(true);
    expect(isTemplateCompatibleWithPurpose('company_policies_bot', 'lead_generation')).toBe(false);
    expect(isTemplateCompatibleWithPurpose('simple_lead_capture', 'lead_generation')).toBe(true);
  });
});
