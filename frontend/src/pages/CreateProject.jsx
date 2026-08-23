import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, AudioLines, BookOpen, Loader2 } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { supabase } from '../supabase';
import { api } from '../api';

export default function CreateProject() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [format, setFormat] = useState('drama');
  const [unitName, setUnitName] = useState('');
  const [writerName, setWriterName] = useState('');
  const [narrationChoice, setNarrationChoice] = useState('self');
  const [aiVoiceProvider, setAiVoiceProvider] = useState('google');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { user } = useAuth();

  useEffect(() => {
    if (format === 'book' && !['self', 'ai', 'professional'].includes(narrationChoice)) {
      setNarrationChoice('self');
    } else if (format === 'drama' && narrationChoice !== 'self') {
      setNarrationChoice('self');
    }
  }, [format, narrationChoice]);

  const handleContinue = async (e) => {
    e.preventDefault();
    if (!name.trim() || !unitName.trim() || !user) return;
    
    setLoading(true);
    setError('');

    try {
      // 1. Create the Project
      const { data: projectData, error: projectError } = await supabase
        .from('projects')
        .insert({
          user_id: user.id,
          name,
          format,
          writer_name: writerName,
          narration_choice: narrationChoice,
          ai_voice_provider: aiVoiceProvider,
        })
        .select()
        .single();

      if (projectError) throw projectError;

      // 2. Create the Unit
      const { data: unitData, error: unitError } = await supabase
        .from('units')
        .insert({
          project_id: projectData.id,
          name: unitName,
        })
        .select()
        .single();

      if (unitError) throw unitError;

      await api.createProject({
        project_id: projectData.id,
        unit_id: unitData.id,
        name: projectData.name,
        unit_name: unitData.name,
        writer_name: projectData.writer_name || '',
        format: projectData.format,
        narration_choice: projectData.narration_choice,
        ai_voice_provider: projectData.ai_voice_provider || 'google',
      });

      navigate(`/projects/${projectData.id}/story`, {
        state: { 
          projectName: projectData.name, 
          unitName: unitData.name, 
          unitId: unitData.id, 
          format: projectData.format,
          narrationChoice: projectData.narration_choice,
          aiVoiceProvider: projectData.ai_voice_provider,
        }
      });
    } catch (err) {
      console.error("Error creating project:", err);
      setError(err.message || 'Failed to create project');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 py-12">
      <div className="w-full max-w-[480px]">
        {/* Logo Text Animation */}
        <div className="text-center mb-10 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-violet-600 shadow-sm mb-4">
            <AudioLines size={28} className="text-zinc-900" />
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-zinc-900 mb-2">
            Aud<span className="text-violet-900 font-bold">Stories</span>
          </h1>
          <p className="text-textSecondary text-sm font-medium">Professional audio production, simplified.</p>
        </div>

        {/* Card */}
        <div className="card animate-in fade-in zoom-in-95 duration-500 delay-150 fill-mode-both">
          <div className="text-center mb-8 border-b border-border pb-6">
            <h2 className="text-xl font-bold text-zinc-900 tracking-wide">New Project</h2>
            <p className="text-textSecondary mt-1.5 text-sm">Create your project & first unit</p>
          </div>

          {error && (
            <div className="mb-6 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleContinue} className="space-y-7">
            {/* Project Name Input */}
            <div>
              <label htmlFor="projectName" className="block text-sm font-semibold text-textSecondary uppercase tracking-wider mb-2.5">
                Project Name
              </label>
              <input
                id="projectName"
                type="text"
                placeholder="e.g. The Lord of the Rings"
                className="input-field"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>

            {/* Format Radio Group */}
            <div>
              <label className="block text-sm font-semibold text-textSecondary uppercase tracking-wider mb-3">
                Format
              </label>
              <div className="space-y-3.5">
                {/* Option 1: Audio Drama */}
                <label className={`
                  relative flex items-center p-5 rounded-xl border cursor-pointer transition-all duration-300 overflow-hidden
                  ${format === 'drama'
                    ? 'border-violet-500/50 bg-violet-500/10 shadow-[inset_0_0_20px_rgba(124,58,237,0.1)]'
                    : 'border-border hover:border-zinc-300 hover:bg-white'}
                `}>
                  {format === 'drama' && (
                    <div className="absolute top-0 right-0 w-32 h-32 bg-violet-500/20 rounded-full blur-3xl -mr-10 -mt-10 pointer-events-none" />
                  )}
                  <div className="flex-shrink-0 z-10">
                    <input
                      type="radio"
                      name="format"
                      value="drama"
                      className="sr-only"
                      checked={format === 'drama'}
                      onChange={() => setFormat('drama')}
                    />
                    <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all ${format === 'drama' ? 'border-violet-400 bg-transparent' : 'border-zinc-600 bg-white'
                      }`}>
                      <div className={`w-3 h-3 rounded-full transition-all ${format === 'drama' ? 'bg-violet-400 scale-100 shadow-sm' : 'bg-transparent scale-0'}`} />
                    </div>
                  </div>
                  <div className="ml-4 z-10">
                    <span className={`block text-base font-semibold ${format === 'drama' ? 'text-zinc-900' : 'text-textSecondary'}`}>
                      Audio Drama
                    </span>
                    <span className="block text-xs text-textSecondary mt-1 leading-relaxed">
                      Multiple characters, sound design, cinematic vibes.
                    </span>
                  </div>
                  <div className="ml-auto z-10">
                    <div className={`p-2.5 rounded-lg transition-colors ${format === 'drama' ? 'bg-violet-500/20 text-violet-800' : 'bg-white text-textMuted'}`}>
                      <AudioLines size={20} />
                    </div>
                  </div>
                </label>

                {/* Option 2: Audio Book */}
                <label className={`
                  relative flex items-center p-5 rounded-xl border cursor-pointer transition-all duration-300 overflow-hidden
                  ${format === 'book'
                    ? 'border-violet-500/50 bg-violet-500/10 shadow-[inset_0_0_20px_rgba(124,58,237,0.1)]'
                    : 'border-border hover:border-zinc-300 hover:bg-white'}
                `}>
                  {format === 'book' && (
                    <div className="absolute top-0 right-0 w-32 h-32 bg-violet-500/20 rounded-full blur-3xl -mr-10 -mt-10 pointer-events-none" />
                  )}
                  <div className="flex-shrink-0 z-10">
                    <input
                      type="radio"
                      name="format"
                      value="book"
                      className="sr-only"
                      checked={format === 'book'}
                      onChange={() => setFormat('book')}
                    />
                    <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all ${format === 'book' ? 'border-violet-400 bg-transparent' : 'border-zinc-600 bg-white'
                      }`}>
                      <div className={`w-3 h-3 rounded-full transition-all ${format === 'book' ? 'bg-violet-400 scale-100 shadow-sm' : 'bg-transparent scale-0'}`} />
                    </div>
                  </div>
                  <div className="ml-4 z-10">
                    <span className={`block text-base font-semibold ${format === 'book' ? 'text-zinc-900' : 'text-textSecondary'}`}>
                      Audio Book
                    </span>
                    <span className="block text-xs text-textSecondary mt-1 leading-relaxed">
                      Clean narrator production, clear storytelling.
                    </span>
                  </div>
                  <div className="ml-auto z-10">
                    <div className={`p-2.5 rounded-lg transition-colors ${format === 'book' ? 'bg-violet-500/20 text-violet-800' : 'bg-white text-textMuted'}`}>
                      <BookOpen size={20} />
                    </div>
                  </div>
                </label>
              </div>
            </div>

            {/* Unit Name Input (Chapter/Episode) */}
            <div className="animate-in fade-in slide-in-from-top-2 duration-300">
              <label htmlFor="unitName" className="block text-sm font-semibold text-textSecondary uppercase tracking-wider mb-2.5">
                {format === 'drama' ? 'Episode Name' : 'Chapter Name'}
              </label>
              <input
                id="unitName"
                type="text"
                placeholder={format === 'drama' ? 'e.g. Episode 1 — The Arrival' : 'e.g. Chapter 1 — The Beginning'}
                className="input-field"
                value={unitName}
                onChange={(e) => setUnitName(e.target.value)}
                required
              />
            </div>

            {/* Writer Name Input */}
            <div>
              <label htmlFor="writerName" className="block text-sm font-semibold text-textSecondary uppercase tracking-wider mb-2.5">
                Writer Name
              </label>
              <input
                id="writerName"
                type="text"
                placeholder="e.g. Jane Doe"
                className="input-field"
                value={writerName}
                onChange={(e) => setWriterName(e.target.value)}
              />
            </div>

            {/* Narration Choice (Audio Book only) */}
            {format === 'book' && (
              <div>
                <label className="block text-sm font-semibold text-textSecondary uppercase tracking-wider mb-2.5">
                  Narration
                </label>
                <div className="relative">
                  <select
                    className="input-field appearance-none cursor-pointer"
                    value={narrationChoice}
                    onChange={(e) => setNarrationChoice(e.target.value)}
                  >
                    <option value="self" className="bg-white">Self Narrated</option>
                    <option value="ai" className="bg-white">AI Voice</option>
                    <option value="professional" className="bg-white">Professional Narration</option>
                  </select>
                  <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4 text-textSecondary">
                    <svg className="w-4 h-4 fill-current" viewBox="0 0 20 20"><path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" /></svg>
                  </div>
                </div>
              </div>
            )}

            {/* AI Voice Provider (Conditional) */}
            {narrationChoice === 'ai' && (
              <div className="animate-in fade-in slide-in-from-top-2 duration-300">
                <label className="block text-sm font-semibold text-textSecondary uppercase tracking-wider mb-2.5">
                  AI Voice Engine
                </label>
                <div className="relative">
                  <select
                    className="input-field appearance-none cursor-pointer"
                    value={aiVoiceProvider}
                    onChange={(e) => setAiVoiceProvider(e.target.value)}
                  >
                    <option value="google" className="bg-white">Google AI Voice</option>
                  </select>
                  <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4 text-textSecondary">
                    <svg className="w-4 h-4 fill-current" viewBox="0 0 20 20"><path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" /></svg>
                  </div>
                </div>
              </div>
            )}

            {/* Submit Button */}
            <div className="pt-4">
              <button
                type="submit"
                disabled={!name.trim() || !unitName.trim() || loading}
                className="btn-primary w-full group py-4 text-base flex justify-center items-center"
              >
                {loading ? (
                  <>
                    <Loader2 className="animate-spin mr-2" size={18} />
                    Creating Project...
                  </>
                ) : (
                  <>
                    Continue Workflow <ArrowRight size={18} className="ml-2 group-hover:translate-x-1 transition-transform" />
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
