# VendorPulse Local Setup & Execution Guide

This guide details the step-by-step instructions to set up, configure, initialize, and run the **VendorPulse** AP automation and treasury optimization platform locally.

---

## 1. Prerequisites

Ensure your development machine has the following tools installed:
* **Python**: Version 3.10 or higher.
* **Pip**: Python package installer (typically bundled with Python).
* **Git**: To clone/manage the repository.

---

## 2. Environment Configuration

1. **Create the Environment File**:
   In the root directory of the project, verify or create a file named `.env`:
   ```bash
   GEMINI_API_KEY="your-google-gemini-api-key-here"
   DATABASE_URL="sqlite:///vendorpulse.db"
   ```
   * *Note: If `GEMINI_API_KEY` is omitted, the application automatically triggers its **Intelligent Simulator Mode**, matching baseline ledger entries seamlessly without making network requests.*
   * *Note: `DATABASE_URL` defaults to a local SQLite database (`vendorpulse.db` in the project root) for quick setup, but you can configure a PostgreSQL database URL if running in production.*

---

## 3. Backend Installation & Setup

We recommend using a Python virtual environment to manage dependencies.

1. **Create a Virtual Environment**:
   Navigate to the project root and create a virtual environment:
   ```powershell
   # On Windows (PowerShell)
   python -m venv .venv
   
   # On macOS / Linux
   python3 -m venv .venv
   ```

2. **Activate the Virtual Environment**:
   ```powershell
   # On Windows (PowerShell)
   .venv\Scripts\Activate.ps1
   
   # On Windows (Command Prompt)
   .venv\Scripts\activate.bat
   
   # On macOS / Linux
   source .venv/bin/activate
   ```

3. **Install Dependencies**:
   Install all required libraries mapped in the [backend/requirements.txt](file:///D:/VendorPulse/backend/requirements.txt):
   ```bash
   pip install -r backend/requirements.txt
   ```

---

## 4. Database Initialization & Seeding

Before running the application services, you must compile the schemas and populate the baseline demo values.

1. **Initialize the Database**:
   Run the database module directly:
   ```bash
   python backend/database.py
   ```
   This will:
   * Build all PostgreSQL/SQLite tables (`organizations`, `users`, `vendors`, `purchase_orders`, `purchase_order_items`, `goods_receipts`, `goods_receipt_items`, `invoices`, `invoice_items`, `exceptions`, `approval_rules`, `approval_history`, `exception_routing_history`).
   * Seed the database with default organizations, users (finance managers and approvers), vendors, purchase orders, goods receipts, and itemized line items.

---

## 5. Running the Applications

VendorPulse consists of two primary services: the **FastAPI Web API Server** and the **Streamlit Interactive Pitch Dashboard**.

### Service A: FastAPI Backend Server (Production APIs)
This is the core business logic server handling document ingestion, 3-way matching, routing, and cash forecasting.

1. **Start the API Server**:
   Navigate to the `backend` folder and run `main.py`:
   ```bash
   cd backend
   python main.py
   ```
   * The API server will boot on **`http://localhost:8000`** with hot-reloading enabled.
   * **Swagger Interactive Documentation**: View and test the REST endpoints at **`http://localhost:8000/docs`**.

### Service B: Streamlit Pitch Dashboard (Showcase Demo)
This dashboard provides a rich visual tool to pitch the AP automation and Capital Optimizer decision matrix.

1. **Start the Dashboard**:
   From the project root (ensure your virtual environment is active), run:
   ```bash
   streamlit run backend/app.py
   ```
   * The web application will launch automatically in your browser at **`http://localhost:8501`**.

---

## 6. How to Test the Exception Workflows (Simulator Mode)

If you are running in **Simulator Mode** (without a live `GEMINI_API_KEY`), the backend has a smart parser that lets you test different edge cases based on the filename you upload in the document ingestion field:

1. **Perfect 3-Way Match**:
   * **Action**: Upload any standard invoice image/PDF (e.g. `invoice_normal.pdf`).
   * **Result**: Status maps to `MATCHED` and prompts treasury pay early optimization recommendations.
2. **Missing Purchase Order Link**:
   * **Action**: Upload a file containing the keyword `missing_po` (e.g. `missing_po_invoice.png`).
   * **Result**: Status maps to `EXCEPTION` and triggers a `MISSING_PO` exception block.
3. **Unit Price Discrepancy**:
   * **Action**: Upload a file containing the keyword `price_variance` (e.g. `invoice_price_variance.jpg`).
   * **Result**: Raises a `PRICE_VARIANCE` exception for line items and routes them to the Finance manager.
4. **Quantity Discrepancy**:
   * **Action**: Upload a file containing the keyword `qty_variance` (e.g. `qty_variance_bill.png`).
   * **Result**: Raises a `QUANTITY_VARIANCE` exception comparing invoice vs goods receipt and routes it to the department approver.
