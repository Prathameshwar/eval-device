'use client';

import { createContext, useContext, useMemo, type ReactNode } from 'react';

/**
 * Presentation only. Consumers supply the current permissions and enforce authorization
 * again on the server for every operation. This provider performs no authentication,
 * reads no token claims, and grants no access to an API or stored data.
 */

const NO_PERMISSIONS: readonly string[] = Object.freeze([]);

const PermissionContext = createContext<readonly string[]>(NO_PERMISSIONS);

type PermissionProviderProps = {
  /** The actor's resolved permission keys, e.g. `['invoice.read', 'company.*']`. */
  permissions: readonly string[];
  children: ReactNode;
};

export function PermissionProvider({ permissions, children }: PermissionProviderProps) {
  return (
    <PermissionContext.Provider value={permissions}>{children}</PermissionContext.Provider>
  );
}

/** The raw resolved set, for the rare caller that needs to test several keys at once. */
export function usePermissions(): readonly string[] {
  return useContext(PermissionContext);
}

/**
 * `held` satisfies `required` when it matches exactly, or when it is a wildcard whose prefix
 * matches: `invoice.*` covers `invoice.read` and `invoice.line.write`; bare `*` covers
 * everything. Wildcards only ever appear in the *granted* set — a required key is concrete.
 *
 * **Dot-separated**, because that is the platform catalogue's format. This used to test for `:*`,
 * which meant every wildcard grant silently matched nothing — a deny-by-default control failing
 * closed, so it broke quietly rather than loudly.
 */
function satisfies(held: string, required: string): boolean {
  if (held === required || held === '*') return true;
  if (!held.endsWith('.*')) return false;
  return required.startsWith(held.slice(0, -1));
}

/**
 * Deny by default: with no provider, or an empty set, nothing is drawn. An absent set means
 * "unknown", and rendering a money-mutating button on an unknown set is the wrong guess.
 */
export function useCan(key: string): boolean {
  const permissions = usePermissions();
  return useMemo(() => permissions.some((held) => satisfies(held, key)), [permissions, key]);
}

/**
 * A predicate over the resolved set, for filtering a *list* — a menu's items, a table's columns
 * and its row actions. `useCan` takes one key and so cannot be called in a loop; without this a
 * caller either calls a hook conditionally or hand-rolls the wildcard rule a second time.
 *
 * An `undefined` key means "not gated" and passes. That is not a hole in deny-by-default: an
 * item with no `permission` is one the caller never claimed to restrict, and the server still
 * enforces whatever the action actually needs.
 */
export function useGranted(): (key: string | undefined) => boolean {
  const permissions = usePermissions();
  return useMemo(
    () => (key: string | undefined) =>
      key === undefined || permissions.some((held) => satisfies(held, key)),
    [permissions],
  );
}

type CanProps = {
  permission: string;
  /** Rendered when denied. Default is nothing — no placeholder, no disabled ghost control. */
  fallback?: ReactNode;
  children: ReactNode;
};

export function Can({ permission, fallback = null, children }: CanProps) {
  return <>{useCan(permission) ? children : fallback}</>;
}
