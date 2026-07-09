export interface Vendor {
  id: string;
  name: string;
  email: string;
  payment_terms: string;
  default_discount_pct: number;
  discount_days: number;
  net_days: number;
  bank_name: string;
  bank_routing_number: string;
  bank_account_number: string;
  status: string;
}

export interface POItem {
  description: string;
  quantity: number;
  unit_price: number;
  total: number;
}

export interface PurchaseOrder {
  id: string;
  po_number: string;
  vendor_name: string;
  issue_date: string;
  total_amount: number;
  department: string;
  status: string;
  items: POItem[];
}

export interface InvoiceException {
  exception_type: 'MISSING_PO' | 'PRICE_VARIANCE' | 'QUANTITY_VARIANCE' | 'MISSING_GR';
  description: string;
  confidence_score: number;
  predicted_approver: string;
  status: 'OPEN' | 'RESOLVED';
  resolution_action?: string;
  comments?: string;
}

export interface Invoice {
  id: string;
  vendor_name: string;
  invoice_number: string;
  invoice_amount: number;
  purchase_order_number: string;
  payment_terms: string;
  early_payment_discount_percentage: number;
  discount_period_days: number;
  net_period_days: number;
  status: 'PENDING_MATCH' | 'MATCHED' | 'EXCEPTION' | 'APPROVED' | 'PAID' | 'REJECTED';
  matching_result: 'THREE_WAY_OK' | 'PRICE_MISMATCH' | 'QTY_MISMATCH' | 'NO_PO_FOUND';
  early_payment_status: 'CALCULATED' | 'OPTIMAL_PAID_EARLY' | 'OPTIMAL_PAID_NET' | 'SKIPPED';
  implied_annual_yield: number;
  cash_savings: number;
  created_at: string;
  due_date: string;
  early_pay_date: string | null;
  exception?: InvoiceException;
  is_live_ai?: boolean;
}

export interface Settings {
  cost_of_capital: number;
  minimum_liquidity_threshold: number;
  cash_balance: number;
}

export interface ForecastData {
  categories: string[];
  early_payment_schedule: number[];
  net_payment_schedule: number[];
}

export interface Analytics {
  total_ap: number;
  realized_savings: number;
  potential_savings: number;
  dpo: number;
  cash_balance: number;
  cost_of_capital: number;
  forecast: ForecastData;
}
