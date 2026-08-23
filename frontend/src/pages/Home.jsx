import React from 'react';
import { useNavigate } from 'react-router-dom';
import { AudioLines, LogIn, UserPlus, ArrowRight } from 'lucide-react';

export default function Home() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background ambient glows */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-violet-600/20 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-violet-600/20 rounded-full blur-[120px] pointer-events-none" />

      <div className="w-full max-w-4xl flex flex-col items-center z-10">
        <div className="text-center mb-12 animate-in fade-in slide-in-from-bottom-8 duration-1000 ease-out">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-3xl bg-violet-600 shadow-sm mb-8">
            <AudioLines size={40} className="text-zinc-900" />
          </div>
          <h1 className="text-5xl sm:text-7xl font-extrabold tracking-tight text-zinc-900 mb-6">
            Aud<span className="text-violet-900 font-bold">Stories</span>
          </h1>
          <p className="text-textSecondary text-lg sm:text-xl font-medium max-w-2xl mx-auto leading-relaxed">
            Unleash the power of professional audio production. <br className="hidden sm:block" />
            Create breathtaking audio dramas and seamless audio books in minutes.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row gap-5 items-center w-full max-w-md animate-in fade-in zoom-in-95 duration-700 delay-300 fill-mode-both">
          <button
            onClick={() => navigate('/signup')}
            className="btn-primary w-full group py-4 text-base flex justify-center items-center"
          >
            <UserPlus size={20} className="mr-2" />
            Sign Up
            <ArrowRight size={18} className="ml-2 opacity-0 -ml-4 group-hover:opacity-100 group-hover:ml-2 group-hover:translate-x-1 transition-all" />
          </button>

          <button
            onClick={() => navigate('/signin')}
            className="w-full group py-4 px-6 text-base font-medium text-zinc-900 bg-white hover:bg-white border border-zinc-200 hover:border-zinc-300 rounded-xl transition-all duration-300 flex justify-center items-center backdrop-blur-sm shadow-sm"
          >
            <LogIn size={20} className="mr-2 text-violet-800" />
            Sign In
          </button>
        </div>
      </div>
    </div>
  );
}
