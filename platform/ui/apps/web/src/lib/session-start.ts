export function canStartSession(permissions: readonly string[]) {
  return ['org.results.read', 'org.processing.execute', 'org.playback.execute', 'org.training.instruct']
    .every(permission => permissions.includes(permission));
}

export function sessionLanguage(code: string) {
  try { return new Intl.DisplayNames(['en'], { type: 'language' }).of(code) ?? code; }
  catch { return code; }
}
