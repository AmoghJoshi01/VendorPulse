import os
import uuid
import json
import time
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
from google.genai import types
from document_ai_ocr import DocumentAIExtractor

load_dotenv()

app = FastAPI(title="VendorPulse API", description="AI-powered AP Automation Backend")

# Enable CORS for frontend Vite development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development, allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = os.path.join(os.path.dirname(__file__), "db.json")

# --- INITIAL SEED DATA ---
DEFAULT_VENDORS = [
    {
        "id": "v1",
        "name": "Acme Industrial Supplies Ltd.",
        "email": "ap@acmeindustrial.com",
        "payment_terms": "2/10 Net 30",
        "default_discount_pct": 0.02,
        "discount_days": 10,
        "net_days": 30,
        "bank_name": "Chase Bank",
        "bank_routing_number": "021000021",
        "bank_account_number": "******4829",
        "status": "ACTIVE"
    },
    {
        "id": "v2",
        "name": "Globex Logistics",
        "email": "billing@globex.com",
        "payment_terms": "Net 30",
        "default_discount_pct": 0.0,
        "discount_days": 0,
        "net_days": 30,
        "bank_name": "Bank of America",
        "bank_routing_number": "026009593",
        "bank_account_number": "******9928",
        "status": "ACTIVE"
    },
    {
        "id": "v3",
        "name": "Initech IT Solutions",
        "email": "accounts@initech.com",
        "payment_terms": "1/15 Net 45",
        "default_discount_pct": 0.01,
        "discount_days": 15,
        "net_days": 45,
        "bank_name": "Wells Fargo",
        "bank_routing_number": "121000248",
        "bank_account_number": "******1102",
        "status": "ACTIVE"
    },
    {
        "id": "v4",
        "name": "Olivia Wilson Consulting",
        "email": "olivia@wilsonconsulting.co",
        "payment_terms": "3/10 Net 30",
        "default_discount_pct": 0.03,
        "discount_days": 10,
        "net_days": 30,
        "bank_name": "CitiBank",
        "bank_routing_number": "021000089",
        "bank_account_number": "******8832",
        "status": "ACTIVE"
    }
]

DEFAULT_POS = [
    {
        "id": "po1",
        "po_number": "PO-99541",
        "vendor_name": "Acme Industrial Supplies Ltd.",
        "issue_date": "2026-06-15",
        "total_amount": 755.00,
        "department": "Operations",
        "status": "OPEN",
        "items": [
            {"description": "Industrial Safety Gloves", "quantity": 10, "unit_price": 25.50, "total": 255.00},
            {"description": "Heavy Duty Steel Boots", "quantity": 5, "unit_price": 100.00, "total": 500.00}
        ]
    },
    {
        "id": "po2",
        "po_number": "PO-99542",
        "vendor_name": "Globex Logistics",
        "issue_date": "2026-06-20",
        "total_amount": 1200.00,
        "department": "Supply Chain",
        "status": "OPEN",
        "items": [
            {"description": "Freight & Warehousing Services", "quantity": 1, "unit_price": 1200.00, "total": 1200.00}
        ]
    },
    {
        "id": "po3",
        "po_number": "PO-99543",
        "vendor_name": "Initech IT Solutions",
        "issue_date": "2026-06-25",
        "total_amount": 5000.00,
        "department": "Information Technology",
        "status": "OPEN",
        "items": [
            {"description": "Enterprise Software Licensing", "quantity": 1, "unit_price": 5000.00, "total": 5000.00}
        ]
    }
]

DEFAULT_RECEIPTS = [
    {
        "id": "gr1",
        "receipt_number": "GR-88421",
        "po_number": "PO-99541",
        "received_date": "2026-06-18",
        "status": "RECEIVED",
        "items": [
            {"description": "Industrial Safety Gloves", "quantity": 10},
            {"description": "Heavy Duty Steel Boots", "quantity": 5}
        ]
    },
    {
        "id": "gr2",
        "receipt_number": "GR-88422",
        "po_number": "PO-99542",
        "received_date": "2026-06-22",
        "status": "RECEIVED",
        "items": [
            {"description": "Freight & Warehousing Services", "quantity": 1}
        ]
    },
    {
        "id": "gr3",
        "receipt_number": "GR-88423",
        "po_number": "PO-99543",
        "received_date": "2026-06-28",
        "status": "RECEIVED",
        "items": [
            {"description": "Enterprise Software Licensing", "quantity": 1}
        ]
    }
]

DEFAULT_INVOICES = [
    {
        "id": "inv_demo_1",
        "vendor_name": "Acme Industrial Supplies Ltd.",
        "invoice_number": "INV-2026-8942",
        "invoice_amount": 755.00,
        "purchase_order_number": "PO-99541",
        "payment_terms": "2/10 Net 30",
        "early_payment_discount_percentage": 0.02,
        "discount_period_days": 10,
        "net_period_days": 30,
        "status": "APPROVED",
        "matching_result": "THREE_WAY_OK",
        "early_payment_status": "OPTIMAL_PAID_EARLY",
        "implied_annual_yield": 37.24, # (0.02/0.98) * (365/20) * 100
        "cash_savings": 15.10,
        "created_at": "2026-07-01T10:00:00Z",
        "due_date": "2026-07-31",
        "early_pay_date": "2026-07-11"
    },
    {
        "id": "inv_demo_2",
        "vendor_name": "Globex Logistics",
        "invoice_number": "INV-2026-9051",
        "invoice_amount": 1200.00,
        "purchase_order_number": "PO-99542",
        "payment_terms": "Net 30",
        "early_payment_discount_percentage": 0.0,
        "discount_period_days": 0,
        "net_period_days": 30,
        "status": "PENDING_MATCH",
        "matching_result": "THREE_WAY_OK",
        "early_payment_status": "CALCULATED",
        "implied_annual_yield": 0.0,
        "cash_savings": 0.0,
        "created_at": "2026-07-05T14:30:00Z",
        "due_date": "2026-08-04",
        "early_pay_date": None
    },
    {
        "id": "inv_demo_3",
        "vendor_name": "Initech IT Solutions",
        "invoice_number": "INV-2026-9113",
        "invoice_amount": 5400.00, # PO total is 5000.00 -> Price mismatch!
        "purchase_order_number": "PO-99543",
        "payment_terms": "1/15 Net 45",
        "early_payment_discount_percentage": 0.01,
        "discount_period_days": 15,
        "net_period_days": 45,
        "status": "EXCEPTION",
        "matching_result": "PRICE_MISMATCH",
        "early_payment_status": "CALCULATED",
        "implied_annual_yield": 12.29, # (0.01/0.99) * (365/30) * 100
        "cash_savings": 54.00,
        "created_at": "2026-07-08T09:15:00Z",
        "due_date": "2026-08-22",
        "early_pay_date": "2026-07-23",
        "exception": {
            "exception_type": "PRICE_VARIANCE",
            "description": "Invoice total ($5,400.00) exceeds PO-99543 total ($5,000.00) by $400.00 (8.0% variance, limit is 0.5%).",
            "confidence_score": 92.4,
            "predicted_approver": "Bill Lumbergh (IT Director)",
            "status": "OPEN"
        }
    }
]

DEFAULT_SETTINGS = {
    "cost_of_capital": 6.0,
    "minimum_liquidity_threshold": 25000.0,
    "cash_balance": 150000.0
}

# --- DATABASE HELPER FUNCTIONS ---
def load_db() -> Dict[str, Any]:
    if not os.path.exists(DB_FILE):
        db_data = {
            "settings": DEFAULT_SETTINGS,
            "vendors": DEFAULT_VENDORS,
            "pos": DEFAULT_POS,
            "receipts": DEFAULT_RECEIPTS,
            "invoices": DEFAULT_INVOICES
        }
        save_db(db_data)
        return db_data
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except Exception:
        # fallback
        return {
            "settings": DEFAULT_SETTINGS,
            "vendors": DEFAULT_VENDORS,
            "pos": DEFAULT_POS,
            "receipts": DEFAULT_RECEIPTS,
            "invoices": DEFAULT_INVOICES
        }

def save_db(data: Dict[str, Any]):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- MODELS ---
class SettingsUpdate(BaseModel):
    cost_of_capital: float
    minimum_liquidity_threshold: float
    cash_balance: float

class ExceptionResolution(BaseModel):
    action: str # 'PAY_OVERRIDE', 'REQUEST_REVISED', 'WRITE_OFF'
    comments: Optional[str] = ""

# --- API ROUTES ---

@app.get("/api/settings")
def get_settings():
    db = load_db()
    return db["settings"]

@app.post("/api/settings")
def update_settings(settings: SettingsUpdate):
    db = load_db()
    db["settings"] = settings.model_dump()
    save_db(db)
    # Recalculate invoice savings recommendation based on new settings
    recalculate_recommendations(db)
    return db["settings"]

def recalculate_recommendations(db):
    cost_of_capital = db["settings"]["cost_of_capital"]
    for invoice in db["invoices"]:
        if invoice["status"] in ["PENDING_MATCH", "EXCEPTION", "APPROVED"]:
            yield_val = invoice["implied_annual_yield"]
            if yield_val > cost_of_capital:
                invoice["early_payment_status"] = "OPTIMAL_PAID_EARLY"
            else:
                invoice["early_payment_status"] = "OPTIMAL_PAID_NET"
    save_db(db)

@app.get("/api/vendors")
def get_vendors():
    db = load_db()
    return db["vendors"]

@app.get("/api/pos")
def get_pos():
    db = load_db()
    return db["pos"]

@app.get("/api/invoices")
def get_invoices():
    db = load_db()
    return db["invoices"]

@app.post("/api/invoices/{invoice_id}/approve")
def approve_invoice(invoice_id: str):
    db = load_db()
    for inv in db["invoices"]:
        if inv["id"] == invoice_id:
            inv["status"] = "APPROVED"
            save_db(db)
            return inv
    raise HTTPException(status_code=404, detail="Invoice not found")

@app.post("/api/invoices/{invoice_id}/pay")
def pay_invoice(invoice_id: str):
    db = load_db()
    for inv in db["invoices"]:
        if inv["id"] == invoice_id:
            inv["status"] = "PAID"
            # Deduct from cash balance
            db["settings"]["cash_balance"] -= inv["invoice_amount"]
            save_db(db)
            return inv
    raise HTTPException(status_code=404, detail="Invoice not found")

@app.post("/api/invoices/{invoice_id}/reject")
def reject_invoice(invoice_id: str):
    db = load_db()
    for inv in db["invoices"]:
        if inv["id"] == invoice_id:
            inv["status"] = "REJECTED"
            save_db(db)
            return inv
    raise HTTPException(status_code=404, detail="Invoice not found")

@app.post("/api/invoices/{invoice_id}/resolve-exception")
def resolve_exception(invoice_id: str, resolution: ExceptionResolution):
    db = load_db()
    for inv in db["invoices"]:
        if inv["id"] == invoice_id:
            if "exception" in inv:
                inv["exception"]["status"] = "RESOLVED"
                inv["exception"]["resolution_action"] = resolution.action
                inv["exception"]["comments"] = resolution.comments
                
                if resolution.action == "PAY_OVERRIDE":
                    inv["status"] = "APPROVED"
                elif resolution.action == "REQUEST_REVISED":
                    inv["status"] = "REJECTED"
                else:
                    inv["status"] = "APPROVED" # Write off variance and approve
                
                save_db(db)
                return inv
            raise HTTPException(status_code=400, detail="Invoice does not have an open exception")
    raise HTTPException(status_code=404, detail="Invoice not found")

# --- MOCK INVOICE EXTRACTION FALLBACK ---
MOCK_INVOICE_DATA_SUITE = {
    "acme": {
        "vendor_name": "Acme Industrial Supplies Ltd.",
        "invoice_number": "INV-2026-8942",
        "invoice_amount": 755.00,
        "purchase_order_number": "PO-99541",
        "payment_terms": "2/10 Net 30",
        "early_payment_discount_percentage": 0.02,
        "discount_period_days": 10,
        "net_period_days": 30
    },
    "globex": {
        "vendor_name": "Globex Logistics",
        "invoice_number": "INV-2026-9051",
        "invoice_amount": 1200.00,
        "purchase_order_number": "PO-99542",
        "payment_terms": "Net 30",
        "early_payment_discount_percentage": 0.0,
        "discount_period_days": 0,
        "net_period_days": 30
    },
    "initech": {
        "vendor_name": "Initech IT Solutions",
        "invoice_number": "INV-2026-9113",
        "invoice_amount": 5400.00,
        "purchase_order_number": "PO-99543",
        "payment_terms": "1/15 Net 45",
        "early_payment_discount_percentage": 0.01,
        "discount_period_days": 15,
        "net_period_days": 45
    },
    "olivia": {
        "vendor_name": "Olivia Wilson Consulting",
        "invoice_number": "INV-2026-0412",
        "invoice_amount": 2500.00,
        "purchase_order_number": "N/A", # No PO match!
        "payment_terms": "3/10 Net 30",
        "early_payment_discount_percentage": 0.03,
        "discount_period_days": 10,
        "net_period_days": 30
    }
}

# --- PROCESS INVOICE UPLOAD & AI OCR & MATCHING ---
@app.post("/api/invoices/upload")
def upload_invoice(file: UploadFile = File(...)):
    db = load_db()
    
    # 1. READ FILE BYTES
    file_bytes = file.file.read()
    file_name = file.filename.lower()
    
    # Try to find a matches in name to return appropriate mock flow
    mock_key = "olivia"
    if "acme" in file_name:
        mock_key = "acme"
    elif "globex" in file_name:
        mock_key = "globex"
    elif "initech" in file_name:
        mock_key = "initech"
    
    invoice_data = MOCK_INVOICE_DATA_SUITE[mock_key].copy()
    
    # 2. RUN LIVE AI EXTRACTION
    use_live_ai = False
    
    # Check if Google Document AI is configured
    gcp_project = os.environ.get("GCP_PROJECT_ID")
    docai_processor = os.environ.get("DOCUMENT_AI_PROCESSOR_ID")
    
    # Identify MIME Type
    mime = "application/pdf"
    if file_name.endswith(".png"):
        mime = "image/png"
    elif file_name.endswith(".jpg") or file_name.endswith(".jpeg"):
        mime = "image/jpeg"
        
    if gcp_project and docai_processor:
        try:
            extractor = DocumentAIExtractor()
            parsed = extractor.process_document_bytes(file_bytes, mime)
            
            # Merge and validate
            for key in ["vendor_name", "invoice_number", "invoice_amount", "purchase_order_number", "payment_terms"]:
                if key in parsed:
                    invoice_data[key] = parsed[key]
            for key in ["early_payment_discount_percentage", "discount_period_days", "net_period_days"]:
                if key in parsed:
                    invoice_data[key] = float(parsed[key]) if key == "early_payment_discount_percentage" else int(parsed[key])
            
            use_live_ai = True
            print("[Backend] Successfully processed invoice using Google Document AI!")
        except Exception as e:
            print(f"DEBUG BACKEND LIVE DOCUMENT AI ERROR: {e}")
            use_live_ai = False
            
    # Fallback to Gemini API if Document AI is not set or failed
    if not use_live_ai:
        API_KEY = os.environ.get("GEMINI_API_KEY")
        if API_KEY and len(API_KEY) > 5:
            try:
                client = genai.Client()
                prompt = """
                You are an expert accounts payable auditing system. Analyze the uploaded invoice document.
                Extract the data into a valid JSON object matching this schema:
                {
                    "vendor_name": "Extract the sender/seller name from header",
                    "invoice_number": "Extract the invoice number ID",
                    "invoice_amount": Extract total bill value as a raw number/float (e.g. 755.00),
                    "purchase_order_number": "Look for PO number, if none found use 'N/A' or 'None'",
                    "payment_terms": "Look for terms like Net 30, Cash, 2/10 Net 30. If missing use 'Net 30'",
                    "early_payment_discount_percentage": Look for early payment discount percentage as a decimal (e.g. 0.02 for 2%),
                    "discount_period_days": Look for early discount days (e.g. 10 for /10 in '2/10 Net 30'),
                    "net_period_days": Look for total net days (e.g. 30 for Net 30)
                }
                Return ONLY the raw JSON structure. Do not wrap it in markdown block fences or backticks.
                """
                
                response = client.models.generate_content(
                    model='gemini-1.5-flash',
                    contents=[
                        types.Part.from_bytes(data=file_bytes, mime_type=mime),
                        prompt
                    ]
                )
                
                clean_text = response.text.strip()
                if clean_text.startswith("```json"):
                    clean_text = clean_text.split("```json")[1].split("```")[0].strip()
                elif clean_text.startswith("```"):
                    clean_text = clean_text.split("```")[1].split("```")[0].strip()
                    
                parsed = json.loads(clean_text)
                # Merge and validate
                for key in ["vendor_name", "invoice_number", "invoice_amount", "purchase_order_number", "payment_terms"]:
                    if key in parsed:
                        invoice_data[key] = parsed[key]
                for key in ["early_payment_discount_percentage", "discount_period_days", "net_period_days"]:
                    if key in parsed:
                        invoice_data[key] = float(parsed[key]) if key == "early_payment_discount_percentage" else int(parsed[key])
                
                use_live_ai = True
            except Exception as e:
                print(f"DEBUG BACKEND LIVE GEMINI ERROR: {e}")
                use_live_ai = False

    # 3. 3-WAY MATCHING ENGINE & EXCEPTION ROUTING
    po_num = invoice_data.get("purchase_order_number", "N/A")
    matching_result = "THREE_WAY_OK"
    status = "PENDING_MATCH"
    exception_obj = None
    
    # Cross reference with PO Database
    matched_po = None
    if po_num and po_num != "N/A" and po_num != "None":
        for po in db["pos"]:
            if po["po_number"] == po_num:
                matched_po = po
                break
                
    if not matched_po:
        # Exception: Missing PO Reference or Unknown PO
        if po_num and po_num != "N/A":
            matching_result = "NO_PO_FOUND"
            status = "EXCEPTION"
            exception_obj = {
                "exception_type": "MISSING_PO",
                "description": f"Invoice references Purchase Order '{po_num}', but this PO was not found in the ledger database.",
                "confidence_score": 88.0,
                "predicted_approver": "Jane Doe (AP Supervisor)",
                "status": "OPEN"
            }
        else:
            matching_result = "NO_PO_FOUND"
            status = "EXCEPTION"
            exception_obj = {
                "exception_type": "MISSING_PO",
                "description": f"Invoice has no Purchase Order reference. Manual routing required.",
                "confidence_score": 67.5,
                "predicted_approver": "Unassigned central queue",
                "status": "OPEN"
            }
    else:
        # We have a PO, check price variance
        invoice_total = invoice_data["invoice_amount"]
        po_total = matched_po["total_amount"]
        
        # 0.5% tolerance limit (or max $10)
        variance = invoice_total - po_total
        tolerance_limit = max(po_total * 0.005, 10.0)
        
        if variance > tolerance_limit:
            matching_result = "PRICE_MISMATCH"
            status = "EXCEPTION"
            percentage = (variance / po_total) * 100
            exception_obj = {
                "exception_type": "PRICE_VARIANCE",
                "description": f"Invoice total (${invoice_total:,.2f}) exceeds {po_num} total (${po_total:,.2f}) by ${variance:,.2f} ({percentage:.1f}% variance). Maximum tolerance is ${tolerance_limit:,.2f}.",
                "confidence_score": 91.2,
                "predicted_approver": f"{matched_po['department']} Director",
                "status": "OPEN"
            }
        else:
            # Check for quantity mismatch by matching items if receipt exists
            matched_gr = None
            for gr in db["receipts"]:
                if gr["po_number"] == po_num:
                    matched_gr = gr
                    break
            
            if not matched_gr:
                matching_result = "QTY_MISMATCH"
                status = "EXCEPTION"
                exception_obj = {
                    "exception_type": "MISSING_GR",
                    "description": f"Goods receipt not found for Purchase Order '{po_num}'. Cannot verify if items were received.",
                    "confidence_score": 79.0,
                    "predicted_approver": "Warehouse Operations Manager",
                    "status": "OPEN"
                }
            else:
                # We can mock verification of items - everything matches
                matching_result = "THREE_WAY_OK"
                status = "PENDING_MATCH" # Will shift to APPROVED/READY if approved

    # 4. EARLY PAYMENT DISCOUNT OPTIMIZATION MATH
    d_pct = invoice_data.get("early_payment_discount_percentage", 0.0)
    discount_days = invoice_data.get("discount_period_days", 0)
    net_days = invoice_data.get("net_period_days", 30)
    
    days_saved = net_days - discount_days
    if days_saved > 0 and d_pct > 0:
        implied_annual_yield = (d_pct / (1 - d_pct)) * (365 / days_saved) * 100
        cash_savings = invoice_data["invoice_amount"] * d_pct
    else:
        implied_annual_yield = 0.0
        cash_savings = 0.0
        
    cost_of_capital = db["settings"]["cost_of_capital"]
    early_payment_status = "CALCULATED"
    if implied_annual_yield > cost_of_capital:
        early_payment_status = "OPTIMAL_PAID_EARLY"
    else:
        early_payment_status = "OPTIMAL_PAID_NET"

    # Form dates
    created_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    due_date = time.strftime("%Y-%m-%d", time.localtime(time.time() + net_days * 86400))
    early_pay_date = None
    if discount_days > 0:
        early_pay_date = time.strftime("%Y-%m-%d", time.localtime(time.time() + discount_days * 86400))

    new_invoice = {
        "id": "inv_" + uuid.uuid4().hex[:12],
        "vendor_name": invoice_data["vendor_name"],
        "invoice_number": invoice_data["invoice_number"],
        "invoice_amount": invoice_data["invoice_amount"],
        "purchase_order_number": po_num,
        "payment_terms": invoice_data["payment_terms"],
        "early_payment_discount_percentage": d_pct,
        "discount_period_days": discount_days,
        "net_period_days": net_days,
        "status": status,
        "matching_result": matching_result,
        "early_payment_status": early_payment_status,
        "implied_annual_yield": round(implied_annual_yield, 2),
        "cash_savings": round(cash_savings, 2),
        "created_at": created_str,
        "due_date": due_date,
        "early_pay_date": early_pay_date,
        "is_live_ai": use_live_ai
    }
    
    if exception_obj:
        new_invoice["exception"] = exception_obj
        
    db["invoices"].insert(0, new_invoice)
    save_db(db)
    
    return new_invoice

# --- ANALYTICS AND FORECASTING ---
@app.get("/api/analytics")
def get_analytics():
    db = load_db()
    invoices = db["invoices"]
    settings = db["settings"]
    
    # Calculate Total AP
    total_ap = sum(inv["invoice_amount"] for inv in invoices if inv["status"] in ["PENDING_MATCH", "EXCEPTION", "APPROVED"])
    
    # Calculate total early discount savings realized vs potential
    realized_savings = sum(inv["cash_savings"] for inv in invoices if inv["status"] == "PAID" and inv["early_payment_status"] == "OPTIMAL_PAID_EARLY")
    potential_savings = sum(inv["cash_savings"] for inv in invoices if inv["status"] in ["PENDING_MATCH", "EXCEPTION", "APPROVED"] and inv["early_payment_status"] == "OPTIMAL_PAID_EARLY")
    
    # Calculate DPO
    # Formula: DPO = (Average AP / COGS) * 365. Let's mock a monthly COGS of $600,000.
    cogs_monthly = 600000.0
    dpo = round((total_ap / cogs_monthly) * 30, 1) if total_ap > 0 else 32.5
    
    # Cash flow requirements over 30 days
    # Week 1, 2, 3, 4
    week_needs_early = [0.0, 0.0, 0.0, 0.0]
    week_needs_net = [0.0, 0.0, 0.0, 0.0]
    
    for inv in invoices:
        if inv["status"] not in ["PAID", "REJECTED"]:
            # Net due
            net_days = inv["net_period_days"]
            net_week = min(net_days // 7, 3)
            week_needs_net[net_week] += inv["invoice_amount"]
            
            # Early due
            if inv["early_payment_status"] == "OPTIMAL_PAID_EARLY" and inv["discount_period_days"] > 0:
                disc_days = inv["discount_period_days"]
                disc_week = min(disc_days // 7, 3)
                # If paid early, amount is discounted
                discounted_amt = inv["invoice_amount"] * (1 - inv["early_payment_discount_percentage"])
                week_needs_early[disc_week] += discounted_amt
            else:
                # If not eligible or yield < cost of capital, we pay at net date in both scenarios
                week_needs_early[net_week] += inv["invoice_amount"]
                
    return {
        "total_ap": total_ap,
        "realized_savings": round(realized_savings, 2),
        "potential_savings": round(potential_savings, 2),
        "dpo": dpo,
        "cash_balance": settings["cash_balance"],
        "cost_of_capital": settings["cost_of_capital"],
        "forecast": {
            "categories": ["Week 1", "Week 2", "Week 3", "Week 4"],
            "early_payment_schedule": [round(val, 2) for val in week_needs_early],
            "net_payment_schedule": [round(val, 2) for val in week_needs_net]
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
