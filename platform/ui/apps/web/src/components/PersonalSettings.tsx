'use client';
import { BackNavigation } from './BackNavigation';
import { callAction } from '@/lib/call-action';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button, Card, CardBody, Notice, PageHeader, TextField } from '@pms/ui';
import { readPersonal, savePersonal, type PersonalProfile } from '@/lib/personal-actions';
export function PersonalSettings() {
  const router = useRouter();
  const [profile, setProfile] = useState<PersonalProfile>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let live = true;
    void callAction(() => readPersonal()).then((r) => {
      if (!live) return;
      if (r.error !== undefined) setError(r.error);
      else setProfile(r.value);
    });
    return () => {
      live = false;
    };
  }, [reload]);
  async function save() {
    if (!profile) return;
    setBusy(true);
    setError(undefined);
    const r = await callAction(() => savePersonal(profile.display_name, profile.phone ?? ''));
    setBusy(false);
    if (r.error !== undefined) setError(r.error);
    else {
      setProfile({ ...profile, ...r.value });
      setSaved(true);
      router.refresh();
    }
  }
  return (
    <div className="pms-page">
      <BackNavigation href="/home" label="Back to home" />
      <PageHeader
        title="Personal settings"
        lede="Manage your account display name and contact number. Password and email changes are available in your account menu."
      />
      {error ? (
        <Notice
          tone="danger"
          title="Request failed"
          action={
            <Button variant="ghost" onClick={() => setReload((v) => v + 1)}>
              Retry
            </Button>
          }
        >
          {error}
        </Notice>
      ) : null}
      {saved ? (
        <Notice tone="success" title="Profile saved">
          Your account details have been updated.
        </Notice>
      ) : null}
      {profile ? (
        <Card>
          <CardBody>
            <form
              className="pms-console__tenant-form"
              onSubmit={(e) => {
                e.preventDefault();
                void save();
              }}
            >
              <TextField
                label="Display name"
                required
                maxLength={256}
                value={profile.display_name}
                onChange={(e) => {
                  setProfile({ ...profile, display_name: e.target.value });
                  setSaved(false);
                }}
              />
              <TextField
                label="Phone"
                type="tel"
                maxLength={80}
                value={profile.phone ?? ''}
                onChange={(e) => {
                  setProfile({ ...profile, phone: e.target.value });
                  setSaved(false);
                }}
              />
              <TextField label="Sign-in email" value={profile.email} readOnly />
              <Button type="submit" loading={busy}>
                Save profile
              </Button>
            </form>
          </CardBody>
        </Card>
      ) : (
        <p role="status">Loading your profile…</p>
      )}
    </div>
  );
}
