import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { AudioLines, LogIn, ArrowLeft } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

export default function SignIn() {
  const navigate = useNavigate();
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (email && password) {
      setLoading(true);
      setError('');
      try {
        const { error } = await signIn(email, password);
        if (error) {
          setError(error.message);
        } else {
          navigate('/profile');
        }
      } catch {
        setError('An unexpected error occurred.');
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4 relative overflow-hidden">
      {/* Background glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-violet-600/10 rounded-full blur-[150px] pointer-events-none" />

      {/* Back button */}
      <div className="absolute top-8 left-8">
        <Link to="/" className="flex items-center gap-2 text-textSecondary hover:text-zinc-900 transition-colors">
          <ArrowLeft size={20} /> Back to Home
        </Link>
      </div>

      <div className="w-full max-w-[420px] z-10">
        <div className="text-center mb-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-violet-600 shadow-sm mb-4">
            <AudioLines size={28} className="text-zinc-900" />
          </div>
          <h1 className="text-3xl font-bold text-zinc-900 mb-2 tracking-wide">Welcome Back</h1>
          <p className="text-textSecondary text-sm">Enter your credentials to access your account</p>
        </div>

        <div className="card animate-in fade-in zoom-in-95 duration-500 delay-150 fill-mode-both">
          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              {error}
            </div>
          )}
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-semibold text-textSecondary uppercase tracking-wider mb-2.5">
                Email Address
              </label>
              <input
                type="email"
                placeholder="you@example.com"
                className="input-field"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-semibold text-textSecondary uppercase tracking-wider mb-2.5">
                Password
              </label>
              <input
                type="password"
                placeholder="••••••••"
                className="input-field"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
              />
            </div>

            <div className="pt-2">
              <button type="submit" disabled={!email || !password || loading} className="btn-primary w-full py-4 text-base flex justify-center items-center">
                {loading ? (
                  <span className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></span>
                ) : (
                  <>
                    <LogIn size={20} className="mr-2" />
                    Sign In
                  </>
                )}
              </button>
            </div>
          </form>

          <div className="mt-6 text-center text-sm text-textSecondary">
            Don't have an account?{' '}
            <Link to="/signup" className="text-violet-400 hover:text-violet-800 font-medium transition-colors">
              Sign Up
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
