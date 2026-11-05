export type DirectoryPage<T> = { items: T[]; total: number; next_cursor: string | null; has_more: boolean };
export type ApiResult<T> = { value: T; error?: never } | { value?: never; error: string };
