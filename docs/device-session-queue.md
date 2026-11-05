# Device session queue

The web Sessions page plans an ordered queue for each enrolled device. Human-test
receives the next assignment over its existing authenticated HTTPS connection.
There is no database access, learner password or signing private key on the desktop.

## Instructor workflow

Choose a device, select **Plan sessions**, set the practice case, language and
duration, then select trainees. Shared defaults apply to newly added rows; each row
can use a different case, language or duration. The current duration range is 30
seconds to 10 minutes. The per-turn capture limit remains independent.

The queue accepts up to 50 assignments in one atomic request and 100 waiting
assignments per device. Request identities make a manual retry safe after a lost
response. Drag rows or use Move up / Move down; only waiting sessions can be
edited, removed or reordered. Pause prevents the next session from beginning and
does not interrupt the current session. Stale edits return a conflict instead of
overwriting another instructor's order.

Every assignment expires exactly 24 hours after it was added. Editing, reordering,
pausing, beginning or reconnecting never extends that deadline. Expired waiting
sessions cannot start; a running session stops at its duration or the original
24-hour deadline, whichever comes first. Expiry does not erase completed history.

## Desktop workflow

Human-test previews the next trainee's case, language and initial observations.
Begin session starts the duration and creates a conversation linked to that
assignment. The trainee name remains visible. An unavailable assigned language blocks Begin with a clear message; it never silently falls back to another language. Assigned case/language/observations
cannot be changed mid-session; Previous returns to those details, and returning
to the conversation preserves the same assignment.

**Complete & Close** ends the current practice and returns to setup so the next
person can begin. Closing the application cancels its active assigned session.
An instructor can also choose **End session** in the web app. Capture/playback
stop before the desktop acknowledges completion. The web shows stopping while
waiting for acknowledgement. Polling occurs approximately every two seconds;
local capture stops after 20 seconds without a successful poll, within the
server's 30-second lease. Revocation, inactive scope, retired cases or changed
device departments prevent admission/renewal. Interrupted sessions are never
automatically replayed or resumed by a restarted desktop.

With no available assignment, standalone practice remains available with the
label **No trainee assigned**. An assignment arriving during standalone practice
waits until that practice is completed, including when the user returns to its
setup with Previous. Standalone activity is never retroactively assigned to a
trainee. A paused queue also leaves standalone practice available.

## Ownership and history

Assignments record the instructor, learner, organization, department, device and
published scenario. Device-owned conversations have an immutable assignment link;
existing conversation/turn ownership and tenant restrictions remain in force.
Instructors with the required scoped permissions can plan/manage sessions.
Trainees can view only their own assigned-session results. Platform administrator
status alone does not grant access. Results show the saved conversation text when
available, subject to existing retention and desktop history synchronization.
Local conversation text is explicitly client-reported; a selected learner is not
proof of the identity of the person physically using the device. Earlier training
sessions remain accessible through **Earlier sessions**.

## Installation and verification

Deploy the API and web changes together, apply forward migration
`0044_session_queue`, and reapply `platform/api/deploy/grant-runtime-access.sql`.
The API role can manage the queue; worker/retention roles receive no access to its
tables. Restart the API and update/restart Human-test. Local initialization applies
migrations; reapply the runtime grant bundle as described in the API guide. The
existing hosted deployment script performs both migration and grants. No
manual capability flag or fabricated `patient_interview_v1` registration is needed
for this desktop workflow. The separate training-agent endpoints remain available.

The API performs bounded expiry maintenance every ten seconds even with no
connected desktop. Admission and conversation checks independently enforce the
deadline. Assignment identity/deadline, terminal transitions and a single active
session per device are also protected by database constraints/triggers. All
queue changes and their audit events commit atomically.

Tests cover queue order, idempotency, simultaneous begins, user/device scope,
individual trainee history, expiry before/after begin, background expiry,
revocation, lease loss, standalone handoff, assigned defaults and web completion.
Live hosted deployment and physical microphone/speaker verification remain separate
from the isolated database, browser fixtures and native desktop layout checks.
