export interface FirmMembership {
  firm: string;
  firm_name: string;
  firm_type: "Accounting Firm" | "Independent Accountant";
  firm_role: "Firm Admin" | "Accountant" | "Reviewer" | "Staff";
  modules: string[];
}

export interface PortalClient {
  client: string;
  business_name: string;
  contact_role: string;
  can_approve: number;
}

export interface Session {
  user: string | null;
  full_name?: string;
  csrf_token?: string;
  is_platform_admin?: boolean;
  firms?: FirmMembership[];
  portal_clients?: PortalClient[];
  allow_signup: boolean;
}

export interface TeamMember {
  name?: string;
  user: string;
  full_name?: string;
  role?: string;
  assignment_role?: string;
  status?: string;
}

export interface ClientRow {
  name: string;
  business_name: string;
  kra_pin?: string;
  business_type?: string;
  industry?: string;
  status: string;
  provisioning_status: string;
  currency: string;
  last_activity?: string;
  stat_unreconciled?: number;
  stat_drafts?: number;
  stat_overdue_invoices?: number;
  stat_last_posting_date?: string;
  stat_cash_and_bank?: number;
  firm: string;
  access_role: string;
  access_level: number;
  team: TeamMember[];
  open_tasks: number;
  modules: string[];
}

export interface ClientDetail extends Omit<ClientRow, "team" | "open_tasks"> {
  legal_name?: string;
  registration_number?: string;
  vat_registered?: number;
  email?: string;
  phone?: string;
  address?: string;
  fiscal_year_start: string;
  chart_of_accounts: string;
  company_name?: string;
  provisioning_error?: string;
  stat_receivables?: number;
  stat_payables?: number;
  engagement: { name: string; start_date: string; monthly_retainer: number; services: string[] };
  team: TeamMember[];
  portal_users: (TeamMember & { contact_role: string; can_approve: number })[];
  onboarding_checklist: { idx: number; item: string; done: number; done_by?: string; done_on?: string }[];
  other_firms: number;
}

export interface Task {
  name: string;
  title: string;
  client: string;
  client_name?: string;
  firm: string;
  task_type?: string;
  period?: string;
  status: string;
  priority: string;
  due_date?: string;
  assigned_to?: string;
  assigned_to_name?: string;
  reviewer?: string;
  reviewer_name?: string;
  overdue?: boolean;
  description?: string;
}

export interface MonthlyReport {
  name: string;
  client: string;
  client_name?: string;
  firm: string;
  period: string;
  from_date: string;
  to_date: string;
  status: string;
  prepared_by?: string;
  prepared_by_name?: string;
  reviewed_by?: string;
  reviewed_by_name?: string;
  published_on?: string;
  currency?: string;
  total_income: number;
  total_expense: number;
  net_profit: number;
  snapshot_taken_on?: string;
  accountant_notes?: string;
  review_notes?: string;
  client_acknowledged_by?: string;
  client_acknowledged_on?: string;
  trial_balance?: ReportResult;
  profit_and_loss?: ReportResult;
  balance_sheet?: ReportResult;
}

export interface ReportColumn {
  fieldname: string;
  label: string;
  fieldtype: string;
}

export interface ReportResult {
  report: string;
  columns: ReportColumn[];
  rows: Record<string, unknown>[];
}

export interface Account {
  name: string;
  account_name: string;
  account_number?: string;
  parent_account?: string;
  root_type: string;
  account_type?: string;
  is_group?: number;
  balance?: number;
}

export interface DocSummary {
  doctype: string;
  name: string;
  docstatus: number;
  status: string;
  idempotent_replay?: boolean;
  [key: string]: unknown;
}
