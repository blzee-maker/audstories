import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import TopBar from '../components/TopBar';
import { ArrowRight, CheckCircle2, Circle, RefreshCw, Loader2, UploadCloud, PlayCircle, Music, Wind, Volume2, Trash2 } from 'lucide-react';
import { api } from '../api';

export default function PlaceAssets() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const projectName = location.state?.projectName || `Project ${id}`;
  const unitName = location.state?.unitName;
  const displayProjectName = unitName ? `${projectName} — ${unitName}` : projectName;
  const format = location.state?.format || 'drama';
  const isDrama = format === 'drama';

  const [assets, setAssets] = useState({ voice: [], music: [], ambience: [], sfx: [] });
  const [loadingAssets, setLoadingAssets] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [voiceMapState, setVoiceMapState] = useState({ loading: false, characters: [], defaultVoice: '', error: '' });
  const [activeTtsSpeaker, setActiveTtsSpeaker] = useState('');
  const [generatingAllSpeakers, setGeneratingAllSpeakers] = useState(false);
  const [pacingState, setPacingState] = useState({ loading: false, scenes: [], error: '' });
  const [pacingEdits, setPacingEdits] = useState({});
  const [savingPacing, setSavingPacing] = useState(false);

  const [isRendering, setIsRendering] = useState(false);
  const [renderStep, setRenderStep] = useState(0);

  const fileInputRef = useRef(null);
  const [activeUploadId, setActiveUploadId] = useState(null);
  const [activeUploadType, setActiveUploadType] = useState(null);
  const [activeRemoveId, setActiveRemoveId] = useState(null);

  const renderSteps = ['Resolving assets...', 'Rendering final audio...', 'Finishing output...'];

  const [refreshKey, setRefreshKey] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const loadRequirements = useCallback(async () => {
    try {
      setLoadingAssets(true);
      setLoadError('');
      const response = await api.getRequirements(id);
      const next = { voice: [], music: [], ambience: [], sfx: [] };
      for (const item of response.items || []) {
        if (!next[item.asset_kind]) continue;
        next[item.asset_kind].push({
          id: item.requirement_id,
          path: item.folder,
          desc: item.tts_text || item.descriptor,
          status: item.status,
        });
      }
      setAssets(next);
    } catch (err) {
      setLoadError(err.message || 'Failed to load requirements');
    } finally {
      setLoadingAssets(false);
    }
  }, [id]);


  const loadPacing = useCallback(async () => {
    if (!isDrama) {
      setPacingState({ loading: false, scenes: [], error: '' });
      setPacingEdits({});
      return;
    }
    setPacingState((prev) => ({ ...prev, loading: true, error: '' }));
    try {
      const response = await api.getPacing(id);
      setPacingState({
        loading: false,
        scenes: Array.isArray(response.scenes) ? response.scenes : [],
        error: '',
      });
      setPacingEdits((response.overrides && response.overrides.clips) || {});
    } catch (err) {
      setPacingState((prev) => ({
        ...prev,
        loading: false,
        error: err.message || 'Failed to load pacing',
      }));
    }
  }, [id, isDrama]);

  const loadVoiceMap = useCallback(async () => {
    if (!isDrama) {
      setVoiceMapState({ loading: false, characters: [], defaultVoice: '', error: '' });
      return;
    }
    setVoiceMapState((prev) => ({ ...prev, loading: true, error: '' }));
    try {
      const response = await api.getVoiceMap(id);
      setVoiceMapState({
        loading: false,
        characters: Array.isArray(response.characters) ? response.characters : [],
        defaultVoice: response.default_voice || '',
        error: '',
      });
    } catch (err) {
      setVoiceMapState((prev) => ({
        ...prev,
        loading: false,
        error: err.message || 'Failed to load character voice map',
      }));
    }
  }, [id, isDrama]);

  useEffect(() => {
    loadRequirements();
    loadVoiceMap();
    loadPacing();
    const timer = setInterval(() => setRefreshKey((k) => k + 1), 10000);
    return () => clearInterval(timer);
  }, [id, loadRequirements, loadVoiceMap, loadPacing]);

  useEffect(() => {
    if (refreshKey === 0) return;
    loadRequirements();
    loadVoiceMap();
    loadPacing();
  }, [refreshKey, loadRequirements, loadVoiceMap, loadPacing]);

  const handleRefreshClick = () => {
    setIsRefreshing(true);
    setTimeout(() => setIsRefreshing(false), 700);
    setRefreshKey(k => k + 1);
  };

  const totalAssets = Object.values(assets).flat().length;
  const readyAssets = Object.values(assets).flat().filter(a => a.status !== 'missing').length;
  const allReady = readyAssets === totalAssets;

  const handleUploadClick = (type, id) => {
    setActiveUploadId(id);
    setActiveUploadType(type);
    fileInputRef.current?.click();
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file && activeUploadId && activeUploadType) {
      const item = assets[activeUploadType].find((entry) => entry.id === activeUploadId);
      if (item) {
        api
          .uploadAsset(id, item.path, file)
          .then(() => loadRequirements())
          .catch((err) => setLoadError(err.message || 'Upload failed'));
      }
    }
    setActiveUploadId(null);
    setActiveUploadType(null);
    e.target.value = ''; 
  };

  const handleRemoveAsset = async (item) => {
    setActiveRemoveId(item.id);
    setLoadError('');
    try {
      await api.removeAsset(id, item.path);
      await loadRequirements();
    } catch (err) {
      setLoadError(err.message || 'Remove failed');
    } finally {
      setActiveRemoveId(null);
    }
  };

  const generateCharacterAudio = async (speaker) => {
    setActiveTtsSpeaker(speaker);
    setLoadError('');
    try {
      await api.generateDramaTts(id, { character: speaker });
      await loadRequirements();
      await loadVoiceMap();
      await loadPacing();
    } catch (err) {
      setLoadError(err.message || 'Character generation failed');
    } finally {
      setActiveTtsSpeaker('');
    }
  };

  const generateAllCharacters = async () => {
    setGeneratingAllSpeakers(true);
    setLoadError('');
    try {
      await api.generateDramaTts(id);
      await loadRequirements();
      await loadVoiceMap();
      await loadPacing();
    } catch (err) {
      setLoadError(err.message || 'Audio generation failed');
    } finally {
      setGeneratingAllSpeakers(false);
    }
  };


  const updatePacingField = (requirementId, field, value) => {
    setPacingEdits((prev) => ({
      ...prev,
      [requirementId]: {
        ...(prev[requirementId] || {}),
        [field]: value,
      },
    }));
  };

  const savePacing = async () => {
    setSavingPacing(true);
    setLoadError('');
    try {
      await api.savePacing(id, pacingEdits);
      await loadPacing();
    } catch (err) {
      setLoadError(err.message || 'Failed to save pacing');
    } finally {
      setSavingPacing(false);
    }
  };

  const triggerRender = async () => {
    setIsRendering(true);
    setLoadError('');
    try {
      await api.runStage2(id);
      for (let attempt = 0; attempt < 300; attempt += 1) {
        const status = await api.getStatus(id);
        setRenderStep((prev) => Math.min(prev + 1, renderSteps.length - 1));
        if (status.status === 'done') {
          navigate(`/projects/${id}/output`, { state: { ...location.state } });
          return;
        }
        if (status.status === 'failed') {
          throw new Error(status.error || 'Render failed');
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      throw new Error('Render timeout');
    } catch (err) {
      setLoadError(err.message || 'Render failed');
      setIsRendering(false);
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'ready': return <CheckCircle2 className="w-5 h-5 text-violet-400 drop-shadow-sm" />;
      case 'missing': return <Circle className="w-5 h-5 text-rose-500/50" />;
      default: return null;
    }
  };

  const getTypeIcon = (type) => {
    switch(type) {
      case 'voice': return <PlayCircle className="text-rose-400" size={18}/>;
      case 'music': return <Music className="text-violet-400" size={18}/>;
      case 'ambience': return <Wind className="text-violet-400" size={18}/>;
      case 'sfx': return <Volume2 className="text-amber-400" size={18}/>;
      default: return null;
    }
  };

  const renderGroup = (type, title, items) => {
    if (!items || items.length === 0) return null;
    return (
      <div className="mb-12 animate-in fade-in slide-in-from-bottom-4 duration-700 fill-mode-both" style={{ animationDelay: `${Object.keys(assets).indexOf(type) * 100}ms` }} key={type}>
        <h3 className="text-sm font-bold text-zinc-900 tracking-widest uppercase mb-6 flex items-center bg-white p-3 rounded-xl border border-zinc-200 shadow-lg backdrop-blur-md">
          <span className="mr-3">{getTypeIcon(type)}</span>
          {title} 
          <div className="flex-1 mx-4 h-px bg-gradient-to-r from-white/10 to-transparent"></div>
          <span className="text-zinc-600 text-xs font-mono bg-violet-600/40 px-2 py-1 rounded-md">{items.length} CLIPS</span>
        </h3>
        <div className="space-y-3.5">
          {items.map(item => (
            <div key={item.id} className={`
              card py-4 px-5 flex flex-col sm:flex-row sm:items-center gap-4 transition-all duration-300
              ${item.status === 'missing' ? 'border-zinc-200 hover:border-zinc-200 hover:bg-white/40' : 'border-violet-500/20 bg-violet-950/20 shadow-sm'}
            `}>
              <div className="flex-shrink-0" title={item.status === 'missing' ? 'Missing' : 'Ready'}>
                {getStatusIcon(item.status)}
              </div>
              <div className="flex-1 min-w-0 flex flex-col gap-1.5">
                <div className="font-mono text-[11px] text-zinc-600 truncate uppercase tracking-wider">
                  {item.path}
                </div>
                <div className={`text-sm font-medium truncate ${item.status === 'missing' ? 'text-zinc-600' : 'text-violet-50'}`}>
                  {item.desc}
                </div>
              </div>
              <div className="flex-shrink-0 sm:w-32 sm:text-right mt-3 sm:mt-0">
                {item.status === 'missing' ? (
                  <button 
                    onClick={() => handleUploadClick(type, item.id)}
                    className="w-full sm:w-auto text-xs font-bold uppercase tracking-wider bg-white border border-zinc-200 px-4 py-2.5 rounded-lg hover:bg-violet-500 hover:border-violet-500 hover:text-zinc-900 hover:shadow-sm transition-all text-zinc-600 flex items-center justify-center gap-2"
                  >
                    <UploadCloud size={16} /> Upload
                  </button>
                ) : (
                  <div className="flex items-center gap-2 justify-end">
                    <button
                      onClick={() => handleRemoveAsset(item)}
                      disabled={activeRemoveId === item.id}
                      className="text-[11px] font-bold uppercase tracking-wider text-zinc-600 hover:text-zinc-600 border border-transparent hover:border-zinc-200 px-3 py-1.5 rounded-md transition-all disabled:opacity-50"
                    >
                      <Trash2 size={14} className="inline mr-1" />
                      {activeRemoveId === item.id ? 'Removing' : 'Remove'}
                    </button>
                    <button 
                      onClick={() => handleUploadClick(type, item.id)}
                      className="text-[11px] font-bold uppercase tracking-wider text-zinc-600 hover:text-zinc-600 border border-transparent hover:border-zinc-200 px-3 py-1.5 rounded-md transition-all"
                    >
                      Replace
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen flex flex-col pb-32">
      <TopBar projectName={displayProjectName} step={3} totalSteps={4} />
      
      <input 
        type="file" 
        ref={fileInputRef} 
        onChange={handleFileChange} 
        accept="audio/*,.wav,.mp3,.flac" 
        className="hidden" 
      />

      <main className="flex-1 max-w-5xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-10">
        
        {/* Status Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6 mb-12 pb-6 border-b border-zinc-200">
          <div className="flex flex-col gap-2">
            <h1 className="text-3xl font-extrabold text-zinc-900 tracking-tight">{projectName}</h1>
            <div className="flex items-center gap-3">
              <span className="text-xs font-bold bg-violet-500/20 text-violet-800 border border-violet-500/30 px-3 py-1 rounded-full uppercase tracking-widest">
                {format === 'drama' ? 'Audio Drama' : 'Audio Book'}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-4 bg-white p-3 rounded-2xl border border-zinc-200 backdrop-blur-sm">
            <div className={`text-sm font-bold flex items-center gap-2.5 px-3 py-2 rounded-xl ${allReady ? 'bg-violet-500/20 text-violet-400 border border-violet-500/30' : 'bg-amber-500/10 text-amber-500 border border-amber-500/20'}`}>
              {allReady ? (
                <>
                  <CheckCircle2 size={18} /> All assets ready
                </>
              ) : (
                <>
                  <Loader2 size={18} className="animate-spin-slow" /> {readyAssets} / {totalAssets} ready
                </>
              )}
            </div>
            <button 
              onClick={handleRefreshClick}
              disabled={isRefreshing}
              className="p-3 text-zinc-600 hover:text-zinc-900 hover:bg-white rounded-xl transition-all border border-transparent hover:border-zinc-200 disabled:opacity-50"
              title="Refresh status"
            >
              <RefreshCw size={18} className={isRefreshing ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        {loadError && (
          <div className="mb-6 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            {loadError}
          </div>
        )}
        {isDrama && (
          <div className="mb-8 card p-5">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-3">
              <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-900">Character Voice (AI TTS)</h3>
              <button
                onClick={generateAllCharacters}
                disabled={generatingAllSpeakers || (voiceMapState.characters || []).length === 0}
                className="text-xs font-bold uppercase tracking-wider bg-white border border-zinc-200 px-3 py-2 rounded-lg hover:bg-violet-500 hover:border-violet-500 hover:text-zinc-900 transition-all disabled:opacity-50"
              >
                {generatingAllSpeakers ? 'Generating...' : 'Generate All'}
              </button>
            </div>
            {voiceMapState.defaultVoice && (
              <p className="text-xs text-zinc-600 mb-3">Fallback voice: {voiceMapState.defaultVoice}</p>
            )}
            {voiceMapState.loading ? (
              <p className="text-xs text-zinc-600">Loading characters...</p>
            ) : (voiceMapState.characters || []).length === 0 ? (
              <p className="text-xs text-zinc-600">Run Stage 1 first to discover character-wise voice clips.</p>
            ) : (
              <div className="grid gap-2">
                {voiceMapState.characters.map((entry) => (
                  <div key={entry.speaker} className="border border-zinc-200 rounded-lg p-3 flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-zinc-900">{entry.speaker}</div>
                      <div className="text-xs text-zinc-600">{entry.clip_count} clips • {entry.voice}</div>
                    </div>
                    <button
                      onClick={() => generateCharacterAudio(entry.speaker)}
                      disabled={activeTtsSpeaker === entry.speaker}
                      className="text-xs font-bold uppercase tracking-wider bg-white border border-zinc-200 px-3 py-2 rounded-lg hover:bg-violet-500 hover:border-violet-500 hover:text-zinc-900 transition-all disabled:opacity-50"
                    >
                      {activeTtsSpeaker === entry.speaker ? 'Generating...' : 'Generate'}
                    </button>
                  </div>
                ))}
              </div>
            )}
            {voiceMapState.error && <p className="mt-3 text-xs text-red-500">{voiceMapState.error}</p>}
            <p className="mt-3 text-xs text-zinc-600">After AI generation, you can remove any clip and upload your own file.</p>
          </div>
        )}

        {isDrama && (
          <div className="mb-8 card p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-900">Pacing Review</h3>
              <button
                onClick={savePacing}
                disabled={savingPacing || pacingState.loading}
                className="text-xs font-bold uppercase tracking-wider bg-white border border-zinc-200 px-3 py-2 rounded-lg hover:bg-violet-500 hover:border-violet-500 hover:text-zinc-900 transition-all disabled:opacity-50"
              >
                {savingPacing ? 'Saving...' : 'Save'}
              </button>
            </div>
            {pacingState.loading ? (
              <p className="text-xs text-zinc-600">Loading pacing...</p>
            ) : (pacingState.scenes || []).length === 0 ? (
              <p className="text-xs text-zinc-600">Run Stage 1 first to generate pacing clips.</p>
            ) : (
              <div className="space-y-3 max-h-80 overflow-y-auto">
                {(pacingState.scenes || []).map((scene) => (
                  <div key={scene.scene_id} className="border border-zinc-200 rounded-lg p-3">
                    <div className="text-xs font-semibold text-zinc-900 mb-2">
                      {scene.scene_name} - {scene.estimated_duration_s}s / floor {scene.floor_s}s
                    </div>
                    <div className="space-y-2">
                      {(scene.clips || []).map((clip) => {
                        const override = pacingEdits[clip.requirement_id] || {};
                        const preValue = override.pre_silence_s ?? clip.pre_silence_s ?? 0;
                        const postValue = override.post_silence_s ?? clip.post_silence_s ?? 0;
                        return (
                          <div key={clip.requirement_id} className="border border-zinc-200 rounded p-2">
                            <div className="text-[10px] text-zinc-600 mb-1">{clip.dramatic_function || 'dialogue'} - {clip.speaker}</div>
                            <div className="text-xs text-zinc-900 mb-1 truncate">{clip.line_text}</div>
                            <label className="text-[10px] text-zinc-600">Pre ({Math.round(preValue * 1000)}ms)</label>
                            <input type="range" min="0" max="5" step="0.1" value={preValue} onChange={(e) => updatePacingField(clip.requirement_id, 'pre_silence_s', Number(e.target.value))} className="w-full" />
                            <label className="text-[10px] text-zinc-600">Post ({Math.round(postValue * 1000)}ms)</label>
                            <input type="range" min="0" max="5" step="0.1" value={postValue} onChange={(e) => updatePacingField(clip.requirement_id, 'post_silence_s', Number(e.target.value))} className="w-full" />
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
            {pacingState.error && <p className="mt-3 text-xs text-red-500">{pacingState.error}</p>}
          </div>
        )}
        {loadingAssets ? (
          <div className="card text-center py-16">
            <Loader2 className="animate-spin inline-block text-violet-500 mb-3" />
            <p className="text-textSecondary">Loading requirements...</p>
          </div>
        ) : (
          <div>
            {renderGroup('voice', 'Voice', assets.voice)}
            {renderGroup('music', 'Music', assets.music)}
            {renderGroup('ambience', 'Ambience', assets.ambience)}
            {renderGroup('sfx', 'SFX', assets.sfx)}
          </div>
        )}

      </main>

      {/* Sticky Bottom Bar */}
      <div className="fixed bottom-0 left-0 right-0 bg-zinc-950/80 border-t border-zinc-200 backdrop-blur-2xl shadow-[0_-10px_40px_rgba(0,0,0,0.5)] z-50">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 h-24 flex items-center justify-between">
          <div className="flex flex-col">
            <div className="text-xs font-bold text-zinc-600 uppercase tracking-widest mb-1">Pipeline Status</div>
            <div className={`text-lg font-medium ${allReady ? 'text-zinc-900' : 'text-zinc-600'}`}>
              <span className={`font-extrabold ${allReady ? 'text-violet-400' : 'text-zinc-900'}`}>{readyAssets}</span> of {totalAssets} assets placed
            </div>
          </div>
          
          <div className="w-full sm:w-96">
            <button
              onClick={triggerRender}
              disabled={!allReady || isRendering}
              className={`btn-primary w-full relative overflow-hidden transition-all duration-500 ${
                isRendering ? 'bg-violet-600 shadow-sm scale-100' : ''
              } ${!allReady ? 'opacity-50 scale-100' : 'hover:scale-[1.02]'}`}
            >
              {isRendering ? (
                <div className="flex flex-col items-center justify-center py-1">
                  <div className="flex items-center text-zinc-900 font-bold tracking-wide">
                    <Loader2 className="animate-spin mr-3" size={18} /> RENDERING AUDIO
                  </div>
                  <div className="text-[11px] text-violet-900 mt-1 font-mono tracking-widest uppercase">
                    {renderSteps[renderStep]}
                  </div>
                  {/* Glowing Progress Bar */}
                  <div className="absolute bottom-0 left-0 h-1.5 w-full bg-violet-600/40 overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-violet-400 to-fuchsia-400 w-1/3 animate-[slide_1.5s_ease-in-out_infinite] blur-[1px]"></div>
                  </div>
                </div>
              ) : (
                <span className="text-base tracking-wide font-bold">Render Final Audio <ArrowRight size={20} className="inline ml-2 -mt-0.5" /></span>
              )}
            </button>
          </div>
        </div>
      </div>
      
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes slide {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(300%); }
        }
        .animate-spin-slow {
          animation: spin 3s linear infinite;
        }
      `}} />
    </div>
  );
}
