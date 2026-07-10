import { AuthenticateWithRedirectCallback } from "@clerk/clerk-react";

export default function SSOCallback() {
  return (
    <div className="min-h-screen bg-[#0b0f19] flex flex-col justify-center items-center text-slate-100 font-sans">
      <div className="relative">
        <div className="w-16 h-16 border-4 border-emerald-500/30 border-t-emerald-400 rounded-full animate-spin"></div>
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-emerald-400 font-bold text-xs">VP</div>
      </div>
      <h2 className="mt-6 text-xl font-medium tracking-wide text-slate-300">Completing Sign-In...</h2>
      <p className="mt-2 text-sm text-slate-500 animate-pulse">Syncing session with Clerk</p>
      <AuthenticateWithRedirectCallback 
        signInForceRedirectUrl="/dashboard" 
        signUpForceRedirectUrl="/dashboard"
        afterSignInUrl="/dashboard"
        afterSignUpUrl="/dashboard"
      />
    </div>
  );
}
