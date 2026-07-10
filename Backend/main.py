import os
import re
import json
import uuid
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any

def clean_numeric_value(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    # If it is a string, remove currency symbols, commas, percent signs, and spaces
    val_str = str(val).strip()
    try:
        # Regex to strip everything except digits, dots, and minus signs
        cleaned = re.sub(r"[^\d\.-]", "", val_str)
        return float(cleaned) if cleaned else 0.0
    except (ValueError, TypeError):
        return 0.0

from fastapi import FastAPI, Depends, File, UploadFile, Form, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

# Local imports
from database import (
    engine, SessionLocal, get_db, init_db,
    Organization, User, Vendor, PurchaseOrder, GoodsReceipt,
    Invoice, InvoiceException, ApprovalRule, ApprovalHistory, ExceptionRoutingHistory,
    PurchaseOrderItem, GoodsReceiptItem, InvoiceItem
)
from auth import get_current_user

def get_approver_for_amount(amount: float, org_id: str, db: Session) -> User:
    if amount <= 50000:
        name = "Level 1"
    elif amount <= 250000:
        name = "Level 2"
    else:
        name = "Level 3"
        
    mgr = db.query(User).filter(
        User.organization_id == org_id,
        User.first_name == name,
        User.last_name == "Manager"
    ).first()
    
    if not mgr:
        # Fallback to general FINANCE_MANAGER
        mgr = db.query(User).filter(
            User.organization_id == org_id,
            User.role == "FINANCE_MANAGER"
        ).first()
    return mgr

# Attempt live GenAI Setup
from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types

API_KEY = os.environ.get("GEMINI_API_KEY")
client = None
if API_KEY and len(API_KEY) > 5:
    try:
        client = genai.Client()
        print("[INIT] Google GenAI Client connected for vision processing.")
    except Exception as e:
        print(f"[INIT] Live GenAI Client setup failed, running in simulated mode: {e}")

# Initialize FastAPI App
app = FastAPI(
    title="VendorPulse API",
    description="AI-powered Accounts Payable (AP) Automation and Treasury Capital Optimizer API",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure Database is Initialized and Seeded on Startup
@app.on_event("startup")
def on_startup():
    print("[STARTUP] Checking database initialization...")
    init_db(seed=True)


# =========================================================================
# PYDANTIC SCHEMAS
# =========================================================================

class SettingsUpdate(BaseModel):
    cost_of_capital: float
    minimum_liquidity_threshold: float
    cash_balance: float

class ExceptionResolution(BaseModel):
    action: str  # 'PAY_OVERRIDE', 'REQUEST_REVISED', 'WRITE_OFF'
    comments: Optional[str] = ""


# =========================================================================
# SMARTER OCR SIMULATOR BASELINES
# =========================================================================

MOCK_INVOICE_DATA_SUITE = {
    "acme": {
        "vendor_name": "Acme Industrial Supplies Ltd.",
        "invoice_number": "INV-2026-8942",
        "invoice_amount": 755.00,
        "purchase_order_number": "PO-99541",
        "payment_terms": "2/10 Net 30",
        "early_payment_discount_percentage": 0.02,
        "discount_period_days": 10,
        "net_period_days": 30,
        "line_items": [
            {"item_description": "Industrial Safety Gloves", "quantity": 10.0, "unit_price": 25.50, "total_price": 255.00},
            {"item_description": "Heavy Duty Steel Boots", "quantity": 5.0, "unit_price": 100.00, "total_price": 500.00}
        ]
    },
    "globex": {
        "vendor_name": "Globex Logistics",
        "invoice_number": "INV-2026-9051",
        "invoice_amount": 1200.00,
        "purchase_order_number": "PO-99542",
        "payment_terms": "Net 30",
        "early_payment_discount_percentage": 0.0,
        "discount_period_days": 0,
        "net_period_days": 30,
        "line_items": [
            {"item_description": "Freight & Warehousing Services", "quantity": 1.0, "unit_price": 1200.00, "total_price": 1200.00}
        ]
    },
    "initech": {
        "vendor_name": "Initech IT Solutions",
        "invoice_number": "INV-2026-9113",
        "invoice_amount": 5400.00,
        "purchase_order_number": "PO-99543",
        "payment_terms": "1/15 Net 45",
        "early_payment_discount_percentage": 0.01,
        "discount_period_days": 15,
        "net_period_days": 45,
        "line_items": [
            {"item_description": "Enterprise Software Licensing", "quantity": 1.0, "unit_price": 5400.00, "total_price": 5400.00}
        ]
    },
    "olivia": {
        "vendor_name": "Olivia Wilson Consulting",
        "invoice_number": "INV-2026-0412",
        "invoice_amount": 2500.00,
        "purchase_order_number": "N/A",  # No PO Match
        "payment_terms": "3/10 Net 30",
        "early_payment_discount_percentage": 0.03,
        "discount_period_days": 10,
        "net_period_days": 30,
        "line_items": [
            {"item_description": "Strategic Business Consulting", "quantity": 1.0, "unit_price": 2500.00, "total_price": 2500.00}
        ]
    }
}


def parse_invoice_with_gemini(file_bytes: bytes, mime_type: str) -> dict:
    """Wrapper that sends document bytes to Gemini 1.5 Flash or falls back to simulator."""
    if not client:
        return MOCK_INVOICE_DATA_SUITE["acme"]

    try:
        prompt = """
        You are an expert accounts payable auditing system. Analyze the uploaded invoice document image.
        Extract the exact data into a valid JSON object matching this schema:
        {
            "vendor_name": "Name of the supplier",
            "invoice_number": "Invoice ID number",
            "invoice_amount": 123.45 (total bill value as numeric float),
            "purchase_order_number": "PO number referenced, or 'N/A'",
            "payment_terms": "Terms like Net 30, 2/10 Net 30. Default to 'Net 30'",
            "early_payment_discount_percentage": 0.02 (discount percentage as a float if present, else 0.00),
            "discount_period_days": 10 (number of days to get the discount, default 0),
            "net_period_days": 30 (net payout days, default 30),
            "line_items": [
                {
                    "item_description": "Description of line item",
                    "quantity": 1.0 (numeric),
                    "unit_price": 1.00 (numeric),
                    "total_price": 1.00 (numeric)
                }
            ]
        }
        
        CRITICAL RULES:
        1. Extract the numeric total value only for amounts.
        2. Return ONLY the raw JSON structure. Do not wrap it in markdown block fences or backticks.
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                prompt
            ]
        )
        
        clean_text = response.text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text.split("```json")[1].split("```")[0].strip()
        elif clean_text.startswith("```"):
            clean_text = clean_text.split("```")[1].split("```")[0].strip()
            
        return json.loads(clean_text)
        
    except Exception as e:
        print(f"[OCR] Live Gemini parsing failed, falling back to simulator: {e}")
        return MOCK_INVOICE_DATA_SUITE["acme"]


# =========================================================================
# CORE 3-WAY MATCHING ALGORITHM
# =========================================================================

def execute_3_way_match(db: Session, invoice: Invoice, extracted_items: List[dict]):
    """Calculates ledger alignments and logs exception details in accordance with dbflow.md rules."""
    
    # 1. Verify PO number
    po = None
    if invoice.purchase_order_number and invoice.purchase_order_number != "N/A":
        po = db.query(PurchaseOrder).filter(
            PurchaseOrder.organization_id == invoice.organization_id,
            PurchaseOrder.po_number == invoice.purchase_order_number
        ).first()

    if not po:
        # Create a MISSING_PO exception
        exc = InvoiceException(
            invoice_id=invoice.id,
            exception_type="MISSING_PO",
            description=f"Purchase order '{invoice.purchase_order_number}' could not be matched to a record in the database.",
            confidence_score=Decimal("95.00"),
            status="OPEN"
        )
        # Auto-route based on gross invoice amount
        approver = get_approver_for_amount(float(invoice.amount), invoice.organization_id, db)
        if approver:
            exc.predicted_approver_id = approver.id
            exc.assigned_approver_id = approver.id
            
        db.add(exc)
        invoice.status = "EXCEPTION"
        invoice.matching_result = "NO_PO_FOUND"
        db.commit()
        return

    # Link invoice to PO
    invoice.purchase_order_id = po.id
    
    exceptions_raised = []
    
    # 2. Check total amount variance (Tolerance threshold: ±0.5% max $10)
    po_total = float(po.total_amount)
    inv_total = float(invoice.amount)
    variance_amount = abs(inv_total - po_total)
    variance_pct = (variance_amount / po_total) if po_total > 0 else 0.0
    
    if variance_pct > 0.005 or variance_amount > 10.0:
        exc = InvoiceException(
            invoice_id=invoice.id,
            exception_type="TOTAL_VARIANCE",
            description=f"Invoice total (${inv_total:.2f}) differs from Purchase Order total (${po_total:.2f}) by ${variance_amount:.2f} ({variance_pct * 100:.2f}%).",
            confidence_score=Decimal("90.00"),
            status="OPEN"
        )
        exceptions_raised.append(exc)

    # Fetch PO items to match line by line
    po_items = db.query(PurchaseOrderItem).filter(PurchaseOrderItem.purchase_order_id == po.id).all()
    po_items_map = {item.item_description.lower().strip(): item for item in po_items}
    
    # Fetch GR items
    gr = db.query(GoodsReceipt).filter(
        GoodsReceipt.organization_id == invoice.organization_id,
        GoodsReceipt.purchase_order_id == po.id
    ).first()
    
    gr_items_map = {}
    if gr:
        gr_items = db.query(GoodsReceiptItem).filter(GoodsReceiptItem.goods_receipt_id == gr.id).all()
        gr_items_map = {item.purchase_order_item_id: item for item in gr_items}

    # 3. Line by Line Match
    for ext_item in extracted_items:
        desc_val = ext_item.get("item_description")
        desc = str(desc_val).lower().strip() if desc_val else ""
        
        # Safely convert qty, unit price, and total price to float
        try:
            inv_qty = float(ext_item.get("quantity", 0.0) or 0.0)
        except (ValueError, TypeError):
            inv_qty = 0.0
            
        try:
            inv_price = float(ext_item.get("unit_price", 0.0) or 0.0)
        except (ValueError, TypeError):
            inv_price = 0.0
            
        try:
            inv_total_price = float(ext_item.get("total_price", 0.0) or 0.0)
        except (ValueError, TypeError):
            inv_total_price = 0.0
        
        # Insert line item
        inv_line = InvoiceItem(
            invoice_id=invoice.id,
            item_description=desc_val or "Unknown Item",
            quantity=Decimal(str(inv_qty)),
            unit_price=Decimal(str(inv_price)),
            total_price=Decimal(str(inv_total_price))
        )
        
        # Match PO item
        po_item = po_items_map.get(desc)
        # Fallback to loose substring match
        if not po_item and desc:
            for po_desc, item in po_items_map.items():
                if po_desc in desc or desc in po_desc:
                    po_item = item
                    break

        if po_item:
            inv_line.purchase_order_item_id = po_item.id
            
            # A. Check price variance (Tolerance: 0%)
            po_price = float(po_item.unit_price)
            if abs(inv_price - po_price) > 0.001:
                exc = InvoiceException(
                    invoice_id=invoice.id,
                    exception_type="PRICE_VARIANCE",
                    description=f"Line price mismatch on '{po_item.item_description}': Invoiced ${inv_price:.2f} vs PO Unit Price ${po_price:.2f}.",
                    confidence_score=Decimal("88.00"),
                    status="OPEN"
                )
                exceptions_raised.append(exc)
                
            # B. Check quantity variance (Tolerance: +0% / -5% received vs invoiced)
            gr_item = gr_items_map.get(po_item.id)
            if not gr_item:
                exc = InvoiceException(
                    invoice_id=invoice.id,
                    exception_type="MISSING_GR",
                    description=f"No Goods Receipt entry found for item '{po_item.item_description}'.",
                    confidence_score=Decimal("92.00"),
                    status="OPEN"
                )
                exceptions_raised.append(exc)
            else:
                received_qty = float(gr_item.quantity_received)
                if inv_qty > received_qty:
                    exc = InvoiceException(
                        invoice_id=invoice.id,
                        exception_type="QUANTITY_VARIANCE",
                        description=f"Invoiced quantity ({inv_qty}) exceeds quantity marked as received ({received_qty}) on '{po_item.item_description}'.",
                        confidence_score=Decimal("89.00"),
                        status="OPEN"
                    )
                    exceptions_raised.append(exc)
        else:
            # Item not in PO
            exc = InvoiceException(
                invoice_id=invoice.id,
                exception_type="PRICE_VARIANCE",
                description=f"Line item '{desc_val or 'Unknown Item'}' does not exist on Purchase Order {po.po_number}.",
                confidence_score=Decimal("80.00"),
                status="OPEN"
            )
            exceptions_raised.append(exc)
            
        db.add(inv_line)

    # 4. Handle Exceptions Routing & Final Status mapping
    if exceptions_raised:
        invoice.status = "EXCEPTION"
        # Map matching result based on primary exception type
        ext_types = [e.exception_type for e in exceptions_raised]
        if "PRICE_VARIANCE" in ext_types or "TOTAL_VARIANCE" in ext_types:
            invoice.matching_result = "PRICE_MISMATCH"
        elif "QUANTITY_VARIANCE" in ext_types or "MISSING_GR" in ext_types:
            invoice.matching_result = "QTY_MISMATCH"
        else:
            invoice.matching_result = "NO_PO_FOUND"

        # AI Exception Router: Retrieve routing rules based on PO department
        rule = db.query(ApprovalRule).filter(
            ApprovalRule.organization_id == invoice.organization_id,
            ApprovalRule.department == po.department,
            ApprovalRule.is_active == True
        ).first()

        for exc in exceptions_raised:
            # Assign predicted route
            if rule:
                exc.predicted_approver_id = rule.approver_id
                # Rule found = High Confidence (>= 85%). Auto-route.
                exc.confidence_score = Decimal("90.00")
                exc.assigned_approver_id = rule.approver_id
            else:
                # Fallback to amount-based level manager
                approver = get_approver_for_amount(float(invoice.amount), invoice.organization_id, db)
                if approver:
                    exc.predicted_approver_id = approver.id
                    exc.confidence_score = Decimal("85.00")
                    exc.assigned_approver_id = approver.id
            db.add(exc)
    else:
        invoice.status = "MATCHED"
        invoice.matching_result = "THREE_WAY_OK"
        
    db.commit()


# =========================================================================
# SERIALIZATION HELPERS
# =========================================================================

def format_invoice(invoice: Invoice, db: Session) -> Dict[str, Any]:
    # Find early payment yield and cash savings
    d = float(invoice.vendor.default_discount_pct) if invoice.vendor else 0.0
    t_early = float(invoice.vendor.discount_days) if invoice.vendor else 0.0
    t_net = float(invoice.vendor.net_days) if invoice.vendor else 30.0
    days_saved = t_net - t_early
    
    if days_saved > 0 and d > 0:
        implied_annual_yield = round((d / (1.0 - d)) * (365.0 / days_saved) * 100, 2)
        cash_savings = round(float(invoice.amount) * d, 2)
    else:
        implied_annual_yield = 0.0
        cash_savings = 0.0

    due_date_str = invoice.due_date.isoformat() if hasattr(invoice.due_date, 'isoformat') else str(invoice.due_date)
    
    early_pay_date = None
    if invoice.vendor and invoice.vendor.discount_days > 0:
        issue = invoice.issue_date or date.today()
        early_pay_date = (issue + timedelta(days=invoice.vendor.discount_days)).isoformat()

    # Exception mapping
    exception_dict = None
    exc = next((e for e in invoice.exceptions if e.status == "OPEN"), None)
    if not exc and invoice.exceptions:
        exc = invoice.exceptions[0]
    
    if exc:
        predicted_approver = "Finance Manager"
        if exc.predicted_approver_id:
            approver_user = db.query(User).filter(User.id == exc.predicted_approver_id).first()
            if approver_user:
                predicted_approver = f"{approver_user.first_name} {approver_user.last_name} ({approver_user.role})"
        
        exception_dict = {
            "exception_type": exc.exception_type,
            "description": exc.description,
            "confidence_score": float(exc.confidence_score) if exc.confidence_score else 0.0,
            "predicted_approver": predicted_approver,
            "status": exc.status,
            "resolution_action": exc.exception_type,
            "comments": exc.resolution_notes or ""
        }

    # Find PO number
    po_num = "N/A"
    if invoice.purchase_order:
        po_num = invoice.purchase_order.po_number
    elif invoice.ocr_raw_json and isinstance(invoice.ocr_raw_json, dict):
        po_num = invoice.ocr_raw_json.get("purchase_order_number", "N/A")

    # Find approver name
    approver_name = "N/A"
    approval = db.query(ApprovalHistory).filter(
        ApprovalHistory.invoice_id == invoice.id,
        ApprovalHistory.action == 'APPROVED'
    ).order_by(ApprovalHistory.created_at.desc()).first()
    
    if approval:
        approver_user = db.query(User).filter(User.id == approval.approver_id).first()
        if approver_user:
            approver_name = f"{approver_user.first_name} {approver_user.last_name}"
        else:
            approver_name = "Robert Smith"
    else:
        exc = next((e for e in invoice.exceptions), None)
        if exc and exc.assigned_approver_id:
            approver_user = db.query(User).filter(User.id == exc.assigned_approver_id).first()
            if approver_user:
                approver_name = f"{approver_user.first_name} {approver_user.last_name}"
        elif invoice.status in ["APPROVED", "PAID"]:
            approver = get_approver_for_amount(float(invoice.amount), invoice.organization_id, db)
            if approver:
                approver_name = f"{approver.first_name} {approver.last_name}"
            else:
                approver_name = "Robert Smith"

    return {
        "id": str(invoice.id),
        "vendor_name": invoice.vendor.name if invoice.vendor else "Unknown Vendor",
        "invoice_number": invoice.invoice_number,
        "invoice_amount": float(invoice.amount),
        "purchase_order_number": po_num,
        "payment_terms": invoice.payment_terms,
        "early_payment_discount_percentage": d,
        "discount_period_days": int(t_early),
        "net_period_days": int(t_net),
        "status": invoice.status,
        "matching_result": invoice.matching_result or "THREE_WAY_OK",
        "early_payment_status": invoice.early_payment_status or "CALCULATED",
        "implied_annual_yield": implied_annual_yield,
        "cash_savings": cash_savings,
        "created_at": invoice.created_at.isoformat() + "Z" if invoice.created_at else datetime.utcnow().isoformat() + "Z",
        "due_date": due_date_str,
        "early_pay_date": early_pay_date,
        "exception": exception_dict,
        "is_live_ai": bool(invoice.ocr_raw_json.get("is_live_ai", False)) if invoice.ocr_raw_json else False,
        "approver_name": approver_name
    }


# =========================================================================
# API ROUTES
# =========================================================================

@app.get("/api/users/me")
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    vendor_name = ""
    if current_user.vendor_id:
        v = db.query(Vendor).filter(Vendor.id == current_user.vendor_id).first()
        if v:
            vendor_name = v.name
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "role": current_user.role,
        "vendor_id": str(current_user.vendor_id) if current_user.vendor_id else None,
        "vendor_name": vendor_name
    }

class RoleChangeRequest(BaseModel):
    role: str
    vendor_id: Optional[str] = None

@app.post("/api/users/change-role")
def change_role(
    req: RoleChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    current_user.role = req.role
    if req.vendor_id:
        current_user.vendor_id = uuid.UUID(req.vendor_id) if isinstance(req.vendor_id, str) else req.vendor_id
    else:
        current_user.vendor_id = None
    db.commit()
    db.refresh(current_user)
    
    vendor_name = ""
    if current_user.vendor_id:
        v = db.query(Vendor).filter(Vendor.id == current_user.vendor_id).first()
        if v:
            vendor_name = v.name
            
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "role": current_user.role,
        "vendor_id": str(current_user.vendor_id) if current_user.vendor_id else None,
        "vendor_name": vendor_name
    }

@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization settings not found")
    return {
        "cost_of_capital": float(org.cost_of_capital),
        "minimum_liquidity_threshold": float(org.minimum_liquidity_threshold),
        "cash_balance": float(org.cash_balance)
    }


@app.post("/api/settings")
def update_settings(settings: SettingsUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization settings not found")
        
    org.cost_of_capital = Decimal(str(settings.cost_of_capital))
    org.minimum_liquidity_threshold = Decimal(str(settings.minimum_liquidity_threshold))
    org.cash_balance = Decimal(str(settings.cash_balance))
    
    # Recalculate recommendations for outstanding invoices
    invoices = db.query(Invoice).filter(
        Invoice.status.in_(["PENDING_MATCH", "EXCEPTION", "APPROVED"]),
        Invoice.organization_id == current_user.organization_id
    ).all()
    for inv in invoices:
        d = float(inv.vendor.default_discount_pct) if inv.vendor else 0.0
        t_early = float(inv.vendor.discount_days) if inv.vendor else 0.0
        t_net = float(inv.vendor.net_days) if inv.vendor else 30.0
        days_saved = t_net - t_early
        if days_saved > 0 and d > 0:
            implied_annual_yield = (d / (1.0 - d)) * (365.0 / days_saved)
            if implied_annual_yield * 100.0 > settings.cost_of_capital:
                inv.early_payment_status = "OPTIMAL_PAID_EARLY"
            else:
                inv.early_payment_status = "OPTIMAL_PAID_NET"
        else:
            inv.early_payment_status = "OPTIMAL_PAID_NET"
            
    db.commit()
    return {
        "cost_of_capital": float(org.cost_of_capital),
        "minimum_liquidity_threshold": float(org.minimum_liquidity_threshold),
        "cash_balance": float(org.cash_balance)
    }


@app.get("/api/vendors")
def get_vendors(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    vendors = db.query(Vendor).filter(Vendor.organization_id == current_user.organization_id).all()
    return [
        {
            "id": str(v.id),
            "name": v.name,
            "email": v.email,
            "payment_terms": v.payment_terms,
            "default_discount_pct": float(v.default_discount_pct),
            "discount_days": v.discount_days,
            "net_days": v.net_days,
            "bank_name": v.bank_name or "",
            "bank_routing_number": v.bank_routing_number or "",
            "bank_account_number": v.bank_account_number or "",
            "status": v.status
        }
        for v in vendors
    ]


@app.get("/api/pos")
def get_pos(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(PurchaseOrder).filter(PurchaseOrder.organization_id == current_user.organization_id)
    if current_user.role == "SUPPLIER_USER" and current_user.vendor_id:
        query = query.filter(PurchaseOrder.vendor_id == current_user.vendor_id)
    pos = query.all()
    return [
        {
            "id": str(po.id),
            "po_number": po.po_number,
            "vendor_name": po.vendor.name if po.vendor else "Unknown Vendor",
            "issue_date": po.issue_date.isoformat() if hasattr(po.issue_date, 'isoformat') else str(po.issue_date),
            "total_amount": float(po.total_amount),
            "department": po.department,
            "status": po.status,
            "items": [
                {
                    "description": item.item_description,
                    "quantity": float(item.quantity),
                    "unit_price": float(item.unit_price),
                    "total": float(item.total_price)
                }
                for item in po.items
            ]
        }
        for po in pos
    ]


@app.get("/api/invoices")
def get_invoices(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(Invoice).filter(Invoice.organization_id == current_user.organization_id)
    if current_user.role == "SUPPLIER_USER" and current_user.vendor_id:
        query = query.filter(Invoice.vendor_id == current_user.vendor_id)
    invoices = query.all()
    invoices_sorted = sorted(invoices, key=lambda x: x.created_at or datetime.min, reverse=True)
    return [format_invoice(inv, db) for inv in invoices_sorted]


@app.post("/api/invoices/{invoice_id}/approve")
def approve_invoice(invoice_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.organization_id == current_user.organization_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice.status = "APPROVED"
    
    # Record in approval history
    approval = ApprovalHistory(
        invoice_id=invoice.id,
        approver_id=current_user.id,
        action="APPROVED",
        comments="Approved by Business Manager"
    )
    db.add(approval)
    db.commit()
    return format_invoice(invoice, db)


@app.post("/api/invoices/{invoice_id}/pay")
def pay_invoice(invoice_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.organization_id == current_user.organization_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    invoice.status = "PAID"
    
    # Deduct from organization's cash balance
    org = db.query(Organization).filter(Organization.id == invoice.organization_id).first()
    if org:
        d = float(invoice.vendor.default_discount_pct) if invoice.vendor else 0.0
        if invoice.early_payment_status == "OPTIMAL_PAID_EARLY" and d > 0:
            payment_amount = float(invoice.amount) * (1 - d)
        else:
            payment_amount = float(invoice.amount)
        org.cash_balance = Decimal(str(float(org.cash_balance) - payment_amount))
        
    db.commit()
    return format_invoice(invoice, db)


@app.post("/api/invoices/{invoice_id}/reject")
def reject_invoice(invoice_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.organization_id == current_user.organization_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice.status = "REJECTED"
    db.commit()
    return format_invoice(invoice, db)


@app.post("/api/invoices/{invoice_id}/resolve-exception")
def resolve_exception(invoice_id: str, resolution: ExceptionResolution, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.organization_id == current_user.organization_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    # Find active open exception
    exc = next((e for e in invoice.exceptions if e.status == "OPEN"), None)
    if not exc:
         raise HTTPException(status_code=400, detail="Invoice does not have an open exception")
         
    for e in invoice.exceptions:
        if e.status == "OPEN":
            e.status = "RESOLVED"
            e.resolution_notes = resolution.comments
            
    if resolution.action == "PAY_OVERRIDE":
        invoice.status = "APPROVED"
    elif resolution.action == "REQUEST_REVISED":
        invoice.status = "REJECTED"
    else:
        invoice.status = "APPROVED" # Write off variance and approve
        
    db.commit()
    return format_invoice(invoice, db)


@app.post("/api/invoices/upload")
async def upload_invoice(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Ingests invoice document, parses it with live OCR/GenAI (or simulator fallback),
    runs the 3-Way Match Verification Engine, and computes capital optimization recommendations.
    """
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization profile not found. Run database seeding.")

    file_bytes = await file.read()
    file_name = file.filename.lower()
    
    # Try to find a matches in name to return appropriate mock flow
    mock_key = None
    if "acme" in file_name:
        mock_key = "acme"
    elif "globex" in file_name:
        mock_key = "globex"
    elif "initech" in file_name:
        mock_key = "initech"
    elif "olivia" in file_name:
        mock_key = "olivia"
    
    invoice_data = {}
    if mock_key:
        invoice_data = MOCK_INVOICE_DATA_SUITE[mock_key].copy()
    else:
        invoice_data = {
            "vendor_name": "Unknown Vendor",
            "invoice_number": f"INV-{uuid.uuid4().hex[:6].upper()}",
            "invoice_amount": 0.0,
            "purchase_order_number": "N/A",
            "payment_terms": "Net 30",
            "early_payment_discount_percentage": 0.0,
            "discount_period_days": 0,
            "net_period_days": 30,
            "line_items": []
        }

    use_live_ai = False
    
    # Check if Google Document AI is configured
    gcp_project = os.environ.get("GCP_PROJECT_ID")
    docai_processor = os.environ.get("DOCUMENT_AI_PROCESSOR_ID")
    
    mime = "application/pdf"
    if file_name.endswith(".png"):
        mime = "image/png"
    elif file_name.endswith(".jpg") or file_name.endswith(".jpeg"):
        mime = "image/jpeg"
        
    if not mock_key and gcp_project and docai_processor:
        try:
            extractor = DocumentAIExtractor()
            parsed = extractor.process_document_bytes(file_bytes, mime)
            
            for key in ["vendor_name", "invoice_number", "invoice_amount", "purchase_order_number", "payment_terms"]:
                if key in parsed:
                    invoice_data[key] = parsed[key]
            for key in ["early_payment_discount_percentage", "discount_period_days", "net_period_days"]:
                if key in parsed:
                    val = parsed[key]
                    if val is None or val == "" or val == "None" or val == "N/A":
                        invoice_data[key] = 0.0 if key == "early_payment_discount_percentage" else 0
                    else:
                        invoice_data[key] = float(val) if key == "early_payment_discount_percentage" else int(float(val))
            if "line_items" in parsed:
                invoice_data["line_items"] = parsed["line_items"]
            use_live_ai = True
        except Exception as e:
            print(f"[DocumentAI] Live extraction failed: {e}")
            use_live_ai = False
            
    # Fallback to Gemini API if Document AI is not set or failed
    if not mock_key and not use_live_ai:
        if API_KEY and len(API_KEY) > 5:
            try:
                parsed = parse_invoice_with_gemini(file_bytes, mime)
                for key in ["vendor_name", "invoice_number", "invoice_amount", "purchase_order_number", "payment_terms"]:
                    if key in parsed:
                        invoice_data[key] = parsed[key]
                for key in ["early_payment_discount_percentage", "discount_period_days", "net_period_days"]:
                    if key in parsed:
                        val = parsed[key]
                        if val is None or val == "" or val == "None" or val == "N/A":
                            invoice_data[key] = 0.0 if key == "early_payment_discount_percentage" else 0
                        else:
                            invoice_data[key] = float(val) if key == "early_payment_discount_percentage" else int(float(val))
                if "line_items" in parsed:
                    invoice_data["line_items"] = parsed["line_items"]
                use_live_ai = True
            except Exception as e:
                print(f"[Gemini fallback] Live extraction failed: {e}")
                use_live_ai = False

    # Mark live AI flag
    invoice_data["is_live_ai"] = use_live_ai

    # Lookup or create Vendor
    if current_user.role == "SUPPLIER_USER" and current_user.vendor_id:
        vendor = db.query(Vendor).filter(Vendor.id == current_user.vendor_id).first()
    else:
        vendor_name = invoice_data.get("vendor_name", "Unknown Vendor")
        vendor = db.query(Vendor).filter(Vendor.name == vendor_name, Vendor.organization_id == org.id).first()
        if not vendor:
            discount_pct = clean_numeric_value(invoice_data.get("early_payment_discount_percentage", 0.00))
            if discount_pct > 1.0:
                discount_pct = discount_pct / 100.0
                
            vendor = Vendor(
                organization_id=org.id,
                name=vendor_name,
                email=f"billing@{vendor_name.lower().replace(' ', '')}.com",
                payment_terms=invoice_data.get("payment_terms", "Net 30"),
                default_discount_pct=Decimal(str(discount_pct)),
                discount_days=int(clean_numeric_value(invoice_data.get("discount_period_days", 0))),
                net_days=int(clean_numeric_value(invoice_data.get("net_period_days", 30))),
                status="ACTIVE"
            )
            db.add(vendor)
            db.flush()

    # Create Invoice ORM Model
    issue_date = date.today()
    net_days = int(clean_numeric_value(invoice_data.get("net_period_days", 30)))
    due_date = issue_date + timedelta(days=net_days)

    invoice_amount = clean_numeric_value(invoice_data.get("invoice_amount", 0.00))

    invoice = Invoice(
        organization_id=org.id,
        vendor_id=vendor.id,
        invoice_number=invoice_data.get("invoice_number", f"INV-{uuid.uuid4().hex[:6].upper()}"),
        amount=Decimal(str(invoice_amount)),
        tax_amount=Decimal("0.00"),
        issue_date=issue_date,
        due_date=due_date,
        payment_terms=invoice_data.get("payment_terms", "Net 30"),
        file_url=f"s3://vendorpulse-invoices/{file.filename}",
        ocr_raw_json=invoice_data,
        status="PENDING_MATCH",
        early_payment_status="CALCULATED"
    )
    
    # Store PO number temporarily
    invoice.purchase_order_number = invoice_data.get("purchase_order_number")
    
    try:
        db.add(invoice)
        db.flush()

        # Execute 3-Way Match Verification Pipeline
        execute_3_way_match(db, invoice, invoice_data.get("line_items", []))

        # Evaluate Early Payment Yield Recommendation
        d = float(invoice.vendor.default_discount_pct)
        t_early = float(invoice.vendor.discount_days)
        t_net = float(invoice.vendor.net_days)
        days_saved = t_net - t_early

        if days_saved > 0 and d > 0:
            implied_annual_yield = (d / (1.0 - d)) * (365.0 / days_saved)
            if implied_annual_yield * 100.0 > float(org.cost_of_capital):
                invoice.early_payment_status = "OPTIMAL_PAID_EARLY"
            else:
                invoice.early_payment_status = "OPTIMAL_PAID_NET"
        else:
            invoice.early_payment_status = "OPTIMAL_PAID_NET"

        db.commit()
    except Exception as e:
        db.rollback()
        from sqlalchemy.exc import IntegrityError
        if isinstance(e, IntegrityError) or "UNIQUE constraint" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invoice number '{invoice.invoice_number}' already exists in the system for supplier '{vendor_name}'."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process invoice matching: {str(e)}"
        )

    return format_invoice(invoice, db)


@app.post("/api/invoices/email-simulate")
async def email_simulate_invoice(
    sender_email: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Simulates receiving an email from a vendor, checks the subject/body for invoice keywords,
    and runs the AI/OCR ingestion pipeline if the check passes.
    """
    # 1. Natural Language Keywords Check
    invoice_keywords = ["invoice", "bill", "receipt", "payment", "attached", "invoice.pdf", "statement", "fee", "cost", "charge"]
    text_to_check = (subject + " " + body).lower()
    
    keyword_found = any(kw in text_to_check for kw in invoice_keywords)
    if not keyword_found:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ingestion Ignored: The email subject or body does not contain invoice-related language (e.g., 'invoice', 'bill', 'payment', 'attached')."
        )
        
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization profile not found.")
        
    file_bytes = await file.read()
    file_name = file.filename.lower()
    
    # Try to find a matches in name to return appropriate mock flow
    mock_key = None
    if "acme" in file_name:
        mock_key = "acme"
    elif "globex" in file_name:
        mock_key = "globex"
    elif "initech" in file_name:
        mock_key = "initech"
    elif "olivia" in file_name:
        mock_key = "olivia"
        
    invoice_data = {}
    if mock_key:
        invoice_data = MOCK_INVOICE_DATA_SUITE[mock_key].copy()
    else:
        invoice_data = {
            "vendor_name": "Unknown Vendor",
            "invoice_number": f"INV-{uuid.uuid4().hex[:6].upper()}",
            "invoice_amount": 0.0,
            "purchase_order_number": "N/A",
            "payment_terms": "Net 30",
            "early_payment_discount_percentage": 0.0,
            "discount_period_days": 0,
            "net_period_days": 30,
            "line_items": []
        }

    use_live_ai = False
    
    # Check if Google Document AI is configured
    gcp_project = os.environ.get("GCP_PROJECT_ID")
    docai_processor = os.environ.get("DOCUMENT_AI_PROCESSOR_ID")
    
    mime = "application/pdf"
    if file_name.endswith(".png"):
        mime = "image/png"
    elif file_name.endswith(".jpg") or file_name.endswith(".jpeg"):
        mime = "image/jpeg"
        
    if not mock_key and gcp_project and docai_processor:
        try:
            extractor = DocumentAIExtractor()
            parsed = extractor.process_document_bytes(file_bytes, mime)
            for key in ["vendor_name", "invoice_number", "invoice_amount", "purchase_order_number", "payment_terms"]:
                if key in parsed:
                    invoice_data[key] = parsed[key]
            for key in ["early_payment_discount_percentage", "discount_period_days", "net_period_days"]:
                if key in parsed:
                    val = parsed[key]
                    if val is None or val == "" or val == "None" or val == "N/A":
                        invoice_data[key] = 0.0 if key == "early_payment_discount_percentage" else 0
                    else:
                        invoice_data[key] = float(val) if key == "early_payment_discount_percentage" else int(float(val))
            if "line_items" in parsed:
                invoice_data["line_items"] = parsed["line_items"]
            use_live_ai = True
        except Exception as e:
            print(f"[DocumentAI] Live extraction failed: {e}")
            use_live_ai = False
            
    # Fallback to Gemini API
    if not mock_key and not use_live_ai:
        if API_KEY and len(API_KEY) > 5:
            try:
                parsed = parse_invoice_with_gemini(file_bytes, mime)
                for key in ["vendor_name", "invoice_number", "invoice_amount", "purchase_order_number", "payment_terms"]:
                    if key in parsed:
                        invoice_data[key] = parsed[key]
                for key in ["early_payment_discount_percentage", "discount_period_days", "net_period_days"]:
                    if key in parsed:
                        val = parsed[key]
                        if val is None or val == "" or val == "None" or val == "N/A":
                            invoice_data[key] = 0.0 if key == "early_payment_discount_percentage" else 0
                        else:
                            invoice_data[key] = float(val) if key == "early_payment_discount_percentage" else int(float(val))
                if "line_items" in parsed:
                    invoice_data["line_items"] = parsed["line_items"]
                use_live_ai = True
            except Exception as e:
                print(f"[Gemini fallback] Live extraction failed: {e}")
                use_live_ai = False

    invoice_data["is_live_ai"] = use_live_ai

    # Lookup Vendor by sender_email or vendor name
    vendor = db.query(Vendor).filter(Vendor.email == sender_email, Vendor.organization_id == org.id).first()
    if not vendor:
        # Fallback to parsed vendor name
        vendor_name = invoice_data.get("vendor_name", "Unknown Vendor")
        vendor = db.query(Vendor).filter(Vendor.name == vendor_name, Vendor.organization_id == org.id).first()
        if not vendor:
            discount_pct = clean_numeric_value(invoice_data.get("early_payment_discount_percentage", 0.00))
            if discount_pct > 1.0:
                discount_pct = discount_pct / 100.0
            vendor = Vendor(
                organization_id=org.id,
                name=vendor_name,
                email=sender_email if sender_email else f"billing@{vendor_name.lower().replace(' ', '')}.com",
                payment_terms=invoice_data.get("payment_terms", "Net 30"),
                default_discount_pct=Decimal(str(discount_pct)),
                discount_days=int(clean_numeric_value(invoice_data.get("discount_period_days", 0))),
                net_days=int(clean_numeric_value(invoice_data.get("net_period_days", 30))),
                status="ACTIVE"
            )
            db.add(vendor)
            db.flush()

    issue_date = date.today()
    net_days = int(clean_numeric_value(invoice_data.get("net_period_days", 30)))
    due_date = issue_date + timedelta(days=net_days)
    invoice_amount = clean_numeric_value(invoice_data.get("invoice_amount", 0.00))

    invoice = Invoice(
        organization_id=org.id,
        vendor_id=vendor.id,
        invoice_number=invoice_data.get("invoice_number", f"INV-{uuid.uuid4().hex[:6].upper()}"),
        amount=Decimal(str(invoice_amount)),
        tax_amount=Decimal("0.00"),
        issue_date=issue_date,
        due_date=due_date,
        payment_terms=invoice_data.get("payment_terms", "Net 30"),
        file_url=f"s3://vendorpulse-invoices/{file.filename}",
        ocr_raw_json=invoice_data,
        status="PENDING_MATCH",
        early_payment_status="CALCULATED"
    )
    
    invoice.purchase_order_number = invoice_data.get("purchase_order_number")
    
    try:
        db.add(invoice)
        db.flush()
        execute_3_way_match(db, invoice, invoice_data.get("line_items", []))
        
        d = float(invoice.vendor.default_discount_pct)
        t_early = float(invoice.vendor.discount_days)
        t_net = float(invoice.vendor.net_days)
        days_saved = t_net - t_early

        if days_saved > 0 and d > 0:
            implied_annual_yield = (d / (1.0 - d)) * (365.0 / days_saved)
            if implied_annual_yield * 100.0 > float(org.cost_of_capital):
                invoice.early_payment_status = "OPTIMAL_PAID_EARLY"
            else:
                invoice.early_payment_status = "OPTIMAL_PAID_NET"
        else:
            invoice.early_payment_status = "OPTIMAL_PAID_NET"

        db.commit()
    except Exception as e:
        db.rollback()
        from sqlalchemy.exc import IntegrityError
        if isinstance(e, IntegrityError) or "UNIQUE constraint" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invoice number '{invoice.invoice_number}' already exists in the system for supplier '{vendor.name}'."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process invoice matching: {str(e)}"
        )

    return format_invoice(invoice, db)


@app.get("/api/analytics")
def get_analytics(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    cost_of_capital = float(org.cost_of_capital)
    cash_balance = float(org.cash_balance)
    
    invoices = db.query(Invoice).filter(Invoice.organization_id == current_user.organization_id).all()
    
    total_ap = 0.0
    realized_savings = 0.0
    potential_savings = 0.0
    
    week_needs_early = [0.0, 0.0, 0.0, 0.0]
    week_needs_net = [0.0, 0.0, 0.0, 0.0]
    
    for inv in invoices:
        amount = float(inv.amount)
        d = float(inv.vendor.default_discount_pct) if inv.vendor else 0.0
        t_early = inv.vendor.discount_days if inv.vendor else 0
        t_net = inv.vendor.net_days if inv.vendor else 30
        
        days_saved = t_net - t_early
        cash_savings = amount * d if (days_saved > 0 and d > 0) else 0.0
            
        if inv.status in ["PENDING_MATCH", "EXCEPTION", "APPROVED"]:
            total_ap += amount
            if inv.early_payment_status == "OPTIMAL_PAID_EARLY":
                potential_savings += cash_savings
        elif inv.status == "PAID":
            if inv.early_payment_status == "OPTIMAL_PAID_EARLY":
                realized_savings += cash_savings

        if inv.status not in ["PAID", "REJECTED"]:
            net_week = min(t_net // 7, 3)
            week_needs_net[net_week] += amount
            
            if inv.early_payment_status == "OPTIMAL_PAID_EARLY" and t_early > 0:
                early_week = min(t_early // 7, 3)
                discounted_amt = amount - cash_savings
                week_needs_early[early_week] += discounted_amt
            else:
                week_needs_early[net_week] += amount
                
    cogs_monthly = 600000.0
    dpo = round((total_ap / cogs_monthly) * 30, 1) if total_ap > 0 else 32.5
    
    return {
        "total_ap": total_ap,
        "realized_savings": round(realized_savings, 2),
        "potential_savings": round(potential_savings, 2),
        "dpo": dpo,
        "cash_balance": cash_balance,
        "cost_of_capital": cost_of_capital,
        "forecast": {
            "categories": ["Week 1", "Week 2", "Week 3", "Week 4"],
            "early_payment_schedule": [round(val, 2) for val in week_needs_early],
            "net_payment_schedule": [round(val, 2) for val in week_needs_net]
        }
    }


# =========================================================================
# ADMINISTRATOR ENDPOINTS
# =========================================================================

class ApproveUserRequest(BaseModel):
    role: str  # 'FINANCE_MANAGER' or 'SUPPLIER_USER'
    vendor_id: Optional[str] = None

@app.get("/api/users/pending")
def get_pending_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "ADMINISTRATOR":
        raise HTTPException(status_code=403, detail="Only administrators can view pending users.")
    users = db.query(User).filter(User.status == "PENDING").all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "first_name": u.first_name or "New",
            "last_name": u.last_name or "Signup",
            "created_at": u.created_at.isoformat() if u.created_at else None
        }
        for u in users
    ]

@app.post("/api/users/{user_id}/approve")
def approve_user(
    user_id: str, 
    payload: ApproveUserRequest, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    if current_user.role != "ADMINISTRATOR":
        raise HTTPException(status_code=403, detail="Only administrators can approve users.")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    user.role = payload.role
    user.status = "APPROVED"
    if payload.role == "SUPPLIER_USER" and payload.vendor_id:
        user.vendor_id = uuid.UUID(payload.vendor_id) if isinstance(payload.vendor_id, str) else payload.vendor_id
        
    db.commit()
    db.refresh(user)
    return {"status": "success", "message": f"User approved as {payload.role}"}

@app.post("/api/users/{user_id}/reject")
def reject_user(
    user_id: str, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    if current_user.role != "ADMINISTRATOR":
        raise HTTPException(status_code=403, detail="Only administrators can reject users.")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.status = "REJECTED"
    db.commit()
    return {"status": "success", "message": "User registration request rejected."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
