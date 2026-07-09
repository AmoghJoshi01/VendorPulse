import os
import re
import json
from typing import Dict, Any, Optional, List
from google.cloud import documentai_v1 as documentai
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

class DocumentAIExtractor:
    """
    A robust, production-ready document extraction utility that leverages
    Google Cloud Document AI (Invoice Parser/OCR) and Gemini.
    """
    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        processor_id: Optional[str] = None
    ):
        # Read from constructor parameters or fallback to env variables
        self.project_id = project_id or os.environ.get("GCP_PROJECT_ID")
        self.location = location or os.environ.get("GCP_LOCATION", "us")
        self.processor_id = processor_id or os.environ.get("DOCUMENT_AI_PROCESSOR_ID")
        
        # Check if Google GenAI key is available for fallback layout normalization
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY")
        self._document_ai_client = None

    @property
    def client(self):
        """Lazy loader for Document AI Client to avoid instantiation overhead."""
        if self._document_ai_client is None:
            # Document AI utilizes standard GOOGLE_APPLICATION_CREDENTIALS environment variable
            # pointing to the service account JSON key file.
            self._document_ai_client = documentai.DocumentProcessorServiceClient()
        return self._document_ai_client

    def process_document_bytes(self, file_bytes: bytes, mime_type: str) -> Dict[str, Any]:
        """
        Sends document bytes to Google Document AI, processes response entities,
        and returns a normalized AP data dict.
        """
        if not self.project_id or not self.processor_id:
            raise ValueError(
                "GCP_PROJECT_ID and DOCUMENT_AI_PROCESSOR_ID must be set. "
                "Ensure they are configured in your environmental variables or passed in constructor."
            )

        try:
            # Build full processor path name
            name = self.client.processor_path(self.project_id, self.location, self.processor_id)

            # Package raw bytes in Document AI RawDocument container
            raw_document = documentai.RawDocument(content=file_bytes, mime_type=mime_type)

            # Request structure
            request = documentai.ProcessRequest(name=name, raw_document=raw_document)
            
            print(f"[DocumentAI] Processing document via processor: {self.processor_id}...")
            result = self.client.process_document(request=request)
            document = result.document

            # Determine processor type from result or try parsing structured entities first
            if document.entities:
                print("[DocumentAI] Structured entities detected. Running Specialised Parser parser...")
                return self._parse_structured_entities(document.entities, document.text)
            else:
                print("[DocumentAI] No structured entities. Running Generic OCR + LLM Normalizer Hybrid flow...")
                return self._parse_generic_ocr_with_llm(document.text)

        except Exception as e:
            print(f"[DocumentAI] ERROR executing extraction pipeline: {e}")
            raise e

    def _parse_structured_entities(self, entities, full_text: str) -> Dict[str, Any]:
        """
        Parses structured Document AI Invoice Parser entities into our schema,
        converting currencies and dates to proper typed representations.
        """
        # Map fields to our system schemas
        extracted_data = {
            "vendor_name": "Unknown Vendor",
            "invoice_number": "N/A",
            "invoice_amount": 0.0,
            "purchase_order_number": "N/A",
            "payment_terms": "Net 30",
            "early_payment_discount_percentage": 0.0,
            "discount_period_days": 0,
            "net_period_days": 30
        }

        # Document AI maps values to standard type namespaces: e.g. supplier_name, invoice_id, total_amount
        for entity in entities:
            e_type = entity.type_
            e_val = entity.mention_text or entity.normalized_value.text
            
            if e_type == "supplier_name":
                extracted_data["vendor_name"] = e_val.strip()
            elif e_type == "invoice_id":
                extracted_data["invoice_number"] = e_val.strip()
            elif e_type == "total_amount":
                extracted_data["invoice_amount"] = self._clean_float_value(e_val)
            elif e_type == "purchase_order":
                extracted_data["purchase_order_number"] = e_val.strip()
            elif e_type == "payment_terms":
                extracted_data["payment_terms"] = e_val.strip()
                # Parse days from terms
                discount_pct, disc_days, net_days = self._parse_terms_days(e_val)
                extracted_data["early_payment_discount_percentage"] = discount_pct
                extracted_data["discount_period_days"] = disc_days
                extracted_data["net_period_days"] = net_days

        # Validate total amount, fallback to regex search in full text if missing
        if extracted_data["invoice_amount"] == 0.0:
            extracted_data["invoice_amount"] = self._extract_amount_via_regex(full_text)

        return extracted_data

    def _parse_generic_ocr_with_llm(self, text_layout: str) -> Dict[str, Any]:
        """
        Pipes extracted layout text from a general Document OCR processor
        into Gemini for structured JSON classification.
        """
        if not self.gemini_api_key:
            raise ValueError(
                "Gemini API key (GEMINI_API_KEY) is required when using a generic OCR processor "
                "to structure raw document layouts."
            )

        print("[DocumentAI] Invoking Gemini structure engine...")
        client = genai.Client()
        
        prompt = f"""
        Analyze the following text extracted from an invoice by Google Document AI.
        Clean the layout, structure the key fields, and output a valid JSON object matching this schema:
        
        {{
            "vendor_name": "Vendor/Company Name (or 'Unknown Vendor')",
            "invoice_number": "Invoice ID/Number (use 'N/A' if missing)",
            "invoice_amount": total amount to pay as a float/number (e.g. 1250.00),
            "purchase_order_number": "PO reference number if present (use 'N/A' if missing)",
            "payment_terms": "e.g. 2/10 Net 30, Net 30, etc. (use 'Net 30' if missing)",
            "early_payment_discount_percentage": Early payment discount rate as float (e.g. 0.02 for 2%, 0.00 if none),
            "discount_period_days": Early payment discount window in days (e.g. 10 for /10 in '2/10 Net 30', 0 if none),
            "net_period_days": Standard payment window in days (e.g. 30, 45, 60, defaults to 30)
        }}

        Invoice Raw Text Layout:
        -------------------------
        {text_layout}
        -------------------------

        CRITICAL: Output ONLY the raw JSON object structure. Do not wrap it in backticks, markdown fences, or extra commentary.
        """
        
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt
        )
        
        clean_text = response.text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text.split("```json")[1].split("```")[0].strip()
        elif clean_text.startswith("```"):
            clean_text = clean_text.split("```")[1].split("```")[0].strip()
            
        return json.loads(clean_text)

    def _clean_float_value(self, val_str: str) -> float:
        """Helper to remove currency symbols, commas, and parse floats cleanly."""
        try:
            # Strip currency markers, spaces, and commas
            cleaned = re.sub(r"[^\d\.]", "", val_str)
            return float(cleaned)
        except ValueError:
            return 0.0

    def _extract_amount_via_regex(self, text: str) -> float:
        """Fallback regex pattern matcher looking for totals in case Document AI fails to match."""
        patterns = [
            r"(?:Total|Total Due|Balance Due|Amount Due|Net Amount)\s*[:\$]*\s*([\d,]+\.\d{2})",
            r"([\d,]+\.\d{2})\s*(?:USD|CAD|EUR|GBP)?"
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return self._clean_float_value(match.group(1))
        return 0.0

    def _parse_terms_days(self, terms_str: str) -> tuple[float, int, int]:
        """
        Parses early payment discounts and net day timelines from standard AP strings.
        Example: "2/10 Net 30" -> (0.02, 10, 30)
                 "Net 45" -> (0.0, 0, 45)
        """
        terms_lower = terms_str.lower()
        discount_pct = 0.0
        discount_days = 0
        net_days = 30
        
        # Matches patterns like "2/10 Net 30" or "1.5/15 Net 45"
        discount_match = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+)", terms_lower)
        if discount_match:
            try:
                discount_pct = float(discount_match.group(1)) / 100.0
                discount_days = int(discount_match.group(2))
            except ValueError:
                pass
                
        # Matches net days "net 30", "net 45" or "n30"
        net_match = re.search(r"net\s*(\d+)|n\s*(\d+)", terms_lower)
        if net_match:
            try:
                days_group = net_match.group(1) or net_match.group(2)
                net_days = int(days_group)
            except ValueError:
                pass
                
        return discount_pct, discount_days, net_days


# --- CONSOLE TESTING SUITE ---
if __name__ == "__main__":
    import sys
    
    print("=========================================")
    print(" Google Document AI OCR Testing Terminal ")
    print("=========================================")
    
    if len(sys.argv) < 2:
        print("\nUsage: python Backend/document_ai_ocr.py <path_to_invoice_file>")
        print("\nMake sure your environmental configurations are set in .env:")
        print(" - GCP_PROJECT_ID")
        print(" - DOCUMENT_AI_PROCESSOR_ID")
        print(" - GOOGLE_APPLICATION_CREDENTIALS (path to service account JSON)")
        sys.exit(1)
        
    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"Error: Target file not found: {file_path}")
        sys.exit(1)
        
    # Read files bytes
    with open(file_path, "rb") as f:
        file_bytes = f.read()
        
    # Map file extension to MIME type
    ext = os.path.splitext(file_path)[1].lower()
    mime = "application/pdf"
    if ext in [".png"]:
        mime = "image/png"
    elif ext in [".jpg", ".jpeg"]:
        mime = "image/jpeg"

    # Execute
    try:
        extractor = DocumentAIExtractor()
        extracted = extractor.process_document_bytes(file_bytes, mime)
        print("\nProcessing Successful! Structured JSON Outcome:")
        print(json.dumps(extracted, indent=4))
    except Exception as e:
        print(f"\nProcessing Failed: {e}")
        print("\nPlease check that your Google Cloud Service Account credentials, Project ID, and Processor IDs are fully set.")
