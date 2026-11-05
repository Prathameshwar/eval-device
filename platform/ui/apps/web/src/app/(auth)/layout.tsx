import { Badge, CheckCircleIcon, ShieldIcon, ThemeSwitcher, currentYear } from '@pms/ui';
import { BrandLockup } from '@/components/BrandMark';

/**
 * The split-screen every authentication route sits in: identity and argument on the left,
 * the form on the right.
 *
 * A route group (`(auth)`) rather than a path segment, so the URLs stay `/login` and
 * `/forgot-password` — the layout is a presentation decision and has no business in the address.
 *
 * The panel's claims are all statements about the platform's design that the codebase actually
 * makes good on (server-side scope, audit records, private media). A compliance badge would be a
 * claim about an audit nobody has run, so there isn't one.
 */

const POINTS = [
  {
    title: 'Objective, repeatable scoring',
    body: 'Every attempt is measured against the same rubric, not against a reviewer’s memory.',
  },
  {
    title: 'Traceable to the transcript',
    body: 'Each score points back at the conversation turn that earned it.',
  },
  {
    title: 'Tenant-isolated by design',
    body: 'Organisation, department and device scope are enforced on the server, not in the browser.',
  },
] as const;

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="pms-auth">
      <aside className="pms-auth__panel">
        <div className="pms-auth__panel-inner">
          <BrandLockup />

          <div className="pms-auth__pitch">
            <p className="pms-auth__claim">Clinical conversations, scored with evidence.</p>
            <div className="pms-auth__rule" aria-hidden="true" />
            <p className="pms-auth__claim-sub">
              Run a training interview, then see exactly how it was assessed — turn by turn.
            </p>
          </div>

          <div className="pms-auth__aside">
            <ul className="pms-auth__points">
              {POINTS.map((point) => (
                <li className="pms-auth__point" key={point.title}>
                  <span className="pms-auth__point-icon" aria-hidden="true">
                    <CheckCircleIcon size={17} />
                  </span>
                  <span>
                    <span className="pms-auth__point-title">{point.title}</span>
                    {point.body}
                  </span>
                </li>
              ))}
            </ul>

            <p className="pms-auth__trust">
              <ShieldIcon size={15} />
              Audit-trailed, role-scoped, and media kept private by default.
            </p>
          </div>
        </div>
      </aside>

      <main className="pms-auth__main">
        <div className="pms-auth__bar">
          <ThemeSwitcher label="Colour theme" />
        </div>

        <div className="pms-auth__body">{children}</div>

        <div className="pms-auth__foot">
          <span className="pms-fine">© {currentYear()} AI Evaluator</span>
          <Badge tone="neutral" variant="outline">
            Account access
          </Badge>
        </div>
      </main>
    </div>
  );
}
