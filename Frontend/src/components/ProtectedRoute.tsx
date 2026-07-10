import { useAuth } from "@clerk/clerk-react";
import { Navigate } from "react-router-dom";

export default function ProtectedRoute({ children }: { children: React.JSX.Element }) {
  const { isLoaded, isSignedIn } = useAuth();

  if (!isLoaded) {
    return (
      <div className="min-h-screen bg-[#0b0f19] flex flex-col justify-center items-center text-slate-100 font-sans">
        <div className="relative">
          <div className="w-16 h-16 border-4 border-emerald-500/30 border-t-emerald-400 rounded-full animate-spin"></div>
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-emerald-400 font-bold text-xs">VP</div>
        </div>
        <h2 className="mt-6 text-xl font-medium tracking-wide text-slate-300">Authenticating...</h2>
        <p className="mt-2 text-sm text-slate-500 animate-pulse">Verifying credentials with Clerk</p>
      </div>
    );
  }

  if (!isSignedIn) {
    return <Navigate to="/login" replace />;
  }

  return children;
}
