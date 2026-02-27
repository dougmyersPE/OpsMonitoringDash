import { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuthStore } from "../stores/auth";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      // IMPORTANT: /auth/login expects form body (OAuth2PasswordRequestForm), NOT JSON
      const params = new URLSearchParams();
      params.append("username", email); // field name is "username" per OAuth2 spec
      params.append("password", password);
      const { data } = await axios.post("/api/v1/auth/login", params, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
      login(data.access_token, email, data.role ?? "operator", rememberMe);
      navigate("/");
    } catch {
      setError("Invalid email or password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-950">
      {/* Subtle radial gradient behind the card */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_oklch(0.59_0.25_263_/_0.06)_0%,_transparent_70%)] pointer-events-none" />

      <div className="relative w-full max-w-sm px-4">
        {/* Logo mark */}
        <div className="flex flex-col items-center mb-8">
          <div className="h-12 w-12 rounded-2xl bg-indigo-600 flex items-center justify-center mb-4 shadow-lg shadow-indigo-500/20">
            <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6">
              <path d="M12 3L21 19H3L12 3Z" fill="white" fillOpacity="0.9" />
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-zinc-100 tracking-tight">Prophet Monitor</h1>
          <p className="text-zinc-500 text-sm mt-1">Sign in to your workspace</p>
        </div>

        {/* Form card */}
        <form
          onSubmit={handleSubmit}
          className="bg-zinc-900 border border-zinc-800 rounded-2xl p-7 space-y-5 shadow-xl shadow-black/30"
        >
          {error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-3.5 py-2.5">
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="email" className="text-zinc-400 text-xs font-medium">Email</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="you@company.com"
              className="bg-zinc-800 border-zinc-700 text-zinc-100 placeholder:text-zinc-600 focus-visible:ring-indigo-500/30 focus-visible:border-indigo-500/60 h-10"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="password" className="text-zinc-400 text-xs font-medium">Password</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="bg-zinc-800 border-zinc-700 text-zinc-100 focus-visible:ring-indigo-500/30 focus-visible:border-indigo-500/60 h-10"
            />
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              role="checkbox"
              aria-checked={rememberMe}
              onClick={() => setRememberMe((v) => !v)}
              className={`h-4 w-4 rounded border flex-shrink-0 flex items-center justify-center transition-colors ${
                rememberMe
                  ? "bg-indigo-600 border-indigo-600"
                  : "bg-transparent border-zinc-600 hover:border-zinc-400"
              }`}
            >
              {rememberMe && (
                <svg viewBox="0 0 12 12" fill="none" className="h-2.5 w-2.5">
                  <path d="M2 6l3 3 5-5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
            </button>
            <label
              onClick={() => setRememberMe((v) => !v)}
              className="text-sm text-zinc-400 cursor-pointer select-none"
            >
              Remember me
            </label>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full h-10 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
