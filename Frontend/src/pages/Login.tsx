import { useEffect, useState } from "react";
import { useSignIn, useAuth } from "@clerk/clerk-react";
import { useNavigate } from "react-router-dom";
import { TrendingUp, Shield, Activity, Coins } from "lucide-react";

export default function Login() {
  const { signIn, isLoaded: signInLoaded } = useSignIn();
  const { isSignedIn, isLoaded: authLoaded } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoaded && isSignedIn) {
      navigate("/dashboard", { replace: true });
    }
  }, [isSignedIn, authLoaded, navigate]);

  const handleGoogleLogin = async () => {
    if (!signInLoaded) return;
    setError(null);
    try {
      await signIn.authenticateWithRedirect({
        strategy: "oauth_google",
        redirectUrl: `${window.location.origin}/sso-callback`,
        redirectUrlComplete: `${window.location.origin}/dashboard`,
      });
    } catch (err: any) {
      console.error("Clerk OAuth error:", err);
      setError(err.message || "An error occurred during Google sign in.");
    }
  };

  return (
    <div className="min-h-screen bg-[#070a13] text-slate-100 font-sans flex overflow-hidden">
      {/* Decorative background grid and ambient glows */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_80%_at_50%_-20%,rgba(16,185,129,0.08),rgba(255,255,255,0))] pointer-events-none" />
      <div className="absolute top-0 left-0 w-full h-full bg-[linear-gradient(to_right,#0f172a10_1px,transparent_1px),linear-gradient(to_bottom,#0f172a10_1px,transparent_1px)] bg-[size:4rem_4rem] pointer-events-none" />

      {/* Left Column: Premium SaaS Value Prop */}
      <div className="hidden lg:flex lg:w-1/2 bg-[#0c1120] relative flex-col justify-between p-16 border-r border-slate-900 overflow-hidden">
        {/* Glow behind logo */}
        <div className="absolute -top-40 -left-40 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl" />
        
        {/* Logo and Brand */}
        <div className="flex items-center gap-3 relative z-10">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center shadow-lg shadow-emerald-500/20">
            <TrendingUp className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              VendorPulse
              <span className="text-[9px] uppercase font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded-full">Enterprise</span>
            </h1>
            <p className="text-[10px] text-slate-400">AP Automation & Cash Flow Optimization</p>
          </div>
        </div>

        {/* Feature Highlights */}
        <div className="space-y-12 my-auto max-w-md relative z-10">
          <div className="space-y-4">
            <span className="text-xs uppercase font-bold tracking-widest text-emerald-400">AP & Treasury Engine</span>
            <h2 className="text-3xl font-extrabold text-white leading-tight">
              Unlock yield from your accounts payable.
            </h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Automate 3-way invoice matching, dynamic discount optimization, and treasury capital routing in a single consolidated workspace.
            </p>
          </div>

          <div className="space-y-6">
            <div className="flex gap-4 items-start">
              <div className="p-3 bg-emerald-500/5 border border-emerald-500/10 rounded-xl text-emerald-400 shrink-0">
                <Coins className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">Dynamic Capital Optimization</h3>
                <p className="text-xs text-slate-400 mt-1">Capture up to 24% APR implied yields via automated supplier early payment negotiations.</p>
              </div>
            </div>

            <div className="flex gap-4 items-start">
              <div className="p-3 bg-emerald-500/5 border border-emerald-500/10 rounded-xl text-emerald-400 shrink-0">
                <Shield className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">Smart 3-Way Match Verification</h3>
                <p className="text-xs text-slate-400 mt-1">Cross-reference invoices against POs and Goods Receipts with instant line-item mismatch detection.</p>
              </div>
            </div>

            <div className="flex gap-4 items-start">
              <div className="p-3 bg-emerald-500/5 border border-emerald-500/10 rounded-xl text-emerald-400 shrink-0">
                <Activity className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">Real-time Treasury Forecasting</h3>
                <p className="text-xs text-slate-400 mt-1">Simulate corporate cash outflows under different discount capture velocities.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Footer Meta */}
        <div className="text-xs text-slate-500 flex justify-between items-center relative z-10 border-t border-slate-900 pt-8">
          <span>© 2026 VendorPulse Technologies</span>
          <span className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            SOC2 Certified
          </span>
        </div>
      </div>

      {/* Right Column: Beautiful Login Card */}
      <div className="w-full lg:w-1/2 flex flex-col justify-center items-center p-8 sm:p-16 relative">
        {/* Glow behind login card */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-emerald-500/5 rounded-full blur-3xl pointer-events-none" />

        <div className="w-full max-w-md bg-[#0f1424]/40 border border-slate-800/80 rounded-3xl p-8 sm:p-10 shadow-2xl backdrop-blur-md relative z-10">
          <div className="text-center space-y-3 mb-8">
            <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">Welcome to VendorPulse</h2>
            <p className="text-sm text-slate-400">Sign in to your enterprise billing workspace</p>
          </div>

          {error && (
            <div className="mb-6 bg-red-500/5 border border-red-500/10 text-red-400 text-xs p-3.5 rounded-xl text-center leading-relaxed">
              {error}
            </div>
          )}

          {/* Social Sign-in Button */}
          <button
            onClick={handleGoogleLogin}
            disabled={!signInLoaded}
            className="w-full bg-[#1e293b]/50 hover:bg-[#1e293b]/80 text-white font-medium p-3.5 rounded-xl border border-slate-800 hover:border-slate-700 transition-all flex items-center justify-center gap-3 group disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {/* Google Icon */}
            <svg className="w-5 h-5 shrink-0" viewBox="0 0 24 24">
              <path
                fill="#EA4335"
                d="M12 5.04c1.62 0 3.08.56 4.22 1.64l3.15-3.15C17.45 1.68 14.96 1 12 1 7.35 1 3.4 3.65 1.48 7.5l3.77 2.92C6.18 7.37 8.87 5.04 12 5.04z"
              />
              <path
                fill="#4285F4"
                d="M23.49 12.27c0-.81-.07-1.59-.2-2.36H12v4.47h6.44c-.28 1.47-1.11 2.71-2.36 3.55l3.66 2.84c2.14-1.97 3.75-4.87 3.75-8.5z"
              />
              <path
                fill="#FBBC05"
                d="M5.25 10.42a8.39 8.39 0 0 1 0 3.16l-3.77 2.92A11.967 11.967 0 0 1 1 12c0-1.63.32-3.18.91-4.6l3.34 2.59.001.43z"
              />
              <path
                fill="#34A853"
                d="M12 23c3.24 0 5.97-1.07 7.96-2.92l-3.66-2.84c-1.1.74-2.51 1.18-4.3 1.18-3.13 0-5.82-2.33-6.77-5.38l-3.77 2.92C3.4 20.35 7.35 23 12 23z"
              />
            </svg>
            <span className="text-sm font-semibold tracking-wide">Continue with Google</span>
          </button>

          {/* Decorative Divider */}
          <div className="relative my-8">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-slate-800" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-[#0f1424] px-4 text-slate-500 font-semibold tracking-wider">Enterprise Security</span>
            </div>
          </div>

          <div className="space-y-4">
            <div className="text-center">
              <p className="text-xs text-slate-500">
                Contact your IT administrator to request workspace access or change organization roles.
              </p>
            </div>
          </div>
        </div>

        {/* Brand version info for mobile */}
        <div className="lg:hidden mt-8 text-xs text-slate-600 text-center flex flex-col gap-1.5">
          <span>© 2026 VendorPulse Technologies</span>
          <span className="flex items-center justify-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            SOC2 Certified
          </span>
        </div>
      </div>
    </div>
  );
}
