import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Generator

from sqlalchemy import (
    create_engine, Column, String, Integer, Numeric, Boolean, Date, DateTime, ForeignKey, Text, JSON, UniqueConstraint, TypeDecorator, CHAR
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from sqlalchemy.dialects.postgresql import UUID, JSONB

# Declarative base
Base = declarative_base()

# --- DATABASE CONFIGURATION ---
# Reads DATABASE_URL from environment; defaults to a local SQLite database for out-of-the-box running
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///vendorpulse.db")

# Adjust connection URL for compatibility with sqlite/postgres dialects
if DATABASE_URL.startswith("postgres://"):
    # SQLAlchemy requires postgresql:// instead of postgres://
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create Database Engine
# check_same_thread is only used/needed for SQLite
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

# Create Session Local factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Custom TypeDecorator for database-agnostic UUIDs
class GUID(TypeDecorator):
    """Platform-independent GUID type.
    Uses PostgreSQL's UUID type, otherwise uses CHAR(36), storing as stringified values.
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == 'postgresql':
            if isinstance(value, str):
                return uuid.UUID(value)
            return value
        else:
            return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if dialect.name == 'postgresql':
            return value
        else:
            return uuid.UUID(value)

# Dialect-agnostic UUID column helper
def get_uuid_type():
    """Returns the GUID TypeDecorator for database independence."""
    return GUID

# Dialect-agnostic JSON column helper
def get_json_type():
    """Returns PG JSONB type or standard JSON fallback for SQLite compatibility."""
    return JSONB if engine.dialect.name == "postgresql" else JSON


# =========================================================================
# ORM MODEL DEFINITIONS
# =========================================================================

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(get_uuid_type(), primary_key=True, default=uuid.uuid4)
    clerk_org_id = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    cost_of_capital = Column(Numeric(5, 2), default=Decimal("6.00"))
    cash_balance = Column(Numeric(15, 2), default=Decimal("150000.00"))
    minimum_liquidity_threshold = Column(Numeric(15, 2), default=Decimal("25000.00"))
    base_currency = Column(String(3), default="USD")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    vendors = relationship("Vendor", back_populates="organization", cascade="all, delete-orphan")
    purchase_orders = relationship("PurchaseOrder", back_populates="organization", cascade="all, delete-orphan")
    goods_receipts = relationship("GoodsReceipt", back_populates="organization", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="organization", cascade="all, delete-orphan")
    approval_rules = relationship("ApprovalRule", back_populates="organization", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(get_uuid_type(), primary_key=True, default=uuid.uuid4)
    clerk_user_id = Column(String(255), unique=True, nullable=False)
    organization_id = Column(get_uuid_type(), ForeignKey("organizations.id", ondelete="CASCADE"))
    email = Column(String(255), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    role = Column(String(50), nullable=False)  # 'ADMIN', 'FINANCE_MANAGER', 'APPROVER', 'SUPPLIER_USER'
    vendor_id = Column(get_uuid_type(), ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(50), default="APPROVED")  # 'PENDING', 'APPROVED', 'REJECTED'
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="users")
    vendor = relationship("Vendor")


class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(get_uuid_type(), primary_key=True, default=uuid.uuid4)
    organization_id = Column(get_uuid_type(), ForeignKey("organizations.id", ondelete="CASCADE"))
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    payment_terms = Column(String(100), default="Net 30")
    default_discount_pct = Column(Numeric(5, 4), default=Decimal("0.0000"))
    discount_days = Column(Integer, default=0)
    net_days = Column(Integer, default=30)
    bank_name = Column(String(255))
    bank_routing_number = Column(String(100))
    bank_account_number = Column(String(100))
    status = Column(String(50), default="ACTIVE")  # 'ACTIVE', 'PENDING_VERIFICATION', 'SUSPENDED'
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="vendors")
    invoices = relationship("Invoice", back_populates="vendor")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(get_uuid_type(), primary_key=True, default=uuid.uuid4)
    organization_id = Column(get_uuid_type(), ForeignKey("organizations.id", ondelete="CASCADE"))
    vendor_id = Column(get_uuid_type(), ForeignKey("vendors.id", ondelete="SET NULL"))
    po_number = Column(String(100), unique=True, nullable=False)
    issue_date = Column(Date, nullable=False)
    total_amount = Column(Numeric(15, 2), nullable=False)
    department = Column(String(100), nullable=False)
    status = Column(String(50), default="OPEN")  # 'OPEN', 'PARTIALLY_FILLED', 'CLOSED'
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="purchase_orders")
    vendor = relationship("Vendor")
    goods_receipts = relationship("GoodsReceipt", back_populates="purchase_order")
    invoices = relationship("Invoice", back_populates="purchase_order")
    items = relationship("PurchaseOrderItem", back_populates="purchase_order", cascade="all, delete-orphan")


class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"

    id = Column(get_uuid_type(), primary_key=True, default=uuid.uuid4)
    organization_id = Column(get_uuid_type(), ForeignKey("organizations.id", ondelete="CASCADE"))
    purchase_order_id = Column(get_uuid_type(), ForeignKey("purchase_orders.id", ondelete="SET NULL"))
    receipt_number = Column(String(100), nullable=False)
    received_date = Column(Date, nullable=False)
    status = Column(String(50), default="RECEIVED")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="goods_receipts")
    purchase_order = relationship("PurchaseOrder", back_populates="goods_receipts")
    items = relationship("GoodsReceiptItem", back_populates="goods_receipt", cascade="all, delete-orphan")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(get_uuid_type(), primary_key=True, default=uuid.uuid4)
    organization_id = Column(get_uuid_type(), ForeignKey("organizations.id", ondelete="CASCADE"))
    vendor_id = Column(get_uuid_type(), ForeignKey("vendors.id", ondelete="SET NULL"))
    purchase_order_id = Column(get_uuid_type(), ForeignKey("purchase_orders.id", ondelete="SET NULL"))
    invoice_number = Column(String(100), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    tax_amount = Column(Numeric(15, 2), default=Decimal("0.00"))
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    payment_terms = Column(String(100), default="Net 30")
    file_url = Column(String(512))
    ocr_raw_json = Column(get_json_type())
    status = Column(String(50), default="PENDING_MATCH")  # 'PENDING_MATCH', 'MATCHED', 'EXCEPTION', 'IN_APPROVAL'
    matching_result = Column(String(50))  # 'THREE_WAY_OK', 'PRICE_MISMATCH', etc.
    early_payment_status = Column(String(50), default="CALCULATED")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique Constraint to prevent double-uploading an invoice number for a vendor
    __table_args__ = (
        UniqueConstraint("organization_id", "vendor_id", "invoice_number", name="idx_invoices_num_vendor_uc"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="invoices")
    vendor = relationship("Vendor", back_populates="invoices")
    purchase_order = relationship("PurchaseOrder", back_populates="invoices")
    exceptions = relationship("InvoiceException", back_populates="invoice", cascade="all, delete-orphan")
    approval_history = relationship("ApprovalHistory", back_populates="invoice", cascade="all, delete-orphan")
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")


class InvoiceException(Base):
    __tablename__ = "exceptions"

    id = Column(get_uuid_type(), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(get_uuid_type(), ForeignKey("invoices.id", ondelete="CASCADE"))
    exception_type = Column(String(100), nullable=False)  # 'PRICE_VARIANCE', 'QUANTITY_VARIANCE', etc.
    description = Column(Text)
    confidence_score = Column(Numeric(5, 2))
    predicted_approver_id = Column(get_uuid_type(), ForeignKey("users.id", ondelete="SET NULL"))
    assigned_approver_id = Column(get_uuid_type(), ForeignKey("users.id", ondelete="SET NULL"))
    status = Column(String(50), default="OPEN")  # 'OPEN', 'RESOLVED', 'FORWARDED'
    resolved_by_id = Column(get_uuid_type(), ForeignKey("users.id", ondelete="SET NULL"))
    resolution_notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    resolved_at = Column(DateTime(timezone=True))

    # Relationships
    invoice = relationship("Invoice", back_populates="exceptions")


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id = Column(get_uuid_type(), primary_key=True, default=uuid.uuid4)
    purchase_order_id = Column(get_uuid_type(), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False)
    item_description = Column(Text, nullable=False)
    quantity = Column(Numeric(12, 4), nullable=False)
    unit_price = Column(Numeric(15, 2), nullable=False)
    total_price = Column(Numeric(15, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    purchase_order = relationship("PurchaseOrder", back_populates="items")


class GoodsReceiptItem(Base):
    __tablename__ = "goods_receipt_items"

    id = Column(get_uuid_type(), primary_key=True, default=uuid.uuid4)
    goods_receipt_id = Column(get_uuid_type(), ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False)
    purchase_order_item_id = Column(get_uuid_type(), ForeignKey("purchase_order_items.id", ondelete="SET NULL"))
    quantity_received = Column(Numeric(12, 4), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    goods_receipt = relationship("GoodsReceipt", back_populates="items")
    purchase_order_item = relationship("PurchaseOrderItem")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(get_uuid_type(), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(get_uuid_type(), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    purchase_order_item_id = Column(get_uuid_type(), ForeignKey("purchase_order_items.id", ondelete="SET NULL"))
    item_description = Column(Text, nullable=False)
    quantity = Column(Numeric(12, 4), nullable=False)
    unit_price = Column(Numeric(15, 2), nullable=False)
    total_price = Column(Numeric(15, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    invoice = relationship("Invoice", back_populates="items")
    purchase_order_item = relationship("PurchaseOrderItem")


class ApprovalRule(Base):
    __tablename__ = "approval_rules"

    id = Column(get_uuid_type(), primary_key=True, default=uuid.uuid4)
    organization_id = Column(get_uuid_type(), ForeignKey("organizations.id", ondelete="CASCADE"))
    department = Column(String(100))
    min_amount = Column(Numeric(15, 2), default=Decimal("0.00"))
    max_amount = Column(Numeric(15, 2))
    approver_id = Column(get_uuid_type(), ForeignKey("users.id", ondelete="CASCADE"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="approval_rules")


class ApprovalHistory(Base):
    __tablename__ = "approval_history"

    id = Column(get_uuid_type(), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(get_uuid_type(), ForeignKey("invoices.id", ondelete="CASCADE"))
    approver_id = Column(get_uuid_type(), ForeignKey("users.id", ondelete="CASCADE"))
    action = Column(String(50), nullable=False)  # 'APPROVED', 'REJECTED', 'REROUTED'
    comments = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    invoice = relationship("Invoice", back_populates="approval_history")


class ExceptionRoutingHistory(Base):
    __tablename__ = "exception_routing_history"

    id = Column(get_uuid_type(), primary_key=True, default=uuid.uuid4)
    organization_id = Column(get_uuid_type(), ForeignKey("organizations.id", ondelete="CASCADE"))
    exception_type = Column(String(100), nullable=False)
    vendor_id = Column(get_uuid_type(), ForeignKey("vendors.id", ondelete="SET NULL"))
    amount = Column(Numeric(15, 2), nullable=False)
    variance_amount = Column(Numeric(15, 2), default=Decimal("0.00"))
    department = Column(String(100))
    final_approver_id = Column(get_uuid_type(), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


# =========================================================================
# HELPER ACTIONS: DB INIT & SEEDING
# =========================================================================

def get_db() -> Generator[Session, None, None]:
    """FastAPI Dependency to get database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(seed: bool = True):
    """Initializes schema tables and seeds baseline demo data if database is empty."""
    Base.metadata.create_all(bind=engine)
    
    if seed:
        db = SessionLocal()
        try:
            # Check if organization already exists to prevent duplicate seeding
            if db.query(Organization).first() is not None:
                return
                
            print("[SEED] Seeding database with baseline demo data...")
            
            # 1. Create Organization
            org = Organization(
                clerk_org_id="org_2tJ8XWn6qE",
                name="Acme Corporation",
                cost_of_capital=Decimal("6.00"),
                cash_balance=Decimal("150000.00"),
                minimum_liquidity_threshold=Decimal("25000.00"),
                base_currency="USD"
            )
            db.add(org)
            db.flush() # Populate org.id
            
            # 2. Create Users
            finance_mgr = User(
                clerk_user_id="user_finance_mgr_1",
                organization_id=org.id,
                email="treasury@acme.com",
                first_name="Jane",
                last_name="Doe",
                role="FINANCE_MANAGER"
            )
            approver = User(
                clerk_user_id="user_approver_1",
                organization_id=org.id,
                email="ops.lead@acme.com",
                first_name="Robert",
                last_name="Smith",
                role="APPROVER"
            )
            level1_mgr = User(
                clerk_user_id="user_level1_mgr",
                organization_id=org.id,
                email="level1@abcenterprises.com",
                first_name="Level 1",
                last_name="Manager",
                role="FINANCE_MANAGER"
            )
            level2_mgr = User(
                clerk_user_id="user_level2_mgr",
                organization_id=org.id,
                email="level2@abcenterprises.com",
                first_name="Level 2",
                last_name="Manager",
                role="FINANCE_MANAGER"
            )
            level3_mgr = User(
                clerk_user_id="user_level3_mgr",
                organization_id=org.id,
                email="level3@abcenterprises.com",
                first_name="Level 3",
                last_name="Manager",
                role="FINANCE_MANAGER"
            )
            db.add_all([finance_mgr, approver, level1_mgr, level2_mgr, level3_mgr])
            db.flush()
            
            # 3. Create Vendors
            v_acme = Vendor(
                organization_id=org.id,
                name="Acme Industrial Supplies Ltd.",
                email="ap@acmeindustrial.com",
                payment_terms="2/10 Net 30",
                default_discount_pct=Decimal("0.0200"),
                discount_days=10,
                net_days=30,
                bank_name="Chase Bank",
                bank_routing_number="021000021",
                bank_account_number="1234567829",
                status="ACTIVE"
            )
            v_globex = Vendor(
                organization_id=org.id,
                name="Globex Logistics",
                email="billing@globex.com",
                payment_terms="Net 30",
                default_discount_pct=Decimal("0.0000"),
                discount_days=0,
                net_days=30,
                bank_name="Bank of America",
                bank_routing_number="026009593",
                bank_account_number="9876543210",
                status="ACTIVE"
            )
            v_initech = Vendor(
                organization_id=org.id,
                name="Initech IT Solutions",
                email="accounts@initech.com",
                payment_terms="1/15 Net 45",
                default_discount_pct=Decimal("0.0100"),
                discount_days=15,
                net_days=45,
                bank_name="Wells Fargo",
                bank_routing_number="121000248",
                bank_account_number="5678901234",
                status="ACTIVE"
            )
            v_olivia = Vendor(
                organization_id=org.id,
                name="Olivia Wilson Consulting",
                email="olivia@wilsonconsulting.co",
                payment_terms="3/10 Net 30",
                default_discount_pct=Decimal("0.0300"),
                discount_days=10,
                net_days=30,
                bank_name="CitiBank",
                bank_routing_number="021000089",
                bank_account_number="3456789012",
                status="ACTIVE"
            )
            db.add_all([v_acme, v_globex, v_initech, v_olivia])
            db.flush()

            # 3b. Create Supplier Users for testing
            supplier_acme = User(
                clerk_user_id="user_supplier_acme",
                organization_id=org.id,
                email="ap@acmeindustrial.com",
                first_name="Alice",
                last_name="Acme",
                role="SUPPLIER_USER",
                vendor_id=v_acme.id
            )
            supplier_olivia = User(
                clerk_user_id="user_supplier_olivia",
                organization_id=org.id,
                email="olivia@wilsonconsulting.co",
                first_name="Olivia",
                last_name="Wilson",
                role="SUPPLIER_USER",
                vendor_id=v_olivia.id
            )
            db.add_all([supplier_acme, supplier_olivia])
            db.flush()

            # 4. Create Purchase Orders & Items
            po_acme = PurchaseOrder(
                organization_id=org.id,
                vendor_id=v_acme.id,
                po_number="PO-99541",
                issue_date=date(2026, 6, 15),
                total_amount=Decimal("755.00"),
                department="Operations",
                status="OPEN"
            )
            po_globex = PurchaseOrder(
                organization_id=org.id,
                vendor_id=v_globex.id,
                po_number="PO-99542",
                issue_date=date(2026, 6, 20),
                total_amount=Decimal("1200.00"),
                department="Supply Chain",
                status="OPEN"
            )
            po_initech = PurchaseOrder(
                organization_id=org.id,
                vendor_id=v_initech.id,
                po_number="PO-99543",
                issue_date=date(2026, 6, 25),
                total_amount=Decimal("5000.00"),
                department="Information Technology",
                status="OPEN"
            )
            db.add_all([po_acme, po_globex, po_initech])
            db.flush()

            # PO Items
            po_item_acme1 = PurchaseOrderItem(
                purchase_order_id=po_acme.id,
                item_description="Industrial Safety Gloves",
                quantity=Decimal("10.0"),
                unit_price=Decimal("25.50"),
                total_price=Decimal("255.00")
            )
            po_item_acme2 = PurchaseOrderItem(
                purchase_order_id=po_acme.id,
                item_description="Heavy Duty Steel Boots",
                quantity=Decimal("5.0"),
                unit_price=Decimal("100.00"),
                total_price=Decimal("500.00")
            )
            po_item_globex = PurchaseOrderItem(
                purchase_order_id=po_globex.id,
                item_description="Freight & Warehousing Services",
                quantity=Decimal("1.0"),
                unit_price=Decimal("1200.00"),
                total_price=Decimal("1200.00")
            )
            po_item_initech = PurchaseOrderItem(
                purchase_order_id=po_initech.id,
                item_description="Enterprise Software Licensing",
                quantity=Decimal("1.0"),
                unit_price=Decimal("5000.00"),
                total_price=Decimal("5000.00")
            )
            db.add_all([po_item_acme1, po_item_acme2, po_item_globex, po_item_initech])
            db.flush()

            # 5. Create Goods Receipts & Items
            gr_acme = GoodsReceipt(
                organization_id=org.id,
                purchase_order_id=po_acme.id,
                receipt_number="GR-88421",
                received_date=date(2026, 6, 18),
                status="RECEIVED"
            )
            gr_globex = GoodsReceipt(
                organization_id=org.id,
                purchase_order_id=po_globex.id,
                receipt_number="GR-88422",
                received_date=date(2026, 6, 22),
                status="RECEIVED"
            )
            gr_initech = GoodsReceipt(
                organization_id=org.id,
                purchase_order_id=po_initech.id,
                receipt_number="GR-88423",
                received_date=date(2026, 6, 28),
                status="RECEIVED"
            )
            db.add_all([gr_acme, gr_globex, gr_initech])
            db.flush()

            gr_item_acme1 = GoodsReceiptItem(
                goods_receipt_id=gr_acme.id,
                purchase_order_item_id=po_item_acme1.id,
                quantity_received=Decimal("10.0")
            )
            gr_item_acme2 = GoodsReceiptItem(
                goods_receipt_id=gr_acme.id,
                purchase_order_item_id=po_item_acme2.id,
                quantity_received=Decimal("5.0")
            )
            gr_item_globex = GoodsReceiptItem(
                goods_receipt_id=gr_globex.id,
                purchase_order_item_id=po_item_globex.id,
                quantity_received=Decimal("1.0")
            )
            gr_item_initech = GoodsReceiptItem(
                goods_receipt_id=gr_initech.id,
                purchase_order_item_id=po_item_initech.id,
                quantity_received=Decimal("1.0")
            )
            db.add_all([gr_item_acme1, gr_item_acme2, gr_item_globex, gr_item_initech])
            db.flush()

            # 6. Create Default Invoices
            inv1 = Invoice(
                organization_id=org.id,
                vendor_id=v_acme.id,
                purchase_order_id=po_acme.id,
                invoice_number="INV-2026-8942",
                amount=Decimal("755.00"),
                tax_amount=Decimal("0.00"),
                issue_date=date(2026, 7, 1),
                due_date=date(2026, 7, 31),
                payment_terms="2/10 Net 30",
                file_url="s3://vendorpulse-invoices/acme_industrial_inv_8942.pdf",
                status="APPROVED",
                matching_result="THREE_WAY_OK",
                early_payment_status="OPTIMAL_PAID_EARLY"
            )
            inv2 = Invoice(
                organization_id=org.id,
                vendor_id=v_globex.id,
                purchase_order_id=po_globex.id,
                invoice_number="INV-2026-9051",
                amount=Decimal("1200.00"),
                tax_amount=Decimal("0.00"),
                issue_date=date(2026, 7, 5),
                due_date=date(2026, 8, 4),
                payment_terms="Net 30",
                file_url="s3://vendorpulse-invoices/globex_freight_inv_9051.jpeg",
                status="PENDING_MATCH",
                matching_result="THREE_WAY_OK",
                early_payment_status="CALCULATED"
            )
            inv3 = Invoice(
                organization_id=org.id,
                vendor_id=v_initech.id,
                purchase_order_id=po_initech.id,
                invoice_number="INV-2026-9113",
                amount=Decimal("5400.00"),
                tax_amount=Decimal("0.00"),
                issue_date=date(2026, 7, 8),
                due_date=date(2026, 8, 22),
                payment_terms="1/15 Net 45",
                file_url="s3://vendorpulse-invoices/initech_software_inv_9113.pdf",
                status="EXCEPTION",
                matching_result="PRICE_MISMATCH",
                early_payment_status="CALCULATED"
            )
            db.add_all([inv1, inv2, inv3])
            db.flush()

            # Invoice Items
            inv1_item1 = InvoiceItem(
                invoice_id=inv1.id,
                purchase_order_item_id=po_item_acme1.id,
                item_description="Industrial Safety Gloves",
                quantity=Decimal("10.0"),
                unit_price=Decimal("25.50"),
                total_price=Decimal("255.00")
            )
            inv1_item2 = InvoiceItem(
                invoice_id=inv1.id,
                purchase_order_item_id=po_item_acme2.id,
                item_description="Heavy Duty Steel Boots",
                quantity=Decimal("5.0"),
                unit_price=Decimal("100.00"),
                total_price=Decimal("500.00")
            )
            inv2_item = InvoiceItem(
                invoice_id=inv2.id,
                purchase_order_item_id=po_item_globex.id,
                item_description="Freight & Warehousing Services",
                quantity=Decimal("1.0"),
                unit_price=Decimal("1200.00"),
                total_price=Decimal("1200.00")
            )
            inv3_item = InvoiceItem(
                invoice_id=inv3.id,
                purchase_order_item_id=po_item_initech.id,
                item_description="Enterprise Software Licensing",
                quantity=Decimal("1.0"),
                unit_price=Decimal("5400.00"),
                total_price=Decimal("5400.00")
            )
            db.add_all([inv1_item1, inv1_item2, inv2_item, inv3_item])
            db.flush()

            # Create Exception for Initech
            exc = InvoiceException(
                invoice_id=inv3.id,
                exception_type="PRICE_VARIANCE",
                description="Invoice total ($5,400.00) exceeds PO-99543 total ($5,000.00) by $400.00 (8.0% variance, limit is 0.5%).",
                confidence_score=Decimal("92.40"),
                predicted_approver_id=approver.id,
                assigned_approver_id=approver.id,
                status="OPEN"
            )
            db.add(exc)

            # 7. Create Approval Rule (Approvals under $1000 routed to Robert Smith)
            rule = ApprovalRule(
                organization_id=org.id,
                department="Operations",
                min_amount=Decimal("0.00"),
                max_amount=Decimal("1000.00"),
                approver_id=approver.id,
                is_active=True
            )
            db.add(rule)
            
            # Commit the transaction
            db.commit()
            print("[SEED] Database seeding complete.")
            
        except BaseException as e:
            db.rollback()
            print(f"[SEED] Error seeding database: {e}")
        finally:
            db.close()


if __name__ == "__main__":
    # If run directly, initialize and seed database
    init_db()
