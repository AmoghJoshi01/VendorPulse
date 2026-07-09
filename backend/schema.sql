-- VendorPulse Core Database Schema (PostgreSQL)
-- Implements the tables, relationships, and optimization indexes defined in backend/dbflow.md

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =========================================================================
-- 1. TENANT ADMINISTRATION
-- =========================================================================

CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    clerk_org_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    cost_of_capital DECIMAL(5,2) DEFAULT 6.00,
    base_currency VARCHAR(3) DEFAULT 'USD',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    clerk_user_id VARCHAR(255) UNIQUE NOT NULL,
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    role VARCHAR(50) NOT NULL, -- 'ADMIN', 'FINANCE_MANAGER', 'APPROVER', 'SUPPLIER_USER'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 2. CORE FINANCIAL LEDGER ENTITIES
-- =========================================================================

CREATE TABLE IF NOT EXISTS vendors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    payment_terms VARCHAR(100) DEFAULT 'Net 30',
    default_discount_pct DECIMAL(5,4) DEFAULT 0.0000,
    discount_days INT DEFAULT 0,
    net_days INT DEFAULT 30,
    bank_name VARCHAR(255),
    bank_routing_number VARCHAR(100),
    bank_account_number VARCHAR(100),
    status VARCHAR(50) DEFAULT 'ACTIVE', -- 'ACTIVE', 'PENDING_VERIFICATION', 'SUSPENDED'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    vendor_id UUID REFERENCES vendors(id) ON DELETE SET NULL,
    po_number VARCHAR(100) UNIQUE NOT NULL,
    issue_date DATE NOT NULL,
    total_amount DECIMAL(15,2) NOT NULL,
    department VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'OPEN', -- 'OPEN', 'PARTIALLY_FILLED', 'CLOSED'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_order_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    purchase_order_id UUID REFERENCES purchase_orders(id) ON DELETE CASCADE,
    item_description TEXT NOT NULL,
    quantity DECIMAL(12,4) NOT NULL,
    unit_price DECIMAL(15,2) NOT NULL,
    total_price DECIMAL(15,2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS goods_receipts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    purchase_order_id UUID REFERENCES purchase_orders(id) ON DELETE SET NULL,
    receipt_number VARCHAR(100) NOT NULL,
    received_date DATE NOT NULL,
    status VARCHAR(50) DEFAULT 'RECEIVED',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS goods_receipt_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    goods_receipt_id UUID REFERENCES goods_receipts(id) ON DELETE CASCADE,
    purchase_order_item_id UUID REFERENCES purchase_order_items(id) ON DELETE SET NULL,
    quantity_received DECIMAL(12,4) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 3. INVOICE MANAGEMENT & ANALYTICS
-- =========================================================================

CREATE TABLE IF NOT EXISTS invoices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    vendor_id UUID REFERENCES vendors(id) ON DELETE SET NULL,
    purchase_order_id UUID REFERENCES purchase_orders(id) ON DELETE SET NULL,
    invoice_number VARCHAR(100) NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    tax_amount DECIMAL(15,2) DEFAULT 0.00,
    issue_date DATE NOT NULL,
    due_date DATE NOT NULL,
    payment_terms VARCHAR(100) DEFAULT 'Net 30',
    file_url VARCHAR(512),
    ocr_raw_json JSONB,
    status VARCHAR(50) DEFAULT 'PENDING_MATCH', -- 'PENDING_MATCH', 'MATCHED', 'EXCEPTION', 'IN_APPROVAL', 'APPROVED', 'PAID', 'REJECTED'
    matching_result VARCHAR(50), -- 'THREE_WAY_OK', 'PRICE_MISMATCH', 'QTY_MISMATCH', 'NO_PO_FOUND'
    early_payment_status VARCHAR(50) DEFAULT 'CALCULATED', -- 'CALCULATED', 'OPTIMAL_PAID_EARLY', 'OPTIMAL_PAID_NET', 'SKIPPED'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS invoice_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    invoice_id UUID REFERENCES invoices(id) ON DELETE CASCADE,
    purchase_order_item_id UUID REFERENCES purchase_order_items(id) ON DELETE SET NULL,
    item_description TEXT NOT NULL,
    quantity DECIMAL(12,4) NOT NULL,
    unit_price DECIMAL(15,2) NOT NULL,
    total_price DECIMAL(15,2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS exceptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    invoice_id UUID REFERENCES invoices(id) ON DELETE CASCADE,
    exception_type VARCHAR(100) NOT NULL, -- 'PRICE_VARIANCE', 'QUANTITY_VARIANCE', 'MISSING_GR', 'UNKNOWN_VENDOR'
    description TEXT,
    confidence_score DECIMAL(5,2),
    predicted_approver_id UUID REFERENCES users(id) ON DELETE SET NULL,
    assigned_approver_id UUID REFERENCES users(id) ON DELETE SET NULL,
    status VARCHAR(50) DEFAULT 'OPEN', -- 'OPEN', 'RESOLVED', 'FORWARDED'
    resolved_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    resolution_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- =========================================================================
-- 4. WORKFLOW ROUTING & MACHINE LEARNING FEEDBACK
-- =========================================================================

CREATE TABLE IF NOT EXISTS approval_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    department VARCHAR(100),
    min_amount DECIMAL(15,2) DEFAULT 0.00,
    max_amount DECIMAL(15,2),
    approver_id UUID REFERENCES users(id) ON DELETE CASCADE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS approval_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    invoice_id UUID REFERENCES invoices(id) ON DELETE CASCADE,
    approver_id UUID REFERENCES users(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL, -- 'APPROVED', 'REJECTED', 'REROUTED'
    comments TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS exception_routing_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    exception_type VARCHAR(100) NOT NULL,
    vendor_id UUID REFERENCES vendors(id) ON DELETE SET NULL,
    amount DECIMAL(15,2) NOT NULL,
    variance_amount DECIMAL(15,2) DEFAULT 0.00,
    department VARCHAR(100),
    final_approver_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 5. PERFORMANCE OPTIMIZATION INDEXES
-- =========================================================================

-- Foreign Key Indexes for Multi-Tenancy Isolation Query Performance
CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id);
CREATE INDEX IF NOT EXISTS idx_vendors_org ON vendors(organization_id);
CREATE INDEX IF NOT EXISTS idx_pos_org ON purchase_orders(organization_id);
CREATE INDEX IF NOT EXISTS idx_invoices_org ON invoices(organization_id);

-- Indexes for Item Tables to optimize join operations
CREATE INDEX IF NOT EXISTS idx_po_items_po_id ON purchase_order_items(purchase_order_id);
CREATE INDEX IF NOT EXISTS idx_gr_items_gr_id ON goods_receipt_items(goods_receipt_id);
CREATE INDEX IF NOT EXISTS idx_gr_items_po_item_id ON goods_receipt_items(purchase_order_item_id);
CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice_id ON invoice_items(invoice_id);
CREATE INDEX IF NOT EXISTS idx_invoice_items_po_item_id ON invoice_items(purchase_order_item_id);

-- GIN Index on Invoice OCR Metadata JSONB for deep querying of parsed items
CREATE INDEX IF NOT EXISTS idx_invoices_ocr_raw_gin ON invoices USING gin (ocr_raw_json);

-- Tenant-scoped unique index to prevent duplicate invoice numbers from a vendor
CREATE UNIQUE INDEX IF NOT EXISTS idx_invoices_num_vendor ON invoices(organization_id, vendor_id, invoice_number);

-- Index for exception routing queues
CREATE INDEX IF NOT EXISTS idx_exceptions_status ON exceptions(status, assigned_approver_id);
