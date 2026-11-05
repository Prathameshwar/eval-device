/**
 * Shared React components and utilities.
 * Import '@pms/ui/styles.css' once and use a 'pms-root' wrapper.
 * Application routes, branding, authentication and API adapters belong to consumers.
 */

/* ---------- theme ---------- */
export {
  THEME_PREFERENCES,
  THEME_COOKIE,
  THEME_STORAGE_KEY,
  PREFERS_DARK_QUERY,
  isThemePreference,
  resolveTheme,
  colorSchemeFor,
  readStoredPreference,
  persistPreference,
  applyTheme,
  themeScript,
} from './lib/theme';
export type { ThemePreference, ResolvedTheme } from './lib/theme';
export { ThemeProvider, useTheme } from './components/ThemeProvider';
export { ThemeSwitcher } from './components/ThemeSwitcher';

/* ---------- display config, formatting, permissions ---------- */
export {
  EM_DASH,
  DEFAULT_DISPLAY_CONFIG,
  roundDecimalString,
  groupDigits,
  formatMoney,
  formatQuantity,
  formatPercent,
  formatCompact,
  formatDate,
  formatDateTime,
  formatRange,
  formatRelative,
} from './lib/format';
export type {
  DisplayConfig,
  RoundingMode,
  DigitGrouping,
  CurrencyDisplay,
  CurrencySymbolPosition,
  NegativeFormat,
  MoneyOptions,
} from './lib/format';
export { DisplayConfigProvider, useDisplayConfig, useFormatters } from './lib/display-config';
export type { Formatters } from './lib/display-config';
export {
  PermissionProvider,
  usePermissions,
  useCan,
  useGranted,
  Can,
} from './lib/permissions';
/* The scheme allowlist for any href that came from a payload. Exported because an app rendering a
 * link from server data needs the same check, and a second implementation is the one that is wrong. */
export { isSafeHref } from './lib/url';
/* One plural rule for the platform's copy. Exported for the same reason as the formatters: a screen
 * writing "3 companys" beside a table that says "3 companies" is one rule applied twice. */
export { pluralNoun, pluralOf } from './lib/text';
export { usePlacement } from './lib/placement';
export type { Placement, PlacementOptions } from './lib/placement';
export { currentYear } from './lib/date';

/* ---------- shell ---------- */
export { AppShell } from './components/AppShell';
export { Rail, RailSection, RailItem, RailFooter } from './components/Rail';
export { OrgSwitcher } from './components/OrgSwitcher';
export { TopBar } from './components/TopBar';
export { ContextChip, RoleChip } from './components/Chips';
export type { ChipTone } from './components/Chips';
export { NotificationBell } from './components/NotificationBell';
export { UserMenu } from './components/UserMenu';
export type { UserMenuItem } from './components/UserMenu';
export { Avatar } from './components/Avatar';
export type { AvatarShape, AvatarSize } from './components/Avatar';
export { CollapseToggle } from './components/CollapseToggle';
export { AppFooter } from './components/AppFooter';
export type { AppFooterLink } from './components/AppFooter';

/* ---------- content and data ---------- */
export { PageHeader } from './components/PageHeader';
export { WorkflowSteps } from './components/WorkflowSteps';
export { SectionHeader } from './components/SectionHeader';
export { Toolbar } from './components/Toolbar';
export { Tabs, tabButtonId } from './components/Tabs';
export type { Tab } from './components/Tabs';
export { Card, CardHeader, CardBody, CardFooter } from './components/Card';
export { StatTile, StatRow } from './components/StatTile';
export type { StatTone } from './components/StatTile';
export { Badge } from './components/Badge';
export type { Tone } from './components/Badge';
export { ListRow } from './components/ListRow';
export { Meter } from './components/Meter';
export { Disclosure } from './components/Disclosure';
export { Select } from './components/Select';
export type { SelectOption, SelectOptionGroup, SelectItem } from './components/Select';
export { SearchSelect } from './components/SearchSelect';
export type {
  SearchSelectOption,
  SearchSelectLoader,
  SearchSelectProps,
} from './components/SearchSelect';
export { Menu } from './components/Menu';
export type { MenuItem } from './components/Menu';
export { ConfirmDialog } from './components/ConfirmDialog';
export { Modal, Drawer } from './components/Overlay';
export type { OverlaySize } from './components/Overlay';
export { useDialogA11y, FOCUSABLE_SELECTOR } from './lib/dialog';
export type { UseDialogA11yOptions, DialogA11y } from './lib/dialog';
export { FilterChip } from './components/FilterChip';
export { FilterBar } from './components/FilterBar';
export type { AppliedFilter } from './components/FilterBar';
export { Notice, TONE_ICONS } from './components/Notice';
export type { NoticeTone } from './components/Notice';
export { ToastProvider, useToast } from './components/Toast';
export type { ToastApi, ToastOptions, ToastPlacement, ToastTone } from './components/Toast';
export { DataTable } from './components/DataTable';
export type { DataTableProps } from './components/DataTable';
export { TableSearch } from './components/TableSearch';
export type { TableSearchProps } from './components/TableSearch';
export { Pager, PAGE_LIMITS } from './components/Pager';
export type { PagerProps } from './components/Pager';
export { BulkBar } from './components/BulkBar';
export type { BulkBarProps } from './components/BulkBar';
export { ColumnPicker } from './components/ColumnPicker';
export type { ColumnPickerProps } from './components/ColumnPicker';
export { ExportMenu, EXPORT_FORMATS } from './components/ExportMenu';
export type { ExportFormat, ExportMenuProps } from './components/ExportMenu';
export { useColumnPreferences, columnPrefsKey } from './lib/column-prefs';
export type { ColumnPreferences } from './lib/column-prefs';
export type {
  CellAlign,
  CellType,
  Column,
  Density,
  Sort,
  SortDirection,
} from './lib/table';
export { firstDirection, nextSort, sortedBy } from './lib/table';
export {
  useListQuery,
  parseListQuery,
  listQueryString,
  serializeSort,
  parseSort,
  clampLimit,
  LIMIT_DEFAULT,
  LIMIT_MAX,
  SEARCH_MIN,
  SEARCH_MAX,
  SORT_FIELDS_MAX,
  FILTER_VALUES_MAX,
} from './lib/list-query';
export type {
  FilterValue,
  ListFilters,
  ListQuery,
  ListQueryHandle,
  PageMeta,
  UseListQueryOptions,
} from './lib/list-query';
export { EmptyState, ErrorState, Skeleton } from './components/States';
export type { ErrorStatus } from './components/States';
export { BarChart } from './components/BarChart';
export type { BarChartDatum, BarChartSeries, BarChartProps } from './components/BarChart';

/* ---------- form primitives ---------- */
export { Button } from './components/Button';
export { IconButton } from './components/IconButton';
export { TextField } from './components/TextField';
export { PasswordField, assessPassword, scorePassword } from './components/PasswordField';
export type { PasswordAssessment } from './components/PasswordField';
export { EmailField, isEmailLike, normalizeEmail } from './components/EmailField';
export {
  PhoneField,
  isPhoneLike,
  nationalMaxLength,
  splitInternational,
  toE164,
} from './components/PhoneField';
export type { PhoneDialCode, PhoneValue } from './components/PhoneField';
export { Checkbox } from './components/Checkbox';
export { FileUpload, formatBytes } from './components/FileUpload';
export type {
  FileUploadItem,
  FileUploadStatus,
  FileRejection,
  FileRejectionReason,
} from './components/FileUpload';

/* ---------- icons ---------- */
export {
  AlertIcon,
  BackIcon,
  BoxIcon,
  CheckIcon,
  EyeIcon,
  EyeOffIcon,
  FacebookIcon,
  GoogleIcon,
  LockIcon,
  MailIcon,
  PhoneIcon,
  ReceiptIcon,
  ScaleIcon,
  ShieldIcon,
  StoreIcon,
  UserIcon,
} from './components/icons';
export {
  ActivityIcon,
  ArrowRightIcon,
  AuditIcon,
  BellIcon,
  BookIcon,
  CalendarIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ChevronUpDownIcon,
  ClockIcon,
  CloseIcon,
  ContrastIcon,
  CustomersIcon,
  DashboardIcon,
  DocumentIcon,
  DownloadIcon,
  ExternalLinkIcon,
  FilterIcon,
  HelpIcon,
  InfoIcon,
  LogoutIcon,
  MenuIcon,
  MessageIcon,
  MonitorIcon,
  MoonIcon,
  MoreIcon,
  PanelCollapseIcon,
  PaymentsIcon,
  RefreshIcon,
  ReportsIcon,
  RolesIcon,
  SearchIcon,
  SettingsIcon,
  StockIcon,
  SunIcon,
  TaxIcon,
  TrendUpIcon,
  UploadIcon,
  WalletIcon,
  WarnTriangleIcon,
  XCircleIcon,
} from './components/icons-console';
export {
  ChevronLeftIcon,
  ChevronUpIcon,
  ChevronsLeftIcon,
  ChevronsRightIcon,
  ColumnsIcon,
  CopyIcon,
  DensityIcon,
  DragHandleIcon,
  EditIcon,
  MoreVerticalIcon,
  PinIcon,
  PlusIcon,
  TrashIcon,
} from './components/icons-table';
