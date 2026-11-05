export const CLINICAL_CAPABILITIES = [
  ['org.clinical.author', 'Clinical author'],
  ['org.clinical.review', 'Scenario reviewer'],
  ['org.training.instruct', 'Training instructor'],
  ['org.clinical.read', 'Clinical reader'],
] as const;

export type ClinicalCapability = (typeof CLINICAL_CAPABILITIES)[number][0];
export type CapabilityAssignment = {
  capability: ClinicalCapability;
  granted_at: string;
  granted_by: string;
  revoked_at: string | null;
  revoked_by: string | null;
};
