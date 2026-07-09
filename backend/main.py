import os
import json
import uuid
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

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

# Attempt live GenAI Setup
from google import genai
from google.genai import types

API_KEY = os.environ.get("GEMINI_API_KEY")
client = None
if API_KEY:
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

class ItemResponse(BaseModel):
    id: str
    item_description: str
    quantity: float
    unit_price: float
    total_price: float

    class Config:
        from_attributes = True

class ExceptionResponse(BaseModel):
    id: str
    exception_type: str
    description: Optional[str]
    confidence_score: Optional[float]
    assigned_approver_id: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class InvoiceResponse(BaseModel):
    id: str
    vendor_name: Optional[str]
    invoice_number: str
    amount: float
    tax_amount: float
    issue_date: date
    due_date: date
    payment_terms: str
    status: str
    matching_result: Optional[str]
    early_payment_status: str
    file_url: Optional[str]
    created_at: datetime
    items: List[ItemResponse] = []
    exceptions: List[ExceptionResponse] = []

    class Config:
        from_attributes = True

class ExceptionResolveRequest(BaseModel):
    action: str = Field(..., description="Resolution action: 'PAY_OVERRIDE', 'REQUEST_REVISED_INVOICE', 'WRITE_OFF_VARIANCE'")
    notes: str = Field(..., description="Manual resolution notes")
    resolved_by_clerk_id: str = Field(..., description="Clerk ID of the user resolving the exception")

class TreasuryRecommendation(BaseModel):
    invoice_id: str
    invoice_number: str
    vendor_name: str
    amount: float
    due_date: date
    payment_terms: str
    implied_annual_yield_pct: float
    instant_cash_saved: float
    recommendation: str
    economic_value_added: float

    class Config:
        from_attributes = True

class CashFlowForecastItem(BaseModel):
    week_start: date
    early_payment_outflow: float
    net_payment_outflow: float
    cash_savings: float


# =========================================================================
# SMARTER OCR SIMULATOR BASELINES
# =========================================================================

MOCK_BASELINE = {
    "vendor_name": "Acme Industrial Supplies Ltd.",
    "invoice_number": "INV-2026-8942",
    "invoice_amount": 755.00,
    "purchase_order_number": "PO-99541",
    "payment_terms": "2/10 Net 30",
    "early_payment_discount_percentage": 0.02,
    "discount_period_days": 10,
    "net_period_days": 30,
    "line_items": [
        {"item_description": "Heavy Duty Steel Bolts", "quantity": 10.0, "unit_price": 50.00, "total_price": 500.00},
        {"item_description": "Industrial Lubricant Spray", "quantity": 5.0, "unit_price": 51.00, "total_price": 255.00}
    ]
}

MOCK_PRICE_VARIANCE = {
    "vendor_name": "Acme Industrial Supplies Ltd.",
    "invoice_number": "INV-2026-8943",
    "invoice_amount": 805.00,
    "purchase_order_number": "PO-99541",
    "payment_terms": "2/10 Net 30",
    "early_payment_discount_percentage": 0.02,
    "discount_period_days": 10,
    "net_period_days": 30,
    "line_items": [
        {"item_description": "Heavy Duty Steel Bolts", "quantity": 10.0, "unit_price": 55.00, "total_price": 550.00},  # Mismatch! Unit Price is $55, PO is $50
        {"item_description": "Industrial Lubricant Spray", "quantity": 5.0, "unit_price": 51.00, "total_price": 255.00}
    ]
}

MOCK_QTY_VARIANCE = {
    "vendor_name": "Acme Industrial Supplies Ltd.",
    "invoice_number": "INV-2026-8944",
    "invoice_amount": 855.00,
    "purchase_order_number": "PO-99541",
    "payment_terms": "2/10 Net 30",
    "early_payment_discount_percentage": 0.02,
    "discount_period_days": 10,
    "net_period_days": 30,
    "line_items": [
        {"item_description": "Heavy Duty Steel Bolts", "quantity": 12.0, "unit_price": 50.00, "total_price": 600.00},  # Mismatch! Qty is 12, GR is 10
        {"item_description": "Industrial Lubricant Spray", "quantity": 5.0, "unit_price": 51.00, "total_price": 255.00}
    ]
}

MOCK_MISSING_PO = {
    "vendor_name": "Acme Industrial Supplies Ltd.",
    "invoice_number": "INV-2026-8945",
    "invoice_amount": 755.00,
    "purchase_order_number": "PO-UNKNOWN-99",  # Mismatch! PO doesn't exist
    "payment_terms": "2/10 Net 30",
    "early_payment_discount_percentage": 0.02,
    "discount_period_days": 10,
    "net_period_days": 30,
    "line_items": [
        {"item_description": "Heavy Duty Steel Bolts", "quantity": 10.0, "unit_price": 50.00, "total_price": 500.00},
        {"item_description": "Industrial Lubricant Spray", "quantity": 5.0, "unit_price": 51.00, "total_price": 255.00}
    ]
}


def parse_invoice_with_gemini(file_bytes: bytes, mime_type: str) -> dict:
    """Wrapper that sends document bytes to Gemini 1.5 Flash or falls back to simulator."""
    if not client:
        return MOCK_BASELINE

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
            model='gemini-1.5-flash',
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
        return MOCK_BASELINE


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
        # Auto-route to Finance Manager role
        finance_mgr = db.query(User).filter(
            User.organization_id == invoice.organization_id,
            User.role == "FINANCE_MANAGER"
        ).first()
        if finance_mgr:
            exc.predicted_approver_id = finance_mgr.id
            exc.assigned_approver_id = finance_mgr.id
            
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
        desc = ext_item.get("item_description", "").lower().strip()
        inv_qty = ext_item.get("quantity", 0.0)
        inv_price = ext_item.get("unit_price", 0.0)
        
        # Insert line item
        inv_line = InvoiceItem(
            invoice_id=invoice.id,
            item_description=ext_item.get("item_description", "Unknown Item"),
            quantity=Decimal(str(inv_qty)),
            unit_price=Decimal(str(inv_price)),
            total_price=Decimal(str(ext_item.get("total_price", 0.0)))
        )
        
        # Match PO item
        po_item = po_items_map.get(desc)
        # Fallback to loose substring match
        if not po_item:
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
                description=f"Line item '{ext_item.get('item_description')}' does not exist on Purchase Order {po.po_number}.",
                confidence_score=Decimal("80.00"),
                status="OPEN"
            )
            exceptions_raised.append(exc)
            
        db.add(inv_line)

    # 4. Handle Exceptions Routing & Final Status mapping
    if exceptions_raised:
        invoice.status = "EXCEPTION"
        # Map matching result based on primary exception type
        types = [e.exception_type for e in exceptions_raised]
        if "PRICE_VARIANCE" in types:
            invoice.matching_result = "PRICE_MISMATCH"
        elif "QUANTITY_VARIANCE" in types or "MISSING_GR" in types:
            invoice.matching_result = "QTY_MISMATCH"
        else:
            invoice.matching_result = "VARIANCE_FOUND"

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
                # Fallback to operations lead or finance manager with lower confidence (< 85%)
                ops_approver = db.query(User).filter(
                    User.organization_id == invoice.organization_id,
                    User.role == "APPROVER"
                ).first()
                if ops_approver:
                    exc.predicted_approver_id = ops_approver.id
                    exc.confidence_score = Decimal("75.00")
                    # Keep assigned_approver_id NULL for manual triage queue
                    exc.assigned_approver_id = None
            db.add(exc)
    else:
        invoice.status = "MATCHED"
        invoice.matching_result = "THREE_WAY_OK"
        
    db.commit()


# =========================================================================
# API ENDPOINTS
# =========================================================================

@app.post("/api/v1/invoices/upload", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def upload_invoice(
    file: UploadFile = File(...),
    clerk_org_id: str = Form("org_2tJ8XWn6qE"),
    db: Session = Depends(get_db)
):
    """
    Ingests invoice document, parses it with Gemini 1.5 Flash (or simulator fallback),
    runs the 3-Way Match Verification Engine, and computes capital optimization recommendations.
    """
    # 1. Fetch organization
    org = db.query(Organization).filter(Organization.clerk_org_id == clerk_org_id).first()
    if not org:
        raise HTTPException(
            status_code=404, 
            detail=f"Organization with Clerk ID '{clerk_org_id}' not found. Verify database initialization."
        )

    # 2. Extract Document Content
    file_bytes = await file.read()
    filename = file.filename.lower()
    
    # Smarter Simulation selection based on filename tags
    if not client:
        if "price_variance" in filename or "price_mismatch" in filename:
            parsed_data = MOCK_PRICE_VARIANCE
        elif "qty_variance" in filename or "quantity_variance" in filename or "qty_mismatch" in filename:
            parsed_data = MOCK_QTY_VARIANCE
        elif "missing_po" in filename or "no_po" in filename:
            parsed_data = MOCK_MISSING_PO
        else:
            parsed_data = MOCK_BASELINE
    else:
        parsed_data = parse_invoice_with_gemini(file_bytes, file.content_type)

    # 3. Create Invoice Instance
    # Calculate Due Date
    issue_date = date.today()
    net_days = parsed_data.get("net_period_days", 30)
    due_date = issue_date + timedelta(days=net_days)

    vendor_name = parsed_data.get("vendor_name", "Unknown Vendor")
    vendor = db.query(Vendor).filter(
        Vendor.organization_id == org.id,
        Vendor.name == vendor_name
    ).first()
    
    if not vendor:
        # Create vendor if missing
        vendor = Vendor(
            organization_id=org.id,
            name=vendor_name,
            email=f"billing@{vendor_name.lower().replace(' ', '')}.com",
            payment_terms=parsed_data.get("payment_terms", "Net 30"),
            default_discount_pct=Decimal(str(parsed_data.get("early_payment_discount_percentage", 0.00))),
            discount_days=parsed_data.get("discount_period_days", 0),
            net_days=parsed_data.get("net_period_days", 30),
            status="ACTIVE"
        )
        db.add(vendor)
        db.flush()

    invoice = Invoice(
        organization_id=org.id,
        vendor_id=vendor.id,
        invoice_number=parsed_data.get("invoice_number", f"INV-{uuid.uuid4().hex[:6].upper()}"),
        amount=Decimal(str(parsed_data.get("invoice_amount", 0.00))),
        tax_amount=Decimal("0.00"),
        issue_date=issue_date,
        due_date=due_date,
        payment_terms=parsed_data.get("payment_terms", "Net 30"),
        file_url=f"s3://vendorpulse-invoices/{file.filename}",
        ocr_raw_json=parsed_data,
        status="PENDING_MATCH",
        early_payment_status="CALCULATED"
    )
    
    # Store PO number field temporarily for matching process
    invoice.purchase_order_number = parsed_data.get("purchase_order_number")
    
    db.add(invoice)
    db.flush() # Populate invoice.id

    # 4. Trigger Matching Pipeline
    execute_3_way_match(db, invoice, parsed_data.get("line_items", []))

    # 5. Evaluate Early Payment Yield Recommendation (Treasury Optimizer)
    d = float(invoice.vendor.default_discount_pct)
    t_early = float(invoice.vendor.discount_days)
    t_net = float(invoice.vendor.net_days)
    days_saved = t_net - t_early

    if days_saved > 0 and d > 0:
        implied_annual_yield = (d / (1.0 - d)) * (365.0 / days_saved)
        # Compare with Organization Opportunity Cost of Capital
        if implied_annual_yield * 100.0 > float(org.cost_of_capital):
            invoice.early_payment_status = "OPTIMAL_PAID_EARLY"
        else:
            invoice.early_payment_status = "OPTIMAL_PAID_NET"
    else:
        invoice.early_payment_status = "SKIPPED"
        
    db.commit()
    db.refresh(invoice)
    return invoice


@app.get("/api/v1/invoices/{id}/matching")
def get_invoice_matching_detail(id: str, db: Session = Depends(get_db)):
    """
    Returns line-by-line comparison audits between Invoice, Purchase Order, and Goods Receipt.
    """
    invoice = db.query(Invoice).filter(Invoice.id == id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    po_items = []
    gr_items = []
    
    if invoice.purchase_order_id:
        po_items = db.query(PurchaseOrderItem).filter(
            PurchaseOrderItem.purchase_order_id == invoice.purchase_order_id
        ).all()
        
        gr = db.query(GoodsReceipt).filter(
            GoodsReceipt.purchase_order_id == invoice.purchase_order_id
        ).first()
        if gr:
            gr_items = db.query(GoodsReceiptItem).filter(
                GoodsReceiptItem.goods_receipt_id == gr.id
            ).all()

    # Structure line-by-line response
    response_items = []
    gr_map = {item.purchase_order_item_id: float(item.quantity_received) for item in gr_items}
    
    inv_items = db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice.id).all()
    
    for item in inv_items:
        po_item = next((p for p in po_items if p.id == item.purchase_order_item_id), None)
        po_qty = float(po_item.quantity) if po_item else None
        po_price = float(po_item.unit_price) if po_item else None
        received_qty = gr_map.get(item.purchase_order_item_id) if po_item else None
        
        response_items.append({
            "item_description": item.item_description,
            "invoiced": {
                "quantity": float(item.quantity),
                "unit_price": float(item.unit_price),
                "total_price": float(item.total_price)
            },
            "purchase_order": {
                "quantity": po_qty,
                "unit_price": po_price,
                "total_price": float(po_item.total_price) if po_item else None
            } if po_item else None,
            "goods_receipt": {
                "quantity_received": received_qty
            } if received_qty is not None else None
        })

    return {
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "status": invoice.status,
        "matching_result": invoice.matching_result,
        "line_by_line_matching": response_items
    }


@app.get("/api/v1/exceptions/pending", response_model=List[ExceptionResponse])
def get_pending_exceptions(
    assigned_approver_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Fetches unresolved matching exceptions. Supports filtering by assignee
    (enabling personalized approver inbox views).
    """
    query = db.query(InvoiceException).filter(InvoiceException.status == "OPEN")
    
    if assigned_approver_id:
        query = query.filter(InvoiceException.assigned_approver_id == assigned_approver_id)
        
    return query.all()


@app.post("/api/v1/exceptions/{id}/resolve")
def resolve_exception(
    id: str,
    payload: ExceptionResolveRequest,
    db: Session = Depends(get_db)
):
    """
    Resolves an invoice match exception, pushes the invoice into approval flow,
    and captures resolution telemetry to reinforce the AI routing classifier dataset.
    """
    # 1. Fetch Exception
    exc = db.query(InvoiceException).filter(InvoiceException.id == id).first()
    if not exc:
        raise HTTPException(status_code=404, detail="Exception record not found.")
        
    if exc.status == "RESOLVED":
        return {"status": "already_resolved", "invoice_id": exc.invoice_id}

    # Verify resolving user
    user = db.query(User).filter(User.clerk_user_id == payload.resolved_by_clerk_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Resolving user profile not found.")

    # 2. Update Exception Status
    exc.status = "RESOLVED"
    exc.resolved_by_id = user.id
    exc.resolution_notes = payload.notes
    exc.resolved_at = datetime.utcnow()

    # 3. Log AI Reinforcement Telemetry
    invoice = exc.invoice
    po = invoice.purchase_order
    dept = po.department if po else None
    vendor_id = invoice.vendor_id
    
    # Calculate variance amount
    po_total = float(po.total_amount) if po else 0.0
    inv_total = float(invoice.amount)
    variance = Decimal(str(abs(inv_total - po_total)))

    telemetry = ExceptionRoutingHistory(
        organization_id=invoice.organization_id,
        exception_type=exc.exception_type,
        vendor_id=vendor_id,
        amount=invoice.amount,
        variance_amount=variance,
        department=dept,
        final_approver_id=user.id
    )
    db.add(telemetry)

    # 4. Check if any other OPEN exceptions exist for this invoice
    remaining_exceptions = db.query(InvoiceException).filter(
        InvoiceException.invoice_id == invoice.id,
        InvoiceException.status == "OPEN"
    ).count()

    if remaining_exceptions == 0:
        # Move invoice status out of EXCEPTION into IN_APPROVAL
        invoice.status = "IN_APPROVAL"
        invoice.matching_result = "THREE_WAY_OK"
        
        # Log to Approval History
        history = ApprovalHistory(
            invoice_id=invoice.id,
            approver_id=user.id,
            action="APPROVED",
            comments=f"Exception resolved. Match approved. Resolution: {payload.notes}"
        )
        db.add(history)

    db.commit()
    return {
        "status": "resolved", 
        "invoice_id": invoice.id,
        "invoice_status": invoice.status
    }


@app.get("/api/v1/treasury/discount-matrix", response_model=List[TreasuryRecommendation])
def get_treasury_discount_matrix(
    clerk_org_id: str = "org_2tJ8XWn6qE",
    db: Session = Depends(get_db)
):
    """
    Returns cash optimization opportunities for outstanding invoices, sorted by implied discount yield,
    allowing finance managers to maximize Cash Flow Economic Value Added (EVA).
    """
    org = db.query(Organization).filter(Organization.clerk_org_id == clerk_org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization profile not found.")

    invoices = db.query(Invoice).filter(
        Invoice.organization_id == org.id,
        Invoice.status.in_(["MATCHED", "IN_APPROVAL", "APPROVED"])
    ).all()

    matrix = []
    wacc = float(org.cost_of_capital)

    for inv in invoices:
        d = float(inv.vendor.default_discount_pct)
        t_early = float(inv.vendor.discount_days)
        t_net = float(inv.vendor.net_days)
        days_saved = t_net - t_early
        
        amount = float(inv.amount)

        if days_saved > 0 and d > 0:
            implied_yield = (d / (1.0 - d)) * (365.0 / days_saved) * 100.0
            instant_savings = amount * d
            # EVA = Savings - (Opportunity Cost of Capital * Amount * Days Saved / 365)
            capital_cost_of_early_pay = (wacc / 100.0) * amount * (days_saved / 365.0)
            eva = instant_savings - capital_cost_of_early_pay
        else:
            implied_yield = 0.0
            instant_savings = 0.0
            eva = 0.0

        recommendation = "HOLD PAYMENT"
        if implied_yield > wacc and eva > 0:
            recommendation = "PAY EARLY"

        matrix.append(
            TreasuryRecommendation(
                invoice_id=str(inv.id),
                invoice_number=inv.invoice_number,
                vendor_name=inv.vendor.name,
                amount=amount,
                due_date=inv.due_date,
                payment_terms=inv.payment_terms,
                implied_annual_yield_pct=round(implied_yield, 2),
                instant_cash_saved=round(instant_savings, 2),
                recommendation=recommendation,
                economic_value_added=round(eva, 2)
            )
        )

    # Sort matrix by highest yield first
    matrix.sort(key=lambda x: x.implied_annual_yield_pct, reverse=True)
    return matrix


@app.get("/api/v1/analytics/cashflow", response_model=List[CashFlowForecastItem])
def get_cashflow_forecast(
    clerk_org_id: str = "org_2tJ8XWn6qE",
    db: Session = Depends(get_db)
):
    """
    Returns weekly accounts payable cash requirements forecast.
    Compares early payment layout (paying on Day 10) against standard layout (paying on Day 30).
    """
    org = db.query(Organization).filter(Organization.clerk_org_id == clerk_org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization profile not found.")

    invoices = db.query(Invoice).filter(
        Invoice.organization_id == org.id,
        Invoice.status != "REJECTED"
    ).all()

    # Group by week starts
    forecast_data = {}
    today = date.today()
    
    # Generate weekly buckets for the next 4 weeks
    for i in range(4):
        week_start = today + timedelta(days=(i * 7) - today.weekday())
        forecast_data[week_start] = {
            "early": 0.0,
            "net": 0.0,
            "savings": 0.0
        }

    for inv in invoices:
        amount = float(inv.amount)
        d = float(inv.vendor.default_discount_pct)
        t_early = inv.vendor.discount_days
        t_net = inv.vendor.net_days
        
        # Calculate early payment date and net payment date
        early_pay_date = inv.issue_date + timedelta(days=t_early)
        net_pay_date = inv.issue_date + timedelta(days=t_net)

        # Map to weekly buckets
        early_week = early_pay_date - timedelta(days=early_pay_date.weekday())
        net_week = net_pay_date - timedelta(days=net_pay_date.weekday())

        # Early Payment scenario
        if early_week in forecast_data:
            discounted_amt = amount * (1.0 - d)
            forecast_data[early_week]["early"] += discounted_amt
            forecast_data[early_week]["savings"] += (amount * d)
            
        # Net Payment scenario
        if net_week in forecast_data:
            forecast_data[net_week]["net"] += amount

    response = []
    for w_start, vals in sorted(forecast_data.items()):
        response.append(
            CashFlowForecastItem(
                week_start=w_start,
                early_payment_outflow=round(vals["early"], 2),
                net_payment_outflow=round(vals["net"], 2),
                cash_savings=round(vals["savings"], 2)
            )
        )

    return response


# =========================================================================
# MAIN EXECUTION BLOCK (FOR DEV RUNS)
# =========================================================================

if __name__ == "__main__":
    import uvicorn
    # Start ASGI Server
    print("[RUN] Launching API server on http://localhost:8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
