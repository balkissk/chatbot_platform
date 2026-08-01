export type AssistantLanguageCode = 'en' | 'fr';
export type AssistantChannelCode = 'public_chat' | 'web_widget' | 'rest_public_api';
export type AssistantPurposeCode = 'customer_support' | 'employee_knowledge' | 'training_certification' | 'lead_generation' | 'custom';

export type AssistantTemplateOption = {
  key: string;
  name: string;
  description: string;
};

export const ASSISTANT_LANGUAGE_OPTIONS: ReadonlyArray<{ label: string; value: AssistantLanguageCode }> = [
  { label: 'English', value: 'en' },
  { label: 'French', value: 'fr' }
];

export const ASSISTANT_CHANNEL_OPTIONS: ReadonlyArray<{ label: string; value: AssistantChannelCode; description: string }> = [
  { label: 'Public Chat', value: 'public_chat', description: 'Publish a hosted chat page for end users.' },
  { label: 'Web Widget', value: 'web_widget', description: 'Embed the assistant into an external website.' },
  { label: 'REST Public API', value: 'rest_public_api', description: 'Integrate the assistant through a secured runtime API.' }
];

export const ASSISTANT_PURPOSE_OPTIONS: ReadonlyArray<{ label: string; value: AssistantPurposeCode }> = [
  { label: 'Customer Support', value: 'customer_support' },
  { label: 'Employee Knowledge', value: 'employee_knowledge' },
  { label: 'Training & Certification', value: 'training_certification' },
  { label: 'Lead Generation', value: 'lead_generation' },
  { label: 'Custom', value: 'custom' }
];

export const ASSISTANT_TEMPLATE_OPTIONS: Readonly<Record<AssistantPurposeCode, ReadonlyArray<AssistantTemplateOption>>> = {
  customer_support: [
    { key: 'customer_support_basic', name: 'Customer Support Basic', description: 'Message, customer question, AI/RAG answer, and closing step.' },
    { key: 'customer_support_rag', name: 'Customer Support + RAG', description: 'Support assistant optimized for answering from uploaded knowledge.' },
    { key: 'customer_support_handoff', name: 'Customer Support + Human Handoff', description: 'Support answer flow with a handoff step for complex issues.' },
    { key: 'customer_support_ticket_creation', name: 'Customer Support + Ticket Creation', description: 'Collect issue details and prepare a support ticket handoff.' }
  ],
  employee_knowledge: [
    { key: 'hr_knowledge_bot', name: 'HR Knowledge Bot', description: 'Answer HR policy and employee process questions from knowledge.' },
    { key: 'it_helpdesk_bot', name: 'IT Helpdesk Bot', description: 'Guide employees through common IT support requests.' },
    { key: 'company_policies_bot', name: 'Company Policies Bot', description: 'Help employees find company policy answers quickly.' },
    { key: 'employee_onboarding_bot', name: 'Employee Onboarding Bot', description: 'Guide new employees through onboarding steps and resources.' }
  ],
  training_certification: [
    { key: 'microsoft_certification_advisor', name: 'Microsoft Certification Advisor', description: 'Recommend Microsoft certification paths based on goals.' },
    { key: 'azure_training_assistant', name: 'Azure Training Assistant', description: 'Help users choose Azure learning paths and next courses.' },
    { key: 'cybersecurity_learning_assistant', name: 'Cybersecurity Learning Assistant', description: 'Recommend cybersecurity learning tracks and certifications.' },
    { key: 'course_recommendation_bot', name: 'Course Recommendation Bot', description: 'Collect learner goals and suggest relevant courses.' }
  ],
  lead_generation: [
    { key: 'simple_lead_capture', name: 'Contact Capture', description: 'Collect contact details and route the request to the team.' },
    { key: 'sales_starter', name: 'Qualification Bot', description: 'Capture business needs and qualify requests for sales follow-up.' },
    { key: 'consultation_booking', name: 'Meeting Scheduler', description: 'Capture consultation needs, preferred date, and contact details.' },
    { key: 'cloud_assessment_lead_form', name: 'Cloud Assessment Lead Form', description: 'Qualify Azure and Microsoft Cloud assessment requests.' },
    { key: 'training_registration_bot', name: 'Training Registration Bot', description: 'Collect training interest and registration contact details.' }
  ],
  custom: [
    { key: 'blank_business_bot', name: 'Blank Business Bot', description: 'A minimal business assistant starter flow.' },
    { key: 'ai_assistant_starter', name: 'AI Assistant Starter', description: 'Start with a question and AI/RAG answer structure.' },
    { key: 'faq_starter', name: 'FAQ Starter', description: 'Start with a guided FAQ-style button flow.' },
    { key: 'sales_starter', name: 'Sales Starter', description: 'Start with a simple sales intake and qualification flow.' }
  ]
};

export function normalizeAssistantLanguage(value: unknown): AssistantLanguageCode {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'english' || normalized === 'anglais' || normalized === 'en') return 'en';
  if (normalized === 'french' || normalized === 'francais' || normalized === 'fr') return 'fr';
  return 'fr';
}

export function languageLabel(value: unknown): string {
  const raw = String(value || '').trim();
  const normalized = raw.toLowerCase();
  if (normalized === 'english' || normalized === 'anglais' || normalized === 'en') return 'English';
  if (normalized === 'french' || normalized === 'francais' || normalized === 'fr') return 'French';
  if (!raw) return '';
  return raw.toUpperCase();
}

export function normalizeAssistantChannel(value: unknown): AssistantChannelCode {
  const normalized = String(value || '').trim().toLowerCase().replace(/\s+/g, '_');
  if (normalized === 'public_chat' || normalized === 'public' || normalized === 'web' || normalized === 'web_chat') return 'public_chat';
  if (normalized === 'web_widget' || normalized === 'widget') return 'web_widget';
  if (normalized === 'rest_public_api' || normalized === 'rest_api' || normalized === 'public_api' || normalized === 'api') return 'rest_public_api';
  return 'web_widget';
}

export function normalizeAssistantPurpose(value: unknown): AssistantPurposeCode {
  const normalized = String(value || '').trim().toLowerCase().replace(/&/g, 'and').replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  if (normalized === 'customer_support' || normalized === 'support') return 'customer_support';
  if (normalized === 'employee_knowledge' || normalized === 'employee' || normalized === 'hr' || normalized === 'knowledge') return 'employee_knowledge';
  if (normalized === 'training_certification' || normalized === 'training_and_certification' || normalized === 'training' || normalized === 'certification') return 'training_certification';
  if (normalized === 'lead_generation' || normalized === 'lead' || normalized === 'sales') return 'lead_generation';
  return 'custom';
}

export function purposeLabel(value: unknown): string {
  const normalized = normalizeAssistantPurpose(value);
  return ASSISTANT_PURPOSE_OPTIONS.find(option => option.value === normalized)?.label || 'Custom';
}

export function templatesForPurpose(value: unknown): ReadonlyArray<AssistantTemplateOption> {
  return ASSISTANT_TEMPLATE_OPTIONS[normalizeAssistantPurpose(value)];
}

export function templatePurpose(templateKey: unknown): AssistantPurposeCode | '' {
  const key = String(templateKey || '').trim();
  if (!key) return '';
  for (const purpose of Object.keys(ASSISTANT_TEMPLATE_OPTIONS) as AssistantPurposeCode[]) {
    if (ASSISTANT_TEMPLATE_OPTIONS[purpose].some(template => template.key === key)) {
      return purpose;
    }
  }
  return '';
}

export function templateOption(templateKey: unknown): AssistantTemplateOption | undefined {
  const key = String(templateKey || '').trim();
  for (const options of Object.values(ASSISTANT_TEMPLATE_OPTIONS)) {
    const found = options.find(template => template.key === key);
    if (found) return found;
  }
  return undefined;
}

export function isTemplateCompatibleWithPurpose(templateKey: unknown, purpose: unknown): boolean {
  const key = String(templateKey || '').trim();
  if (!key) return true;
  return templatesForPurpose(purpose).some(template => template.key === key);
}

export function channelLabel(value: unknown): string {
  const raw = String(value || '').trim();
  const normalized = normalizeAssistantChannel(value);
  if (!raw) return '';
  return ASSISTANT_CHANNEL_OPTIONS.find(option => option.value === normalized)?.label || raw;
}

export function channelDescription(value: unknown): string {
  const normalized = normalizeAssistantChannel(value);
  return ASSISTANT_CHANNEL_OPTIONS.find(option => option.value === normalized)?.description || '';
}
