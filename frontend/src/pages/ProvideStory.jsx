import React, { useState, useRef } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import TopBar from '../components/TopBar';
import { ArrowRight, UploadCloud, Loader2, Sparkles, FileText } from 'lucide-react';
import { supabase } from '../supabase';
import { api } from '../api';

export default function ProvideStory() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const projectName = location.state?.projectName || `Project ${id}`;
  const unitName = location.state?.unitName;
  const displayProjectName = unitName ? `${projectName} - ${unitName}` : projectName;
  const format = location.state?.format || 'drama';

  const [text, setText] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [progressStatus, setProgressStatus] = useState(null); 
  const [errorMessage, setErrorMessage] = useState('');
  const [preview, setPreview] = useState(null);
  
  const fileInputRef = useRef(null);

  const handleTextChange = (e) => {
    const val = e.target.value;
    if (val.length <= 50000) {
      setText(val);
      setPreview(null);
    }
  };

  const handleFileDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer?.files[0] || e.target.files?.[0];
    const allowedExt = format === 'drama' ? ['.txt', '.fountain'] : ['.txt'];
    const ok = file && allowedExt.some((ext) => file.name.toLowerCase().endsWith(ext));
    if (!ok) {
      alert(`Please upload ${allowedExt.join(' or ')} file`);
      return;
    }
    
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target.result;
      setText(content.substring(0, 50000));
      setPreview(null);
    };
    reader.readAsText(file);
  };

  const triggerPreview = async () => {
    if (format !== 'drama' || !text.trim()) return;
    setIsPreviewing(true);
    setErrorMessage('');
    try {
      const response = await api.previewScript(id, { story_text: text });
      setPreview(response);
    } catch (err) {
      setErrorMessage(err.message || 'Preview failed. Please try again.');
    } finally {
      setIsPreviewing(false);
    }
  };

  const triggerAnalysis = async () => {
    if (format === 'drama' && preview?.diagnostics?.length > 0) {
      const proceed = window.confirm('Preview has parser warnings. Continue to Stage 1 anyway?');
      if (!proceed) return;
    }
    setIsAnalyzing(true);
    setProgressStatus('analyzing');
    setErrorMessage('');
    
    try {
      if (!location.state?.unitId) {
        throw new Error('Unit is missing. Please re-open this workflow from Project Details.');
      }

      if (location.state?.unitId) {
        const { error } = await supabase
          .from('units')
          .update({ story_text: text })
          .eq('id', location.state.unitId);
        
        if (error) throw error;
      }

      await api.saveStory(id, {
        unit_id: location.state.unitId,
        unit_name: location.state.unitName,
        story_text: text,
      });

      await api.runStage1(id);

      const maxAttempts = 240;
      for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        const status = await api.getStatus(id);
        if (status.status === 'awaiting_assets' || status.status === 'stage2' || status.status === 'done') {
          setProgressStatus('success');
          const nextPath = format === 'drama' ? `/projects/${id}/drama-dashboard` : `/projects/${id}/analysis`;
          navigate(nextPath, {
            state: {
              ...location.state,
              storyText: text,
            },
          });
          return;
        }
        if (status.status === 'failed') {
          throw new Error(status.error || 'Stage 1 failed');
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }

      throw new Error('Analysis is taking too long. Please try again.');
    } catch (err) {
      console.error("Failed to save story:", err);
      setProgressStatus('failed');
      setErrorMessage(err.message || 'Analysis failed. Please try again.');
      setIsAnalyzing(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar projectName={displayProjectName} step={1} totalSteps={4} />
      
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-10">
        <div className="flex flex-col lg:flex-row gap-10">
          
          {/* Left Panel */}
          <div className="flex-1 space-y-6 animate-in fade-in slide-in-from-left-8 duration-700">
            <div>
              <h1 className="text-3xl font-extrabold text-zinc-900 tracking-tight flex items-center gap-3">
                <FileText className="text-violet-400" /> Your Story
              </h1>
              <p className="text-textSecondary mt-2">Paste your script or story text below</p>
            </div>

            <div className="relative group">
              <textarea
                className="script-textarea min-h-[420px] shadow-2xl shadow-black/50"
                placeholder="Paste your script, chapter, or story here..."
                value={text}
                onChange={handleTextChange}
                disabled={isAnalyzing}
              />
              <div className="absolute bottom-4 right-4 text-xs font-mono text-zinc-600 bg-white/90 px-3 py-1.5 rounded-lg border border-zinc-200 shadow-lg pointer-events-none transition-opacity group-hover:opacity-100 opacity-70">
                {text.length.toLocaleString()} / 50,000
              </div>
            </div>

            {/* Drop Zone */}
            <div 
              className={`border-2 border-dashed rounded-2xl p-10 text-center transition-all duration-300 relative overflow-hidden group
                ${isAnalyzing ? 'opacity-50 pointer-events-none border-zinc-200 bg-white' : 'border-zinc-200 hover:border-violet-500/50 hover:bg-violet-500/5 cursor-pointer hover:shadow-sm'}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleFileDrop}
              onClick={() => !isAnalyzing && fileInputRef.current?.click()}
            >
              <div className="absolute inset-0 bg-gradient-to-b from-transparent to-black/20 pointer-events-none" />
              <input 
                type="file" 
                ref={fileInputRef} 
                onChange={handleFileDrop} 
                accept={format === 'drama' ? '.txt,.fountain' : '.txt'} 
                className="hidden" 
              />
              <div className="w-16 h-16 rounded-full bg-white border border-zinc-200 flex items-center justify-center mx-auto mb-4 group-hover:scale-110 group-hover:bg-violet-500/20 transition-all duration-500">
                <UploadCloud className="h-8 w-8 text-zinc-600 group-hover:text-violet-400 transition-colors" />
              </div>
              <p className="text-sm font-semibold text-textSecondary uppercase tracking-widest group-hover:text-zinc-900 transition-colors">
                Drop your <span className="text-violet-400">{format === 'drama' ? '.fountain/.txt' : '.txt'}</span> file here
              </p>
            </div>

            <button
              className="btn-primary w-full py-4 text-lg mt-4 shadow-2xl"
              disabled={text.trim().length === 0 || isAnalyzing}
              onClick={triggerAnalysis}
            >
              {isAnalyzing ? (
                <>
                  <Loader2 className="animate-spin mr-3" size={20} />
                  Analysing with AI...
                </>
              ) : (
                <>
                  <Sparkles size={20} className="mr-2" /> Analyse Story <ArrowRight size={20} className="ml-2" />
                </>
              )}
            </button>
            {format === 'drama' && (
              <button
                className="btn-secondary w-full py-3 text-base"
                disabled={text.trim().length === 0 || isAnalyzing || isPreviewing}
                onClick={triggerPreview}
              >
                {isPreviewing ? 'Previewing script...' : 'Preview Script'}
              </button>
            )}
            {progressStatus === 'failed' && (
              <p className="text-error text-sm text-center font-medium mt-3 bg-error/10 py-2 rounded-lg border border-error/20">
                {errorMessage || 'Analysis failed. Please try again.'}
              </p>
            )}
            {preview && format === 'drama' && (
              <div className="card bg-white/60 border-zinc-200 space-y-3">
                <h3 className="font-bold text-zinc-900 uppercase tracking-wider text-sm">
                  Script Preview
                </h3>
                <p className="text-sm text-textSecondary">
                  Scenes: {preview.scenes?.length || 0} | Warnings: {preview.diagnostics?.length || 0}
                </p>
                {(preview.diagnostics || []).slice(0, 5).map((item, idx) => (
                  <div key={`${item.code}-${idx}`} className="text-xs rounded-lg border border-zinc-200 p-2">
                    <span className="font-semibold">{item.severity.toUpperCase()}</span> [{item.code}] line {item.line}: {item.message}
                  </div>
                ))}
                {(preview.scenes || []).slice(0, 4).map((scene) => (
                  <div key={scene.scene_index} className="text-xs rounded-lg border border-zinc-200 p-2 space-y-1">
                    <p className="font-semibold">{scene.heading}</p>
                    <p>Speakers: {(scene.speakers || []).join(', ') || 'None'}</p>
                    <p>SFX: {(scene.sfx || []).join(', ') || 'None'}</p>
                    <p>Ambience: {(scene.ambience || []).join(', ') || 'None'}</p>
                    <p>Energy/Mood: {scene.energy_level} / {scene.primary_emotion}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right Panel */}
          <div className="lg:w-[340px] space-y-6 animate-in fade-in slide-in-from-right-8 duration-700 delay-150 fill-mode-both">
            {isAnalyzing ? (
              <div className="card text-center py-16 flex flex-col items-center justify-center relative overflow-hidden border-violet-500/30 shadow-sm">
                <div className="absolute inset-0 bg-violet-500/5 animate-pulse" />
                <div className="relative z-10">
                  <div className="relative w-16 h-16 mx-auto mb-6">
                    <div className="absolute inset-0 border-4 border-violet-500/30 rounded-full"></div>
                    <div className="absolute inset-0 border-4 border-violet-500 rounded-full border-t-transparent animate-spin"></div>
                  </div>
                  <h3 className="text-lg font-bold text-zinc-900 mb-2 tracking-wide">Analysing Story</h3>
                  <p className="text-sm text-violet-900/80 font-medium">Extracting characters & events...</p>
                </div>
              </div>
            ) : (
              <>
                <div className="card bg-white/60 border-zinc-200 relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-32 h-32 bg-violet-500/10 rounded-full blur-3xl -mr-16 -mt-16" />
                  <h3 className="font-bold text-zinc-900 mb-6 uppercase tracking-wider text-sm flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-violet-500" /> What happens next
                  </h3>
                  <ul className="space-y-6 relative z-10">
                    {[
                      { num: 1, text: "We analyse your story & extract assets" },
                      { num: 2, text: "You place or record audio files" },
                      { num: 3, text: "We render your cinematic audio" }
                    ].map((step, i) => (
                      <li key={i} className="flex gap-4 items-start group">
                        <div className="flex-shrink-0 mt-0.5">
                          <div className="w-6 h-6 rounded-full border border-zinc-300 bg-violet-100 flex items-center justify-center text-xs font-bold text-zinc-600 group-hover:border-violet-500/50 group-hover:text-violet-400 group-hover:bg-violet-500/10 transition-colors shadow-sm">
                            {step.num}
                          </div>
                        </div>
                        <span className="text-sm font-medium text-textSecondary group-hover:text-zinc-600 transition-colors leading-relaxed">
                          {step.text}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="card bg-violet-50 border-violet-500/20 relative overflow-hidden">
                  <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAiIGhlaWdodD0iMjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMiIgY3k9IjIiIHI9IjEiIGZpbGw9InJnYmEoMjU1LDI1NSwyNTUsMC4wNSkiLz48L3N2Zz4=')] opacity-50"></div>
                  <h3 className="font-bold text-zinc-900 mb-3 flex items-center gap-2 relative z-10 uppercase tracking-wider text-sm">
                    <span className="text-violet-400">💡</span> Pro Tips
                  </h3>
                  <p className="text-sm text-violet-900/70 leading-relaxed font-medium relative z-10">
                    {format === 'drama' 
                      ? "Use standard script format. Character names in CAPS before their dialogue. We will auto-detect speakers!"
                      : "Paste your chapter text. One narrator will read the entire text. Ensure chapter markers are clear."}
                  </p>
                </div>
              </>
            )}
          </div>

        </div>
      </main>
    </div>
  );
}
