'use client';
import { useEffect, useState } from 'react';
import { Button, Notice } from '@pms/ui';
import { listCapabilities, setCapability } from '@/lib/capability-actions';
import { CLINICAL_CAPABILITIES, type CapabilityAssignment, type ClinicalCapability } from '@/lib/clinical-capabilities';
import { callAction } from '@/lib/call-action';

export function MemberCapabilities({ contextId, memberId, role, departmentId }: {
  contextId: string; memberId: string; role?: string | null; departmentId?: string | null;
}) {
  const [items, setItems] = useState<CapabilityAssignment[]>([]);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState<ClinicalCapability>();
  const [reload, setReload] = useState(0);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let live = true;
    setLoaded(false);
    setItems([]);
    setError(undefined);
    void callAction(() => listCapabilities(contextId, memberId)).then((result) => {
      if (!live) return;
      if (result.error) setError(result.error);
      else { setItems(result.value ?? []); setError(undefined); setLoaded(true); }
    });
    return () => { live = false; };
  }, [contextId, memberId, reload]);
  async function change(capability: ClinicalCapability, enabled: boolean) {
    setBusy(capability);
    setError(undefined);
    const result = await callAction(() => setCapability(contextId, memberId, capability, enabled));
    setBusy(undefined);
    if (result.error) setError(result.error);
    else { setLoaded(false); setReload((value) => value + 1); }
  }
  return <section aria-labelledby="clinical-capabilities-heading">
    <h2 id="clinical-capabilities-heading">Clinical and training responsibilities</h2>
    <p>Assignments take effect on the next request. A separate reviewer should approve authored content.</p>
    {error ? <Notice tone="danger" title="Could not load or update responsibilities"
      action={<Button variant="ghost" disabled={!!busy} onClick={() => setReload(value => value + 1)}>Reload responsibilities</Button>}>{error}</Notice> : null}
    <ul>{CLINICAL_CAPABILITIES.map(([capability, label]) => {
      const assignment = items.find((row) => row.capability === capability);
      const includedWithRole = role === 'org_admin' && capability === 'org.clinical.author';
      const enabled = includedWithRole || (!!assignment && !assignment.revoked_at);
      const eligible = capability === 'org.clinical.read'
        ? ['org_admin', 'org_user', 'org_read_only'].includes(role ?? '')
        : ['org_admin', 'org_user'].includes(role ?? '') &&
          (capability === 'org.training.instruct' || !departmentId);
      return <li key={capability}>
        <strong>{label}</strong>{' — '}{includedWithRole ? 'Included with tenant administrator role' : enabled ? 'Assigned' : 'Not assigned'}{' '}
        {!includedWithRole && <Button variant="ghost" disabled={!loaded || !!busy || (!eligible && !enabled)} loading={busy === capability}
          onClick={() => void change(capability, !enabled)}>
          {enabled ? 'Revoke' : 'Assign'}
        </Button>}
        {!eligible ? <span className="pms-hint">{enabled ? 'Inactive for this role or scope. Revoke to remove the saved assignment.' : 'Requires an eligible staff role and scope.'}</span> : null}
      </li>;
    })}</ul>
  </section>;
}
