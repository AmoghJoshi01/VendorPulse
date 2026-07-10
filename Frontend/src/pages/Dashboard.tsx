import { useState, useEffect } from 'react';
import { UserButton, OrganizationSwitcher, useAuth } from "@clerk/clerk-react";
import { 
  DollarSign, 
  Upload, 
  TrendingUp, 
  Settings as SettingsIcon, 
  AlertTriangle, 
  CheckCircle2, 
  Clock, 
  FileText, 
  XCircle, 
  Users, 
  RefreshCw, 
  Sliders, 
  Building, 
  ChevronRight, 
  Info,
  Calendar,
  AlertCircle
} from 'lucide-react';
import { Invoice, Vendor, PurchaseOrder, Analytics, Settings } from '../types';

const API_BASE = 'http://127.0.0.1:8000/api';

export default function Dashboard() {
  const { getToken } = useAuth();

  const authFetch = async (url: string, options: RequestInit = {}) => {
    const token = await getToken();
    const headers = {
      ...(options.headers || {}),
      'Authorization': `Bearer ${token}`
    };
    return fetch(url, { ...options, headers });
  };

  const [activeTab, setActiveTab] = useState<'dashboard' | 'upload' | 'invoices' | 'matching' | 'settings' | 'portal'>('dashboard');
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [pos, setPos] = useState<PurchaseOrder[]>([]);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [settings, setSettings] = useState<Settings>({ cost_of_capital: 6.0, minimum_liquidity_threshold: 25000.0, cash_balance: 150000.0 });
  const [loading, setLoading] = useState<boolean>(true);
  const [uploading, setUploading] = useState<boolean>(false);
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);
  const [resolutionComment, setResolutionComment] = useState<string>('');
  
  // Custom File Uploader States
  const [customFile, setCustomFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<Invoice | null>(null);
  const [customUploading, setCustomUploading] = useState<boolean>(false);
  const [customUploadError, setCustomUploadError] = useState<string | null>(null);
  const [uploadStep, setUploadStep] = useState<number>(0);
  
  // Simulation templates for Pitch / Demo
  const demoFiles = [
    { name: 'acme_industrial_inv_8942.pdf', label: 'Acme - 3-Way Match Ok (Early Pay Rec)', mockName: 'acme' },
    { name: 'globex_freight_inv_9051.jpeg', label: 'Globex - 3-Way Match Ok (Hold Net Rec)', mockName: 'globex' },
    { name: 'initech_software_inv_9113.pdf', label: 'Initech - Price Mismatch Exception', mockName: 'initech' },
    { name: 'olivia_wilson_consulting_0412.png', label: 'Olivia Wilson - Missing PO Exception', mockName: 'olivia' }
  ];

  // Supplier portal state
  const [portalSelectedInvoice, setPortalSelectedInvoice] = useState<Invoice | null>(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [settingsRes, invoicesRes, posRes, vendorsRes, analyticsRes] = await Promise.all([
        authFetch(`${API_BASE}/settings`),
        authFetch(`${API_BASE}/invoices`),
        authFetch(`${API_BASE}/pos`),
        authFetch(`${API_BASE}/vendors`),
        authFetch(`${API_BASE}/analytics`)
      ]);

      const settingsData = await settingsRes.json();
      const invoicesData = await invoicesRes.json();
      const posData = await posRes.json();
      const vendorsData = await vendorsRes.json();
      const analyticsData = await analyticsRes.json();

      setSettings(settingsData);
      setInvoices(invoicesData);
      setPos(posData);
      setVendors(vendorsData);
      setAnalytics(analyticsData);
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateSettings = async (newSettings: Settings) => {
    try {
      const res = await authFetch(`${API_BASE}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newSettings)
      });
      const data = await res.json();
      setSettings(data);
      // Reload analytics and invoices since recommendation might change
      const [invRes, anaRes] = await Promise.all([
        authFetch(`${API_BASE}/invoices`),
        authFetch(`${API_BASE}/analytics`)
      ]);
      setInvoices(await invRes.json());
      setAnalytics(await anaRes.json());
    } catch (err) {
      console.error('Error updating settings:', err);
    }
  };

  const handleAction = async (invoiceId: string, action: 'approve' | 'pay' | 'reject') => {
    try {
      const res = await authFetch(`${API_BASE}/invoices/${invoiceId}/${action}`, { method: 'POST' });
      if (res.ok) {
        // Refresh data
        await fetchData();
        // Update selectedInvoice if it is the current one
        if (selectedInvoice && selectedInvoice.id === invoiceId) {
          const updated = invoices.find(i => i.id === invoiceId);
          if (updated) {
            setSelectedInvoice({ ...updated, status: action === 'approve' ? 'APPROVED' : action === 'pay' ? 'PAID' : 'REJECTED' });
          }
        }
      }
    } catch (err) {
      console.error(`Error performing action ${action} on invoice ${invoiceId}:`, err);
    }
  };

  const handleResolveException = async (invoiceId: string, action: string) => {
    try {
      const res = await authFetch(`${API_BASE}/invoices/${invoiceId}/resolve-exception`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, comments: resolutionComment })
      });
      if (res.ok) {
        setResolutionComment('');
        await fetchData();
        // Update selected invoice in match viewer
        const updated = await res.json();
        setSelectedInvoice(updated);
      }
    } catch (err) {
      console.error('Error resolving exception:', err);
    }
  };

  const handleSimulateUpload = async (mockType: string) => {
    setUploading(true);
    // Simulate API delay for dramatic pitch flow
    try {
      // Create empty mock file object matching the name
      const blob = new Blob(['mock invoice content'], { type: 'application/pdf' });
      const file = new File([blob], `${mockType}_invoice_demo.pdf`);
      
      const formData = new FormData();
      formData.append('file', file);

      const res = await authFetch(`${API_BASE}/invoices/upload`, {
        method: 'POST',
        body: formData
      });
      
      if (res.ok) {
        const newInvoice = await res.json();
        await fetchData();
        // Switch to the invoices tab to see the new invoice
        setActiveTab('invoices');
        // Highlight it in matching view if it has an exception, or select it
        setSelectedInvoice(newInvoice);
      }
    } catch (err) {
      console.error('Error uploading invoice:', err);
    } finally {
      setUploading(false);
    }
  };

  const handleCustomFileUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customFile) return;
    
    setCustomUploading(true);
    setCustomUploadError(null);
    setUploadResult(null);
    setUploadStep(0);
    
    // Animate upload steps for higher-fidelity user experience
    const stepInterval = setInterval(() => {
      setUploadStep(prev => (prev < 4 ? prev + 1 : prev));
    }, 1200);
    
    try {
      const formData = new FormData();
      formData.append('file', customFile);
      
      const res = await authFetch(`${API_BASE}/invoices/upload`, {
        method: 'POST',
        body: formData
      });
      
      clearInterval(stepInterval);
      
      if (res.ok) {
        const data = await res.json();
        setUploadStep(5);
        setUploadResult(data);
        // Refresh analytics and ledger
        await fetchData();
      } else {
        const err = await res.text();
        setCustomUploadError(err || 'Failed to upload and process file.');
      }
    } catch (err: any) {
      clearInterval(stepInterval);
      setCustomUploadError(err.message || 'An error occurred during upload.');
    } finally {
      setCustomUploading(false);
    }
  };

  // Helper formatting functions
  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  };

  // Find corresponding PO
  const getMatchedPO = (invoice: Invoice) => {
    if (!invoice.purchase_order_number) return null;
    return pos.find(p => p.po_number === invoice.purchase_order_number) || null;
  };

  // Find corresponding GR
  const getMatchedGR = (invoice: Invoice) => {
    if (!invoice.purchase_order_number) return null;
    return receipts.find(r => r.po_number === invoice.purchase_order_number) || null;
  };

  // Simulated receipts database (fetched from backend or static since we fetch pos)
  const receipts = [
    {
      po_number: "PO-99541",
      receipt_number: "GR-88421",
      received_date: "2026-06-18",
      status: "RECEIVED",
      items: [
        {"description": "Industrial Safety Gloves", "quantity": 10},
        {"description": "Heavy Duty Steel Boots", "quantity": 5}
      ]
    },
    {
      po_number: "PO-99542",
      receipt_number: "GR-88422",
      received_date: "2026-06-22",
      status: "RECEIVED",
      items: [
        {"description": "Freight & Warehousing Services", "quantity": 1}
      ]
    },
    {
      po_number: "PO-99543",
      receipt_number: "GR-88423",
      received_date: "2026-06-28",
      status: "RECEIVED",
      items: [
        {"description": "Enterprise Software Licensing", "quantity": 1}
      ]
    }
  ];

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col justify-center items-center text-slate-100 font-sans">
        <div className="relative">
          <div className="w-16 h-16 border-4 border-emerald-500/30 border-t-emerald-400 rounded-full animate-spin"></div>
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-emerald-400 font-bold text-xs">VP</div>
        </div>
        <h2 className="mt-6 text-xl font-medium tracking-wide text-slate-300">Loading AP Intelligence...</h2>
        <p className="mt-2 text-sm text-slate-500 animate-pulse">Establishing ledger integration</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0b0f19] text-slate-200 font-sans flex flex-col antialiased selection:bg-emerald-500/30 selection:text-emerald-300">
      {/* Top Banner */}
      <header className="border-b border-slate-800 bg-[#0f1524]/80 backdrop-blur-md sticky top-0 z-40 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center shadow-lg shadow-emerald-500/10">
            <TrendingUp className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              VendorPulse <span className="text-[10px] uppercase font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded-full">v2.0 AP Intelligence</span>
            </h1>
            <p className="text-xs text-slate-400">AP Automation & Cash Flow Optimization</p>
          </div>
        </div>

        {/* Corporate Status Indicators & User Controls */}
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-6 text-xs border border-slate-800/80 bg-slate-900/60 rounded-xl p-2 px-4 shadow-inner">
            <div className="flex flex-col">
              <span className="text-slate-500">Corporate WACC</span>
              <span className="font-semibold text-emerald-400 flex items-center gap-1">
                <Sliders className="w-3 h-3" /> {settings.cost_of_capital.toFixed(1)}%
              </span>
            </div>
            <div className="h-6 w-px bg-slate-800"></div>
            <div className="flex flex-col">
              <span className="text-slate-500">Treasury Cash Balance</span>
              <span className="font-semibold text-white">{formatCurrency(settings.cash_balance)}</span>
            </div>
            <div className="h-6 w-px bg-slate-800"></div>
            <div className="flex flex-col">
              <span className="text-slate-500">API Status</span>
              <span className="font-semibold text-teal-400 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-teal-400 animate-ping"></span> Live Gemini AI
              </span>
            </div>
          </div>

          <div className="h-8 w-px bg-slate-800" />

          {/* Clerk Controls */}
          <div className="flex items-center gap-3">
            <OrganizationSwitcher
              appearance={{
                elements: {
                  rootBox: "text-xs font-semibold",
                  organizationSwitcherTrigger: "bg-slate-900/80 border border-slate-800 text-slate-300 hover:text-white hover:border-slate-700 px-3 py-2 rounded-xl transition-all font-semibold",
                  organizationPreviewTextContainer: "text-slate-300 text-xs font-semibold",
                  organizationPreviewTitle: "text-slate-300 text-xs font-semibold",
                }
              }}
            />
            <UserButton
              showName={true}
              appearance={{
                elements: {
                  userButtonTrigger: "bg-slate-900/80 border border-slate-800 hover:border-slate-700 px-3 py-2 rounded-xl transition-all",
                  userButtonOuterIdentifier: "text-slate-300 font-semibold text-xs",
                }
              }}
            />
          </div>
        </div>
      </header>

      {/* Main Container */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="w-64 border-r border-slate-800 bg-[#0c111e]/90 p-4 flex flex-col justify-between">
          <div className="space-y-6">
            <div>
              <p className="text-[11px] font-bold text-slate-500 uppercase tracking-widest px-3 mb-3">Core Modules</p>
              <nav className="space-y-1">
                <button 
                  onClick={() => setActiveTab('dashboard')}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                    activeTab === 'dashboard' 
                      ? 'bg-gradient-to-r from-emerald-500/10 to-teal-500/5 text-emerald-400 border border-emerald-500/20 shadow-sm shadow-emerald-500/5' 
                      : 'text-slate-400 hover:bg-slate-800/40 hover:text-slate-200 border border-transparent'
                  }`}
                >
                  <TrendingUp className="w-4.5 h-4.5" />
                  <span>Treasury Analytics</span>
                </button>

                <button 
                  onClick={() => setActiveTab('upload')}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                    activeTab === 'upload' 
                      ? 'bg-gradient-to-r from-emerald-500/10 to-teal-500/5 text-emerald-400 border border-emerald-500/20 shadow-sm shadow-emerald-500/5' 
                      : 'text-slate-400 hover:bg-slate-800/40 hover:text-slate-200 border border-transparent'
                  }`}
                >
                  <Upload className="w-4.5 h-4.5" />
                  <span>Document Ingestion</span>
                </button>

                <button 
                  onClick={() => setActiveTab('invoices')}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                    activeTab === 'invoices' 
                      ? 'bg-gradient-to-r from-emerald-500/10 to-teal-500/5 text-emerald-400 border border-emerald-500/20 shadow-sm shadow-emerald-500/5' 
                      : 'text-slate-400 hover:bg-slate-800/40 hover:text-slate-200 border border-transparent'
                  }`}
                >
                  <FileText className="w-4.5 h-4.5" />
                  <span className="flex-1 text-left">Invoice Ledger</span>
                  {invoices.filter(i => i.status === 'PENDING_MATCH' || i.status === 'EXCEPTION').length > 0 && (
                    <span className="bg-amber-500/10 text-amber-400 border border-amber-500/20 text-xs px-2 py-0.5 rounded-full font-bold">
                      {invoices.filter(i => i.status === 'PENDING_MATCH' || i.status === 'EXCEPTION').length}
                    </span>
                  )}
                </button>

                <button 
                  onClick={() => {
                    // Set default selected invoice if none selected yet
                    if (!selectedInvoice && invoices.length > 0) {
                      setSelectedInvoice(invoices[0]);
                    }
                    setActiveTab('matching');
                  }}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                    activeTab === 'matching' 
                      ? 'bg-gradient-to-r from-emerald-500/10 to-teal-500/5 text-emerald-400 border border-emerald-500/20 shadow-sm shadow-emerald-500/5' 
                      : 'text-slate-400 hover:bg-slate-800/40 hover:text-slate-200 border border-transparent'
                  }`}
                >
                  <AlertTriangle className="w-4.5 h-4.5" />
                  <span className="flex-1 text-left">3-Way Match & QA</span>
                  {invoices.filter(i => i.status === 'EXCEPTION').length > 0 && (
                    <span className="bg-red-500/10 text-red-400 border border-red-500/20 text-xs px-2 py-0.5 rounded-full font-bold">
                      {invoices.filter(i => i.status === 'EXCEPTION').length}
                    </span>
                  )}
                </button>
              </nav>
            </div>

            <div>
              <p className="text-[11px] font-bold text-slate-500 uppercase tracking-widest px-3 mb-3">Portals & Settings</p>
              <nav className="space-y-1">
                <button 
                  onClick={() => {
                    // Set default for portal view
                    if (invoices.length > 0) {
                      setPortalSelectedInvoice(invoices[0]);
                    }
                    setActiveTab('portal');
                  }}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                    activeTab === 'portal' 
                      ? 'bg-gradient-to-r from-emerald-500/10 to-teal-500/5 text-emerald-400 border border-emerald-500/20 shadow-sm shadow-emerald-500/5' 
                      : 'text-slate-400 hover:bg-slate-800/40 hover:text-slate-200 border border-transparent'
                  }`}
                >
                  <Building className="w-4.5 h-4.5" />
                  <span>Supplier Portal</span>
                </button>

                <button 
                  onClick={() => setActiveTab('settings')}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                    activeTab === 'settings' 
                      ? 'bg-gradient-to-r from-emerald-500/10 to-teal-500/5 text-emerald-400 border border-emerald-500/20 shadow-sm shadow-emerald-500/5' 
                      : 'text-slate-400 hover:bg-slate-800/40 hover:text-slate-200 border border-transparent'
                  }`}
                >
                  <SettingsIcon className="w-4.5 h-4.5" />
                  <span>Treasury Settings</span>
                </button>
              </nav>
            </div>
          </div>

          {/* Quick Upload Simulator */}
          <div className="border border-slate-800 bg-slate-900/40 rounded-xl p-4 space-y-3">
            <h4 className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
              <Upload className="w-3.5 h-3.5 text-emerald-400" /> Upload Simulation
            </h4>
            <p className="text-[11px] text-slate-500 leading-normal">
              Click a demo file to simulate real-time AI ingestion, document parsing, and match evaluation.
            </p>
            <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
              {demoFiles.map((file) => (
                <button
                  key={file.mockName}
                  disabled={uploading}
                  onClick={() => handleSimulateUpload(file.mockName)}
                  className="w-full text-left text-[11px] bg-slate-950 hover:bg-slate-900 border border-slate-800 hover:border-slate-700 p-2 rounded-lg text-slate-400 hover:text-white transition-all flex justify-between items-center group disabled:opacity-50"
                >
                  <span className="truncate pr-1 group-hover:text-emerald-400 transition-colors">{file.label}</span>
                  <ChevronRight className="w-3 h-3 text-slate-600 shrink-0" />
                </button>
              ))}
            </div>
            {uploading && (
              <div className="flex items-center gap-2 text-xs text-emerald-400 bg-emerald-500/5 border border-emerald-500/10 p-2 rounded-lg">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>AI Parsing Document...</span>
              </div>
            )}
          </div>
        </aside>

        {/* Content Area */}
        <main className="flex-1 bg-[#0b0f19] overflow-y-auto p-8">
          
          {/* TAB 1: TREASURY ANALYTICS */}
          {activeTab === 'dashboard' && analytics && (
            <div className="space-y-8 animate-fade-in">
              {/* Dashboard Header */}
              <div className="flex justify-between items-center">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight text-white">Treasury Optimization Control</h2>
                  <p className="text-sm text-slate-400">Capital allocations, savings yield calculations, and AP forecasts.</p>
                </div>
                <button 
                  onClick={fetchData} 
                  className="bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300 p-2 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all"
                >
                  <RefreshCw className="w-3.5 h-3.5" /> Sync Ledger
                </button>
              </div>

              {/* Grid Widgets */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                {/* Total Accounts Payable */}
                <div className="bg-[#0f1524]/60 border border-slate-800/80 rounded-2xl p-6 shadow-sm flex flex-col justify-between">
                  <div className="flex justify-between items-start">
                    <span className="text-sm font-semibold text-slate-400">Total Accounts Payable</span>
                    <span className="bg-slate-800 p-2 rounded-xl text-slate-300"><FileText className="w-4 h-4" /></span>
                  </div>
                  <div className="mt-4">
                    <span className="text-3xl font-extrabold tracking-tight text-white">{formatCurrency(analytics.total_ap)}</span>
                    <p className="text-[11px] text-slate-500 mt-1">Outstanding bills in AP pipeline</p>
                  </div>
                </div>

                {/* Cash Saved */}
                <div className="bg-[#0f1524]/60 border border-slate-800/80 rounded-2xl p-6 shadow-sm flex flex-col justify-between relative overflow-hidden group">
                  <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/5 rounded-full blur-2xl group-hover:bg-emerald-500/10 transition-all"></div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm font-semibold text-slate-400">Early Payment Savings (Paid)</span>
                    <span className="bg-emerald-500/10 border border-emerald-500/20 p-2 rounded-xl text-emerald-400"><DollarSign className="w-4 h-4" /></span>
                  </div>
                  <div className="mt-4">
                    <span className="text-3xl font-extrabold tracking-tight text-emerald-400">{formatCurrency(analytics.realized_savings)}</span>
                    <p className="text-[11px] text-emerald-500 mt-1">Earned via early payment discounts</p>
                  </div>
                </div>

                {/* Potential Savings */}
                <div className="bg-[#0f1524]/60 border border-slate-800/80 rounded-2xl p-6 shadow-sm flex flex-col justify-between">
                  <div className="flex justify-between items-start">
                    <span className="text-sm font-semibold text-slate-400">Potential Savings (Pending)</span>
                    <span className="bg-teal-500/10 border border-teal-500/20 p-2 rounded-xl text-teal-400"><TrendingUp className="w-4 h-4" /></span>
                  </div>
                  <div className="mt-4">
                    <span className="text-3xl font-extrabold tracking-tight text-teal-300">{formatCurrency(analytics.potential_savings)}</span>
                    <p className="text-[11px] text-slate-500 mt-1">Available if early payouts approved</p>
                  </div>
                </div>

                {/* Days Payable Outstanding */}
                <div className="bg-[#0f1524]/60 border border-slate-800/80 rounded-2xl p-6 shadow-sm flex flex-col justify-between">
                  <div className="flex justify-between items-start">
                    <span className="text-sm font-semibold text-slate-400">Days Payable Outstanding</span>
                    <span className="bg-slate-800 p-2 rounded-xl text-slate-300"><Clock className="w-4 h-4" /></span>
                  </div>
                  <div className="mt-4">
                    <span className="text-3xl font-extrabold tracking-tight text-white">{analytics.dpo} Days</span>
                    <p className="text-[11px] text-slate-500 mt-1">
                      Avg. payment cycle duration (Target: 30)
                    </p>
                  </div>
                </div>
              </div>

              {/* Chart & Treasury Optimization Recommendation */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* 30-Day Outflow Forecast Chart */}
                <div className="lg:col-span-2 bg-[#0f1524]/60 border border-slate-800/80 rounded-2xl p-6 shadow-sm space-y-6">
                  <div className="flex justify-between items-center">
                    <div>
                      <h3 className="text-lg font-bold text-white">30-Day Cash Outflow Forecast</h3>
                      <p className="text-xs text-slate-400">Comparing Standard net payment vs Discounted early payment schedule.</p>
                    </div>
                    <div className="flex items-center gap-4 text-xs">
                      <div className="flex items-center gap-1.5">
                        <span className="w-3 h-3 rounded bg-emerald-500"></span>
                        <span className="text-slate-400">Early Pay Route</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="w-3 h-3 rounded bg-indigo-500"></span>
                        <span className="text-slate-400">Hold Net Route</span>
                      </div>
                    </div>
                  </div>

                  {/* Simulated Visual Chart Bars */}
                  <div className="h-64 flex items-end gap-12 px-6 pt-4 border-b border-slate-800">
                    {analytics.forecast.categories.map((week, idx) => {
                      const earlyVal = analytics.forecast.early_payment_schedule[idx];
                      const netVal = analytics.forecast.net_payment_schedule[idx];
                      
                      const maxVal = Math.max(
                        ...analytics.forecast.early_payment_schedule,
                        ...analytics.forecast.net_payment_schedule,
                        1000
                      );

                      const earlyHeight = (earlyVal / maxVal) * 100;
                      const netHeight = (netVal / maxVal) * 100;

                      return (
                        <div key={week} className="flex-1 flex flex-col items-center h-full justify-end group relative">
                          {/* Hover Tooltip */}
                          <div className="absolute -top-12 scale-0 group-hover:scale-100 transition-all bg-slate-900 border border-slate-700 text-[10px] p-2 rounded-lg z-10 space-y-0.5 shadow-lg pointer-events-none">
                            <p className="text-white font-semibold">{week}</p>
                            <p className="text-emerald-400">Early Pay: {formatCurrency(earlyVal)}</p>
                            <p className="text-indigo-400">Hold Net: {formatCurrency(netVal)}</p>
                          </div>

                          <div className="w-full flex justify-center items-end gap-2 h-full">
                            {/* Early Pay Bar */}
                            <div 
                              style={{ height: `${earlyHeight}%` }} 
                              className="w-8 bg-gradient-to-t from-emerald-600 to-teal-400 hover:brightness-110 rounded-t transition-all duration-500 relative flex justify-center"
                            >
                              {earlyVal > 0 && (
                                <span className="absolute -top-5 text-[9px] font-semibold text-emerald-400">
                                  {formatCurrency(earlyVal / 1000)}k
                                </span>
                              )}
                            </div>
                            
                            {/* Net Pay Bar */}
                            <div 
                              style={{ height: `${netHeight}%` }} 
                              className="w-8 bg-gradient-to-t from-indigo-600 to-blue-400 hover:brightness-110 rounded-t transition-all duration-500 relative flex justify-center"
                            >
                              {netVal > 0 && (
                                <span className="absolute -top-5 text-[9px] font-semibold text-indigo-400">
                                  {formatCurrency(netVal / 1000)}k
                                </span>
                              )}
                            </div>
                          </div>
                          <span className="text-xs text-slate-500 mt-2 font-medium">{week}</span>
                        </div>
                      );
                    })}
                  </div>
                  
                  <div className="bg-slate-900/40 p-4 rounded-xl flex items-start gap-3 border border-slate-800">
                    <Info className="w-4 h-4 text-teal-400 mt-0.5 shrink-0" />
                    <p className="text-xs text-slate-400 leading-relaxed">
                      **Treasury Insight**: Under the early payment route, payouts are pulled forward into earlier weeks to capture discounts, reducing total cash outlay. Under the hold net route, cash remains in your account longer, preserving short-term liquidity.
                    </p>
                  </div>
                </div>

                {/* Treasury Decision Helper Matrix */}
                <div className="bg-[#0f1524]/60 border border-slate-800/80 rounded-2xl p-6 shadow-sm space-y-6 flex flex-col justify-between">
                  <div>
                    <h3 className="text-lg font-bold text-white">Yield Optimizer Matrix</h3>
                    <p className="text-xs text-slate-400">Evaluating early payment returns against corporate WACC.</p>
                  </div>

                  <div className="space-y-4">
                    <div className="bg-slate-900/60 p-4 rounded-xl space-y-2 border border-slate-800/60">
                      <div className="flex justify-between text-xs">
                        <span className="text-slate-400">Opportunity Cost (WACC)</span>
                        <span className="font-semibold text-white">{settings.cost_of_capital.toFixed(1)}%</span>
                      </div>
                      <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                        <div style={{ width: `${(settings.cost_of_capital / 15) * 100}%` }} className="bg-emerald-500 h-full rounded-full"></div>
                      </div>
                    </div>

                    <div className="space-y-2.5">
                      <h4 className="text-xs font-semibold text-slate-400">Payment Recommendations</h4>
                      {invoices.filter(i => i.status === 'PENDING_MATCH' || i.status === 'APPROVED').length === 0 ? (
                        <p className="text-xs text-slate-500 italic">No pending invoices to optimize.</p>
                      ) : (
                        <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                          {invoices.filter(i => i.status === 'PENDING_MATCH' || i.status === 'APPROVED').map((inv) => {
                            const isOptimal = inv.early_payment_status === 'OPTIMAL_PAID_EARLY';
                            return (
                              <div key={inv.id} className="flex justify-between items-center text-xs bg-slate-900/40 p-2.5 rounded-lg border border-slate-800/80">
                                <div className="truncate pr-1">
                                  <p className="font-medium text-white truncate">{inv.vendor_name}</p>
                                  <p className="text-[10px] text-slate-500">Yield: {inv.implied_annual_yield.toFixed(1)}%</p>
                                </div>
                                <span className={`px-2 py-0.5 rounded text-[10px] font-bold shrink-0 ${
                                  isOptimal 
                                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                                    : 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
                                }`}>
                                  {isOptimal ? 'Pay Early' : 'Hold Net'}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="pt-4 border-t border-slate-800/80">
                    <button 
                      onClick={() => setActiveTab('invoices')}
                      className="w-full bg-emerald-600 hover:bg-emerald-500 text-white p-2.5 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 shadow-lg shadow-emerald-500/10"
                    >
                      Process Pending Ledger <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB: DOCUMENT INGESTION (CUSTOM UPLOAD) */}
          {activeTab === 'upload' && (
            <div className="space-y-8 animate-fade-in">
              <div>
                <h2 className="text-2xl font-bold tracking-tight text-white">Document Ingestion Pipeline</h2>
                <p className="text-sm text-slate-400">Upload a custom PDF or image invoice to test live OCR extraction, 3-way matching, and WACC yield calculations.</p>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
                {/* Left side: Upload Form */}
                <div className="lg:col-span-5 bg-[#0f1524]/60 border border-slate-800/80 rounded-2xl p-6 space-y-6 shadow-sm">
                  <h3 className="text-base font-bold text-white">1. Select Document Payload</h3>
                  
                  <form onSubmit={handleCustomFileUpload} className="space-y-6">
                    {/* Drag and Drop Zone */}
                    <div className="flex justify-center items-center w-full">
                      <label 
                        htmlFor="dropzone-file" 
                        className={`flex flex-col justify-center items-center w-full h-64 rounded-2xl border-2 border-dashed transition-all cursor-pointer ${
                          customFile 
                            ? 'border-emerald-500/50 bg-emerald-500/[0.02]' 
                            : 'border-slate-800 hover:border-slate-700 bg-slate-950/40 hover:bg-slate-900/30'
                        }`}
                      >
                        <div className="flex flex-col justify-center items-center pt-5 pb-6 px-4 text-center">
                          <Upload className={`w-10 h-10 mb-4 transition-colors ${customFile ? 'text-emerald-400' : 'text-slate-500'}`} />
                          {customFile ? (
                            <div className="space-y-2">
                              <p className="text-sm font-semibold text-white truncate max-w-xs">{customFile.name}</p>
                              <p className="text-xs text-slate-400">
                                {(customFile.size / 1024).toFixed(1)} KB — {customFile.type.split('/')[1]?.toUpperCase()}
                              </p>
                              <span className="inline-block mt-2 text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded">
                                Ready for extraction
                              </span>
                            </div>
                          ) : (
                            <div>
                              <p className="mb-2 text-sm text-slate-300 font-semibold">
                                <span className="text-emerald-400 hover:underline">Click to browse</span> or drag and drop
                              </p>
                              <p className="text-xs text-slate-500">PDF, PNG, JPG, or JPEG (Max 10MB)</p>
                            </div>
                          )}
                        </div>
                        <input 
                          id="dropzone-file" 
                          type="file" 
                          className="hidden" 
                          onChange={(e) => {
                            setCustomFile(e.target.files?.[0] || null);
                            setUploadResult(null);
                            setCustomUploadError(null);
                          }} 
                          accept=".pdf,.png,.jpg,.jpeg" 
                        />
                      </label>
                    </div>

                    {customFile && (
                      <div className="flex gap-2">
                        <button
                          type="submit"
                          disabled={customUploading}
                          className="flex-1 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white p-3 rounded-xl text-sm font-bold transition-all flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/10"
                        >
                          {customUploading ? 'Processing...' : '🚀 Execute Live OCR Ingestion'}
                        </button>
                        <button
                          type="button"
                          disabled={customUploading}
                          onClick={() => {
                            setCustomFile(null);
                            setUploadResult(null);
                            setCustomUploadError(null);
                          }}
                          className="bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-400 p-3 rounded-xl text-sm font-bold transition-all"
                        >
                          Clear
                        </button>
                      </div>
                    )}
                  </form>

                  {customUploadError && (
                    <div className="bg-red-500/5 border border-red-500/20 text-red-400 text-xs p-4 rounded-xl flex items-start gap-2 leading-relaxed">
                      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                      <span>{customUploadError}</span>
                    </div>
                  )}

                  {/* Loading Steps Animation */}
                  {customUploading && (
                    <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-4">
                      <div className="flex items-center gap-3">
                        <RefreshCw className="w-5 h-5 text-emerald-400 animate-spin" />
                        <span className="text-sm font-bold text-white">Ingesting Invoice...</span>
                      </div>
                      <div className="space-y-2 text-xs">
                        <div className={`flex items-center gap-2 ${uploadStep >= 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
                          <span className="w-2 h-2 rounded-full bg-current"></span>
                          <span>Uploading document payload...</span>
                        </div>
                        <div className={`flex items-center gap-2 ${uploadStep >= 1 ? 'text-emerald-400' : 'text-slate-500'}`}>
                          <span className="w-2 h-2 rounded-full bg-current"></span>
                          <span>Initializing Google Document AI Processor...</span>
                        </div>
                        <div className={`flex items-center gap-2 ${uploadStep >= 2 ? 'text-emerald-400' : 'text-slate-500'}`}>
                          <span className="w-2 h-2 rounded-full bg-current"></span>
                          <span>Extracting fields: vendor, total, net_days, terms...</span>
                        </div>
                        <div className={`flex items-center gap-2 ${uploadStep >= 3 ? 'text-emerald-400' : 'text-slate-500'}`}>
                          <span className="w-2 h-2 rounded-full bg-current"></span>
                          <span>Cross-referencing Purchase Orders & Goods Receipts...</span>
                        </div>
                        <div className={`flex items-center gap-2 ${uploadStep >= 4 ? 'text-emerald-400' : 'text-slate-500'}`}>
                          <span className="w-2 h-2 rounded-full bg-current"></span>
                          <span>Calculating ROI yield on early payment discount...</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Right side: Realtime Parsing Results */}
                <div className="lg:col-span-7 space-y-6">
                  {uploadResult ? (
                    <div className="bg-[#0f1524]/60 border border-slate-800/80 rounded-2xl p-6 space-y-6 shadow-sm animate-fade-in">
                      <div className="flex justify-between items-center border-b border-slate-800 pb-4">
                        <div>
                          <h3 className="text-lg font-bold text-white">Extraction Ledger Outcome</h3>
                          <p className="text-xs text-slate-400">Live AI parsing successfully completed.</p>
                        </div>
                        <span className="bg-teal-500/10 text-teal-400 border border-teal-500/20 px-3 py-1 rounded-full text-xs font-bold flex items-center gap-1">
                          <CheckCircle2 className="w-3.5 h-3.5" /> 100% Live
                        </span>
                      </div>

                      {/* Yield Recommendation */}
                      <div className={`p-4 rounded-xl border ${
                        uploadResult.early_payment_status === 'OPTIMAL_PAID_EARLY'
                          ? 'bg-emerald-500/5 border-emerald-500/20 text-emerald-400'
                          : 'bg-indigo-500/5 border-indigo-500/20 text-indigo-400'
                      }`}>
                        <h4 className="text-xs font-bold uppercase tracking-wider">Treasury Decision Recommendation</h4>
                        {uploadResult.early_payment_status === 'OPTIMAL_PAID_EARLY' ? (
                          <div className="mt-2 text-sm leading-relaxed">
                            📊 **APPROVE FOR IMMEDIATE PAYMENT**: Implied annual return (**{uploadResult.implied_annual_yield.toFixed(1)}%**) exceeds WACC (**{settings.cost_of_capital.toFixed(1)}%**). Captures instant savings of **{formatCurrency(uploadResult.cash_savings)}**.
                          </div>
                        ) : (
                          <div className="mt-2 text-sm leading-relaxed">
                            🛑 **HOLD PAYMENT UNTIL DUE DATE**: Discount return (**{uploadResult.implied_annual_yield.toFixed(1)}%**) is lower than cost of capital (**{settings.cost_of_capital.toFixed(1)}%**). Pay total net balance exactly on Day **{uploadResult.net_period_days}**.
                          </div>
                        )}
                      </div>

                      {/* Matching Analysis */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 space-y-2">
                          <span className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">3-Way Match QA Result</span>
                          <div className="flex items-center gap-2 mt-1">
                            <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold ${
                              uploadResult.matching_result === 'THREE_WAY_OK'
                                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                : 'bg-red-500/10 text-red-400 border border-red-500/20'
                            }`}>
                              {uploadResult.matching_result}
                            </span>
                          </div>
                          <p className="text-xs text-slate-400 leading-normal mt-2">
                            {uploadResult.exception 
                              ? uploadResult.exception.description
                              : `Invoice matched corresponding PO ${uploadResult.purchase_order_number} and Goods Receipt records perfectly.`
                            }
                          </p>
                        </div>

                        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 space-y-2 flex flex-col justify-between">
                          <div>
                            <span className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">AP Ledger ID</span>
                            <p className="text-sm font-semibold text-white mt-1">{uploadResult.id}</p>
                          </div>
                          <div className="flex gap-2 pt-4">
                            <button
                              onClick={() => {
                                setSelectedInvoice(uploadResult);
                                setActiveTab('matching');
                              }}
                              className="flex-1 bg-slate-950 hover:bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 text-xs py-2 rounded-lg font-bold transition-all text-center"
                            >
                              Inspect Match
                            </button>
                            <button
                              onClick={() => setActiveTab('invoices')}
                              className="flex-1 bg-slate-950 hover:bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 text-xs py-2 rounded-lg font-bold transition-all text-center"
                            >
                              Ledger Inbox
                            </button>
                          </div>
                        </div>
                      </div>

                      {/* Fields Table */}
                      <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 space-y-3">
                        <span className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Extracted Metadata</span>
                        <div className="text-xs divide-y divide-slate-800">
                          <div className="flex justify-between py-2"><span className="text-slate-400">Vendor/Supplier Name</span><span className="font-semibold text-white">{uploadResult.vendor_name}</span></div>
                          <div className="flex justify-between py-2"><span className="text-slate-400">Invoice Number</span><span className="font-semibold text-white">{uploadResult.invoice_number}</span></div>
                          <div className="flex justify-between py-2"><span className="text-slate-400">Invoice Gross Amount</span><span className="font-bold text-white">{formatCurrency(uploadResult.invoice_amount)}</span></div>
                          <div className="flex justify-between py-2"><span className="text-slate-400">PO reference number</span><span className="font-semibold text-white">{uploadResult.purchase_order_number}</span></div>
                          <div className="flex justify-between py-2"><span className="text-slate-400">Payment Terms</span><span className="font-semibold text-white">{uploadResult.payment_terms}</span></div>
                          <div className="flex justify-between py-2"><span className="text-slate-400">Discount Percentage</span><span className="font-semibold text-white">{(uploadResult.early_payment_discount_percentage * 100).toFixed(1)}%</span></div>
                          <div className="flex justify-between py-2"><span className="text-slate-400">Discount Period</span><span className="font-semibold text-white">{uploadResult.discount_period_days} Days</span></div>
                          <div className="flex justify-between py-2"><span className="text-slate-400">Net Period</span><span className="font-semibold text-white">{uploadResult.net_period_days} Days</span></div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="bg-[#0f1524]/60 border border-slate-800/80 rounded-2xl p-12 text-center text-slate-500 italic shadow-sm flex flex-col items-center justify-center h-full min-h-[300px]">
                      <FileText className="w-12 h-12 text-slate-700 mb-3" />
                      <p className="max-w-md text-xs leading-normal">
                        Select a file and execute OCR to parse details. The extracted fields, matching outcomes, and cash yields will display here in real time.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: INVOICE LEDGER */}
          {activeTab === 'invoices' && (
            <div className="space-y-8 animate-fade-in">
              <div className="flex justify-between items-center">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight text-white">Accounts Payable Invoice Ledger</h2>
                  <p className="text-sm text-slate-400">Review status, QA matching outcomes, and execute early discount captures.</p>
                </div>
              </div>

              {/* Ledger Table Grid */}
              <div className="bg-[#0f1524]/60 border border-slate-800/80 rounded-2xl overflow-hidden shadow-sm">
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-slate-800 bg-slate-900/30 text-xs font-semibold text-slate-400 uppercase">
                        <th className="px-6 py-4">Vendor & Invoice ID</th>
                        <th className="px-6 py-4">Total Value</th>
                        <th className="px-6 py-4">Matching QA Status</th>
                        <th className="px-6 py-4">Yield / Terms</th>
                        <th className="px-6 py-4">Treasury Rec</th>
                        <th className="px-6 py-4">Invoice Status</th>
                        <th className="px-6 py-4 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 text-sm">
                      {invoices.length === 0 ? (
                        <tr>
                          <td colSpan={7} className="px-6 py-12 text-center text-slate-500 italic">
                            No invoices in ledger database. Upload some invoices using the simulator to start.
                          </td>
                        </tr>
                      ) : (
                        invoices.map((inv) => {
                          const isOptimal = inv.early_payment_status === 'OPTIMAL_PAID_EARLY';
                          
                          return (
                            <tr key={inv.id} className="hover:bg-slate-900/20 transition-all group">
                              <td className="px-6 py-4">
                                <div className="font-semibold text-white group-hover:text-emerald-400 transition-colors">{inv.vendor_name}</div>
                                <div className="text-xs text-slate-500 flex items-center gap-1.5 mt-0.5">
                                  <span>{inv.invoice_number}</span>
                                  {inv.is_live_ai && (
                                    <span className="bg-teal-500/10 text-teal-400 border border-teal-500/20 px-1.5 py-0.2 rounded text-[9px] font-bold">
                                      Gemini AI Extract
                                    </span>
                                  )}
                                </div>
                              </td>
                              
                              <td className="px-6 py-4 font-semibold text-white">
                                {formatCurrency(inv.invoice_amount)}
                              </td>
                              
                              <td className="px-6 py-4">
                                <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${
                                  inv.matching_result === 'THREE_WAY_OK'
                                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/15'
                                    : inv.matching_result === 'PRICE_MISMATCH'
                                    ? 'bg-red-500/10 text-red-400 border border-red-500/15'
                                    : 'bg-amber-500/10 text-amber-400 border border-amber-500/15'
                                }`}>
                                  {inv.matching_result === 'THREE_WAY_OK' && <CheckCircle2 className="w-3.5 h-3.5" />}
                                  {inv.matching_result !== 'THREE_WAY_OK' && <AlertTriangle className="w-3.5 h-3.5" />}
                                  {inv.matching_result.replace(/_/g, ' ')}
                                </span>
                              </td>

                              <td className="px-6 py-4">
                                <div className="text-white font-medium">{inv.payment_terms}</div>
                                <div className="text-xs text-slate-500 mt-0.5">
                                  {inv.implied_annual_yield > 0 ? (
                                    <span className="text-emerald-500 font-semibold">{inv.implied_annual_yield.toFixed(1)}% yield</span>
                                  ) : (
                                    <span>No discount terms</span>
                                  )}
                                </div>
                              </td>

                              <td className="px-6 py-4">
                                {inv.early_payment_discount_percentage > 0 ? (
                                  <div className="space-y-1">
                                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                      isOptimal 
                                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                                        : 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
                                    }`}>
                                      {isOptimal ? 'Pay Day ' + inv.discount_period_days : 'Pay Day ' + inv.net_period_days}
                                    </span>
                                    <p className="text-[10px] text-slate-400">
                                      {isOptimal 
                                        ? `Save ${formatCurrency(inv.cash_savings)}` 
                                        : `Preserve Cash`
                                      }
                                    </p>
                                  </div>
                                ) : (
                                  <span className="text-xs text-slate-500">Hold Net (Day {inv.net_period_days})</span>
                                )}
                              </td>

                              <td className="px-6 py-4">
                                <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-semibold ${
                                  inv.status === 'PAID'
                                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                    : inv.status === 'APPROVED'
                                    ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                                    : inv.status === 'EXCEPTION'
                                    ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                                    : inv.status === 'REJECTED'
                                    ? 'bg-slate-800 text-slate-400 border border-slate-700'
                                    : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                                }`}>
                                  {inv.status}
                                </span>
                              </td>

                              <td className="px-6 py-4 text-right">
                                <div className="flex justify-end gap-2">
                                  {inv.status === 'EXCEPTION' && (
                                    <button 
                                      onClick={() => {
                                        setSelectedInvoice(inv);
                                        setActiveTab('matching');
                                      }}
                                      className="bg-red-600/10 hover:bg-red-600/25 border border-red-500/25 text-red-400 text-xs px-2.5 py-1.5 rounded-lg font-bold transition-all"
                                    >
                                      Resolve QA
                                    </button>
                                  )}
                                  {inv.status === 'PENDING_MATCH' && (
                                    <button 
                                      onClick={() => handleAction(inv.id, 'approve')}
                                      className="bg-emerald-600/15 hover:bg-emerald-600/30 border border-emerald-500/25 text-emerald-400 text-xs px-2.5 py-1.5 rounded-lg font-bold transition-all"
                                    >
                                      Approve Pay
                                    </button>
                                  )}
                                  {inv.status === 'APPROVED' && (
                                    <button 
                                      onClick={() => handleAction(inv.id, 'pay')}
                                      className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-2.5 py-1.5 rounded-lg font-bold transition-all flex items-center gap-1 shadow-sm"
                                    >
                                      <DollarSign className="w-3.5 h-3.5" /> Pay Now
                                    </button>
                                  )}
                                  {inv.status !== 'PAID' && inv.status !== 'REJECTED' && (
                                    <button 
                                      onClick={() => handleAction(inv.id, 'reject')}
                                      className="bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 text-slate-400 hover:text-slate-200 text-xs px-2.5 py-1.5 rounded-lg font-bold transition-all"
                                    >
                                      Reject
                                    </button>
                                  )}
                                  {inv.status === 'PAID' && (
                                    <span className="text-xs text-slate-500 flex items-center gap-1 mr-2">
                                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> Settled
                                    </span>
                                  )}
                                  {inv.status === 'REJECTED' && (
                                    <span className="text-xs text-slate-500 flex items-center gap-1 mr-2">
                                      <XCircle className="w-3.5 h-3.5 text-red-500" /> Closed
                                    </span>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: 3-WAY MATCH & QA */}
          {activeTab === 'matching' && (
            <div className="space-y-8 animate-fade-in">
              <div>
                <h2 className="text-2xl font-bold tracking-tight text-white">3-Way Match Verification Center</h2>
                <p className="text-sm text-slate-400">Inspect granular invoice data matched against Purchase Orders and Goods Receipts.</p>
              </div>

              {/* Center Panel Grid */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
                {/* Left Side: Invoice List */}
                <div className="lg:col-span-4 bg-[#0f1524]/60 border border-slate-800/80 rounded-2xl p-4 space-y-3 h-[600px] overflow-y-auto">
                  <h3 className="text-sm font-bold text-slate-300 px-2 pb-2 border-b border-slate-800/80">Invoices for Verification</h3>
                  <div className="space-y-2">
                    {invoices.length === 0 ? (
                      <p className="text-xs text-slate-500 italic p-4 text-center">No invoices in ledger.</p>
                    ) : (
                      invoices.map((inv) => (
                        <button
                          key={inv.id}
                          onClick={() => setSelectedInvoice(inv)}
                          className={`w-full text-left p-3 rounded-xl border transition-all ${
                            selectedInvoice?.id === inv.id
                              ? 'bg-slate-900 border-emerald-500/50 shadow-sm'
                              : 'bg-slate-950/40 border-slate-800/80 hover:bg-slate-900/40'
                          }`}
                        >
                          <div className="flex justify-between items-start">
                            <span className="font-semibold text-xs text-slate-200 truncate flex-1 pr-1">{inv.vendor_name}</span>
                            <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded shrink-0 ${
                              inv.status === 'EXCEPTION' 
                                ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                                : inv.status === 'APPROVED' || inv.status === 'PAID'
                                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                            }`}>
                              {inv.status}
                            </span>
                          </div>
                          
                          <div className="flex justify-between items-center mt-2.5 text-xs">
                            <span className="font-bold text-white">{formatCurrency(inv.invoice_amount)}</span>
                            <span className="text-[10px] text-slate-500">{inv.invoice_number}</span>
                          </div>
                          
                          <div className="mt-2 text-[10px] text-slate-500 flex justify-between">
                            <span>PO: {inv.purchase_order_number || 'N/A'}</span>
                            {inv.exception && (
                              <span className="text-red-400 flex items-center gap-0.5">
                                <AlertTriangle className="w-3 h-3" /> {inv.exception.exception_type}
                              </span>
                            )}
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                </div>

                {/* Right Side: 3-Way Match Visualizer */}
                <div className="lg:col-span-8 space-y-6">
                  {selectedInvoice ? (
                    <div className="bg-[#0f1524]/60 border border-slate-800/80 rounded-2xl p-6 shadow-sm space-y-6">
                      {/* Matching Header */}
                      <div className="flex justify-between items-start border-b border-slate-800 pb-4">
                        <div>
                          <h3 className="text-lg font-bold text-white">Cross-Referencing Audit Ledger</h3>
                          <p className="text-xs text-slate-400">Comparing Invoice {selectedInvoice.invoice_number} against matched ledger documentation.</p>
                        </div>
                        <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border ${
                          selectedInvoice.matching_result === 'THREE_WAY_OK'
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                            : 'bg-red-500/10 text-red-400 border-red-500/20'
                        }`}>
                          {selectedInvoice.matching_result === 'THREE_WAY_OK' ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
                          {selectedInvoice.matching_result.replace(/_/g, ' ')}
                        </span>
                      </div>

                      {/* Document Box Cards */}
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {/* 1. Invoice Document */}
                        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 space-y-3 shadow-inner">
                          <h4 className="text-xs font-bold text-slate-400 flex items-center gap-1.5">
                            <FileText className="w-4 h-4 text-emerald-400" /> 1. Extracted Invoice
                          </h4>
                          <div className="text-xs space-y-1.5 text-slate-300">
                            <div className="flex justify-between"><span className="text-slate-500">Invoice ID</span><span className="font-semibold text-white">{selectedInvoice.invoice_number}</span></div>
                            <div className="flex justify-between"><span className="text-slate-500">Vendor</span><span className="font-semibold truncate text-white">{selectedInvoice.vendor_name}</span></div>
                            <div className="flex justify-between"><span className="text-slate-500">Grand Total</span><span className="font-bold text-emerald-400">{formatCurrency(selectedInvoice.invoice_amount)}</span></div>
                            <div className="flex justify-between"><span className="text-slate-500">Terms</span><span className="font-semibold text-white">{selectedInvoice.payment_terms}</span></div>
                            <div className="flex justify-between"><span className="text-slate-500">PO Ref</span><span className="font-semibold text-white">{selectedInvoice.purchase_order_number}</span></div>
                          </div>
                        </div>

                        {/* 2. Purchase Order Ledger */}
                        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 space-y-3 shadow-inner">
                          <h4 className="text-xs font-bold text-slate-400 flex items-center gap-1.5">
                            <Building className="w-4 h-4 text-indigo-400" /> 2. Purchase Order
                          </h4>
                          {getMatchedPO(selectedInvoice) ? (
                            <div className="text-xs space-y-1.5 text-slate-300">
                              <div className="flex justify-between"><span className="text-slate-500">PO Number</span><span className="font-semibold text-white">{getMatchedPO(selectedInvoice)?.po_number}</span></div>
                              <div className="flex justify-between"><span className="text-slate-500">Auth Total</span><span className="font-bold text-white">{formatCurrency(getMatchedPO(selectedInvoice)?.total_amount || 0)}</span></div>
                              <div className="flex justify-between"><span className="text-slate-500">Dept</span><span className="font-semibold text-white">{getMatchedPO(selectedInvoice)?.department}</span></div>
                              <div className="flex justify-between"><span className="text-slate-500">Issued</span><span className="font-semibold text-white">{getMatchedPO(selectedInvoice)?.issue_date}</span></div>
                              <div className="flex justify-between"><span className="text-slate-500">Status</span><span className="font-semibold text-emerald-400">{getMatchedPO(selectedInvoice)?.status}</span></div>
                            </div>
                          ) : (
                            <div className="text-xs text-red-400 flex items-start gap-1 p-2 bg-red-500/5 border border-red-500/10 rounded-lg">
                              <AlertCircle className="w-4 h-4 shrink-0" />
                              <span>No matching PO found in system.</span>
                            </div>
                          )}
                        </div>

                        {/* 3. Goods Receipt Receipt */}
                        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 space-y-3 shadow-inner">
                          <h4 className="text-xs font-bold text-slate-400 flex items-center gap-1.5">
                            <CheckCircle2 className="w-4 h-4 text-teal-400" /> 3. Goods Receipt
                          </h4>
                          {getMatchedGR(selectedInvoice) ? (
                            <div className="text-xs space-y-1.5 text-slate-300">
                              <div className="flex justify-between"><span className="text-slate-500">Receipt ID</span><span className="font-semibold text-white">{getMatchedGR(selectedInvoice)?.receipt_number}</span></div>
                              <div className="flex justify-between"><span className="text-slate-500">Receipt Date</span><span className="font-semibold text-white">{getMatchedGR(selectedInvoice)?.received_date}</span></div>
                              <div className="flex justify-between"><span className="text-slate-500">Receipt Status</span><span className="font-semibold text-emerald-400">{getMatchedGR(selectedInvoice)?.status}</span></div>
                              <div className="text-[10px] text-slate-500 border-t border-slate-800 pt-1.5 mt-1.5">
                                Verified item counts match PO line details.
                              </div>
                            </div>
                          ) : (
                            <div className="text-xs text-amber-400 flex items-start gap-1 p-2 bg-amber-500/5 border border-amber-500/10 rounded-lg">
                              <AlertCircle className="w-4 h-4 shrink-0" />
                              <span>No Goods Receipt registered.</span>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Exception Callout & AI Routing Feedback Loop */}
                      {selectedInvoice.exception && (
                        <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-5 space-y-4">
                          <div className="flex justify-between items-start">
                            <div className="flex gap-2">
                              <AlertTriangle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                              <div>
                                <h4 className="text-sm font-bold text-white flex items-center gap-1.5">
                                  System Exception flagged: <span className="bg-red-500/10 text-red-400 border border-red-500/20 px-2 py-0.2 rounded text-[10px] font-bold">{selectedInvoice.exception.exception_type}</span>
                                </h4>
                                <p className="text-xs text-red-300/80 mt-1 leading-relaxed">{selectedInvoice.exception.description}</p>
                              </div>
                            </div>
                            <span className="bg-slate-900 border border-slate-800 text-[10px] text-slate-400 p-1.5 rounded-lg px-2 text-right">
                              AI Route Confidence: <span className="font-bold text-white">{selectedInvoice.exception.confidence_score.toFixed(1)}%</span>
                            </span>
                          </div>

                          <div className="border-t border-red-500/10 pt-4 flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
                            <div className="text-xs text-slate-400 flex items-center gap-1">
                              <span>Assigned Reviewer:</span>
                              <span className="font-bold text-slate-200 bg-slate-900 border border-slate-800 px-2 py-0.5 rounded flex items-center gap-1">
                                <Users className="w-3.5 h-3.5 text-teal-400" /> {selectedInvoice.exception.predicted_approver}
                              </span>
                            </div>
                            
                            {selectedInvoice.exception.status === 'OPEN' ? (
                              <div className="flex flex-col gap-2 w-full md:w-auto">
                                <input 
                                  type="text" 
                                  value={resolutionComment}
                                  onChange={(e) => setResolutionComment(e.target.value)}
                                  placeholder="Provide audit notes/justification..." 
                                  className="bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/40 w-full"
                                />
                                <div className="flex justify-end gap-2">
                                  <button
                                    onClick={() => handleResolveException(selectedInvoice.id, 'PAY_OVERRIDE')}
                                    className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-3 py-1.5 rounded-lg font-bold transition-all"
                                  >
                                    Override & Pay
                                  </button>
                                  <button
                                    onClick={() => handleResolveException(selectedInvoice.id, 'REQUEST_REVISED')}
                                    className="bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 text-xs px-3 py-1.5 rounded-lg font-bold transition-all"
                                  >
                                    Request Revised Bill
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <span className="text-xs text-emerald-400 bg-emerald-500/5 border border-emerald-500/10 p-2 rounded-lg flex items-center gap-1.5">
                                <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Exception Resolved: {selectedInvoice.exception.resolution_action} ({selectedInvoice.exception.comments})
                              </span>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Decision Options */}
                      {selectedInvoice.status !== 'PAID' && selectedInvoice.status !== 'REJECTED' && !selectedInvoice.exception && (
                        <div className="border-t border-slate-800 pt-6 flex justify-between items-center">
                          <div className="text-xs text-slate-400 flex items-center gap-1">
                            <CheckCircle2 className="w-4 h-4 text-emerald-500" /> All 3-way match items reconciled perfectly. Ready for payment routing.
                          </div>
                          <div className="flex gap-2">
                            {selectedInvoice.status !== 'APPROVED' && (
                              <button 
                                onClick={() => handleAction(selectedInvoice.id, 'approve')}
                                className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-4 py-2 rounded-xl font-bold transition-all"
                              >
                                Approve Payment
                              </button>
                            )}
                            {selectedInvoice.status === 'APPROVED' && (
                              <button 
                                onClick={() => handleAction(selectedInvoice.id, 'pay')}
                                className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-4 py-2 rounded-xl font-bold transition-all flex items-center gap-1"
                              >
                                <DollarSign className="w-4 h-4" /> Execute Settle Payment
                              </button>
                            )}
                            <button 
                              onClick={() => handleAction(selectedInvoice.id, 'reject')}
                              className="bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-400 text-xs px-4 py-2 rounded-xl font-bold transition-all"
                            >
                              Reject Invoice
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="bg-[#0f1524]/60 border border-slate-800/80 rounded-2xl p-12 text-center text-slate-500 italic shadow-sm">
                      Select an invoice from the verification sidebar to run the 3-Way Match inspect ledger.
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: TREASURY SETTINGS */}
          {activeTab === 'settings' && (
            <div className="space-y-8 animate-fade-in">
              <div>
                <h2 className="text-2xl font-bold tracking-tight text-white">Treasury Configuration</h2>
                <p className="text-sm text-slate-400">Configure parameters governing capital allocation models, cash safety margins, and ledger balances.</p>
              </div>

              <div className="max-w-2xl bg-[#0f1524]/60 border border-slate-800/80 rounded-2xl p-8 space-y-6 shadow-sm">
                <div className="space-y-6">
                  {/* Slider: Cost of Capital */}
                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <label className="text-sm font-bold text-slate-300">Opportunity Cost of Capital (WACC / yield threshold)</label>
                      <span className="text-sm font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded">
                        {settings.cost_of_capital.toFixed(1)}%
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 leading-normal">
                      The threshold at which early discount payments represent value-add returns for your firm. Discount yields above this rate are flagged as optimal early payment opportunities.
                    </p>
                    <input 
                      type="range" 
                      min="2.0" 
                      max="15.0" 
                      step="0.5"
                      value={settings.cost_of_capital}
                      onChange={(e) => handleUpdateSettings({ ...settings, cost_of_capital: parseFloat(e.target.value) })}
                      className="w-full h-1.5 bg-slate-900 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                    />
                    <div className="flex justify-between text-[10px] text-slate-600 font-semibold"><span>2.0%</span><span>8.0%</span><span>15.0%</span></div>
                  </div>

                  {/* Input: Minimum Liquidity Safety Margin */}
                  <div className="space-y-2">
                    <label className="text-sm font-bold text-slate-300">Minimum Treasury Liquidity Safety Threshold</label>
                    <p className="text-xs text-slate-500 leading-normal">
                      The safety cash reserve your firm preserves. Early payment suggestions will be suppressed if executing them violates this safety margin.
                    </p>
                    <div className="relative rounded-xl shadow-sm">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <span className="text-slate-500 sm:text-sm">$</span>
                      </div>
                      <input 
                        type="number" 
                        value={settings.minimum_liquidity_threshold}
                        onChange={(e) => handleUpdateSettings({ ...settings, minimum_liquidity_threshold: parseFloat(e.target.value) || 0 })}
                        className="bg-slate-950/80 border border-slate-800 rounded-xl pl-8 pr-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-emerald-500/40 w-full"
                      />
                    </div>
                  </div>

                  {/* Input: Current Cash Balance */}
                  <div className="space-y-2">
                    <label className="text-sm font-bold text-slate-300">Simulated Ledger Cash Balance</label>
                    <p className="text-xs text-slate-500 leading-normal">
                      Current cash reserves. Payments executed from this dashboard deduct directly from this ledger balance.
                    </p>
                    <div className="relative rounded-xl shadow-sm">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <span className="text-slate-500 sm:text-sm">$</span>
                      </div>
                      <input 
                        type="number" 
                        value={settings.cash_balance}
                        onChange={(e) => handleUpdateSettings({ ...settings, cash_balance: parseFloat(e.target.value) || 0 })}
                        className="bg-slate-950/80 border border-slate-800 rounded-xl pl-8 pr-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-emerald-500/40 w-full"
                      />
                    </div>
                  </div>
                  {/* Connected Vendors Info */}
                  <div className="pt-4 border-t border-slate-800 flex justify-between text-xs text-slate-500">
                    <span>Connected Ledger Suppliers:</span>
                    <span className="font-semibold text-slate-300">{vendors.length} active</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 5: SUPPLIER PORTAL */}
          {activeTab === 'portal' && (
            <div className="space-y-8 animate-fade-in">
              <div className="border border-indigo-500/20 bg-indigo-500/5 rounded-2xl p-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div>
                  <h2 className="text-xl font-bold text-white flex items-center gap-2">
                    <Building className="w-5 h-5 text-indigo-400" /> Supplier Self-Service Portal
                  </h2>
                  <p className="text-xs text-slate-400 mt-1">
                    Demo view of what suppliers see. Vendors log in to track invoices, adjust bank accounts, or request discount acceleration.
                  </p>
                </div>
                <span className="bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 px-3 py-1 rounded-full text-xs font-semibold">
                  Mock Identity: Olivia Wilson Consulting
                </span>
              </div>

              {/* Supplier Portal Layout */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
                {/* Invoice list for Supplier */}
                <div className="lg:col-span-7 bg-[#0f1524]/60 border border-slate-800/80 rounded-2xl p-6 shadow-sm space-y-6">
                  <h3 className="text-sm font-bold text-slate-300">Olivia Wilson Billing Ledgers</h3>
                  <div className="space-y-3">
                    {invoices.filter(i => i.vendor_name.includes('Olivia Wilson') || i.vendor_name.includes('Acme')).map((inv) => (
                      <div key={inv.id} className="bg-slate-950/40 border border-slate-800/80 rounded-xl p-4 flex justify-between items-center hover:border-indigo-500/20 transition-all">
                        <div>
                          <p className="font-semibold text-sm text-white">{inv.invoice_number}</p>
                          <div className="flex gap-4 text-xs text-slate-500 mt-1">
                            <span>Billed: {formatCurrency(inv.invoice_amount)}</span>
                            <span>Due Date: {formatDate(inv.due_date)}</span>
                          </div>
                        </div>

                        <div className="flex items-center gap-3">
                          <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                            inv.status === 'PAID'
                              ? 'bg-emerald-500/10 text-emerald-400'
                              : 'bg-amber-500/10 text-amber-400'
                          }`}>
                            {inv.status}
                          </span>
                          
                          {inv.status !== 'PAID' && inv.early_payment_discount_percentage > 0 && (
                            <button
                              onClick={() => {
                                setPortalSelectedInvoice(inv);
                              }}
                              className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs px-3 py-1.5 rounded-lg font-bold transition-all"
                            >
                              Request Early Pay
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Supplier Bank / Term Detail */}
                <div className="lg:col-span-5 space-y-6">
                  <div className="bg-[#0f1524]/60 border border-slate-800/80 rounded-2xl p-6 shadow-sm space-y-4">
                    <h3 className="text-sm font-bold text-slate-300">Supplier Banking Credentials</h3>
                    <div className="space-y-3 text-xs">
                      <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                        <p className="text-slate-500">Bank Name</p>
                        <p className="font-semibold text-white mt-1">CitiBank</p>
                      </div>
                      <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                        <p className="text-slate-500">Routing Transit Number (RTN)</p>
                        <p className="font-semibold text-white mt-1">021000089</p>
                      </div>
                      <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                        <p className="text-slate-500">Depositary Account Number (DAN)</p>
                        <p className="font-semibold text-white mt-1">******8832</p>
                      </div>
                    </div>
                  </div>

                  {portalSelectedInvoice && (
                    <div className="bg-[#0f1524]/60 border border-indigo-500/30 rounded-2xl p-6 shadow-sm space-y-4 animate-fade-in">
                      <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
                        <Calendar className="w-4.5 h-4.5 text-indigo-400" /> Apply Early Discount Settlement
                      </h3>
                      <p className="text-xs text-slate-400 leading-normal">
                        Accept early payment terms for invoice **{portalSelectedInvoice.invoice_number}**. Billed amount will be discounted to settle immediately.
                      </p>

                      <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800/80 text-xs space-y-2">
                        <div className="flex justify-between"><span className="text-slate-500">Original Total</span><span className="font-semibold text-white">{formatCurrency(portalSelectedInvoice.invoice_amount)}</span></div>
                        <div className="flex justify-between"><span className="text-slate-500">Discount Offered ({ (portalSelectedInvoice.early_payment_discount_percentage * 100).toFixed(0) }%)</span><span className="font-semibold text-emerald-400">-{formatCurrency(portalSelectedInvoice.cash_savings)}</span></div>
                        <div className="flex justify-between border-t border-slate-800 pt-2 mt-2 font-bold"><span className="text-slate-400">Accelerated Payout</span><span className="text-emerald-400">{formatCurrency(portalSelectedInvoice.invoice_amount - portalSelectedInvoice.cash_savings)}</span></div>
                      </div>

                      <button
                        onClick={async () => {
                          if (portalSelectedInvoice) {
                            await handleAction(portalSelectedInvoice.id, 'approve');
                            await handleAction(portalSelectedInvoice.id, 'pay');
                            setPortalSelectedInvoice(null);
                          }
                        }}
                        className="w-full bg-indigo-600 hover:bg-indigo-500 text-white p-2.5 rounded-xl text-xs font-bold transition-all"
                      >
                        Accept Terms & Request Payout
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

        </main>
      </div>
    </div>
  );
}
