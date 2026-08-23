import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { AudioLines, ArrowLeft, ArrowRight, Plus, Clock, Play, Download, Settings, BarChart2, CheckCircle2, ChevronRight, Edit3, Loader2, Headphones } from 'lucide-react';
import { supabase } from '../supabase';
import { api } from '../api';

function parseRuntimeToSeconds(value) {
  if (value == null) return null;
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Math.max(0, Math.round(value));
  }
  if (typeof value !== 'string') return null;
  const text = value.trim().toLowerCase();
  if (!text) return null;

  const colonParts = text.split(':').map((part) => Number.parseInt(part, 10));
  if (colonParts.length === 2 && colonParts.every((part) => Number.isFinite(part))) {
    return (colonParts[0] * 60) + colonParts[1];
  }
  if (colonParts.length === 3 && colonParts.every((part) => Number.isFinite(part))) {
    return (colonParts[0] * 3600) + (colonParts[1] * 60) + colonParts[2];
  }

  let total = 0;
  let matched = false;
  const unitRegex = /(\d+)\s*(h|hr|hrs|hour|hours|m|min|mins|minute|minutes|s|sec|secs|second|seconds)\b/g;
  for (const match of text.matchAll(unitRegex)) {
    const amount = Number.parseInt(match[1], 10);
    if (!Number.isFinite(amount)) continue;
    matched = true;
    const unit = match[2];
    if (unit.startsWith('h')) total += amount * 3600;
    else if (unit.startsWith('m')) total += amount * 60;
    else total += amount;
  }

  return matched ? total : null;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '--';
  const safeSeconds = Math.max(0, Math.round(seconds));
  const hrs = Math.floor(safeSeconds / 3600);
  const mins = Math.floor((safeSeconds % 3600) / 60);
  const secs = safeSeconds % 60;
  if (hrs > 0) return `${hrs}h ${mins}m`;
  return `${mins}m ${secs}s`;
}

function getUnitRuntimeSeconds(unit) {
  const directSeconds = [
    unit.runtime_seconds,
    unit.total_runtime_seconds,
    unit.duration_seconds,
    unit.duration,
  ].find((value) => typeof value === 'number' && Number.isFinite(value));

  if (directSeconds != null) {
    return Math.max(0, Math.round(directSeconds));
  }

  return parseRuntimeToSeconds(unit.runtime);
}

export default function ProjectDetails() {
  const { projectId } = useParams();
  const navigate = useNavigate();

  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newUnitName, setNewUnitName] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [backendStatus, setBackendStatus] = useState(null);
  const [activeDownloadId, setActiveDownloadId] = useState(null);
  const [actionError, setActionError] = useState('');
  const [characterCount, setCharacterCount] = useState(0);
  const [unitDurations, setUnitDurations] = useState({});
  const [creditsState, setCreditsState] = useState({
    loading: false,
    running: false,
    items: [],
    error: '',
  });
  const [creditsPreview, setCreditsPreview] = useState({
    slot: null,
    loading: false,
    url: '',
    error: '',
  });
  const [activeCreditsDownloadSlot, setActiveCreditsDownloadSlot] = useState(null);
  const [previewState, setPreviewState] = useState({
    unitId: null,
    loading: false,
    url: '',
    error: '',
  });

  useEffect(() => {
    async function fetchProjectData() {
      try {
        const { data: projectData, error: projectError } = await supabase
          .from('projects')
          .select('*')
          .eq('id', projectId)
          .single();

        if (projectError) throw projectError;

        const { data: unitsData, error: unitsError } = await supabase
          .from('units')
          .select('*')
          .eq('project_id', projectId)
          .order('created_at', { ascending: true });

        if (unitsError) throw unitsError;

        setProject({
          ...projectData,
          units: unitsData || [],
          totalRuntime: projectData.total_runtime || ''
        });
      } catch (err) {
        console.error("Failed to load project:", err);
      } finally {
        setLoading(false);
      }
    }
    
    fetchProjectData();
  }, [projectId]);

  useEffect(() => {
    let alive = true;
    const loadCharacterCount = async () => {
      try {
        const requirements = await api.getRequirements(projectId);
        if (!alive) return;
        const voiceDescriptors = new Set(
          (requirements.items || [])
            .filter((item) => item.asset_kind === 'voice')
            .map((item) => String(item.descriptor || '').trim())
            .filter(Boolean)
        );
        setCharacterCount(voiceDescriptors.size);
      } catch {
        if (!alive) return;
        setCharacterCount(0);
      }
    };

    loadCharacterCount();
    return () => {
      alive = false;
    };
  }, [projectId]);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const res = await api.getStatus(projectId);
        if (alive) setBackendStatus(res.status);
      } catch {
        // Project may not be registered in backend yet.
      }
    };
    poll();
    const timer = setInterval(poll, 3000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [projectId]);

  useEffect(() => {
    return () => {
      if (previewState.url) {
        URL.revokeObjectURL(previewState.url);
      }
      if (creditsPreview.url) {
        URL.revokeObjectURL(creditsPreview.url);
      }
    };
  }, [previewState.url, creditsPreview.url]);

  useEffect(() => {
    const units = project?.units || [];
    if (!project || units.length === 0) {
      setUnitDurations({});
      return;
    }
    let alive = true;
    const loadUnitDurations = async () => {
      try {
        const entries = await Promise.all(
          units.map(async (unit) => {
            try {
              const output = await api.getOutput(projectId, unit.id, unit.name);
              return [unit.id, Number.isFinite(output?.duration_seconds) ? Math.round(output.duration_seconds) : null];
            } catch {
              return [unit.id, null];
            }
          })
        );
        if (!alive) return;
        setUnitDurations(Object.fromEntries(entries));
      } catch {
        if (!alive) return;
        setUnitDurations({});
      }
    };
    loadUnitDurations();
    return () => {
      alive = false;
    };
  }, [project, projectId]);

  useEffect(() => {
    if (!project || project.format !== 'book') return;
    let alive = true;
    const fetchCredits = async () => {
      try {
        if (alive) {
          setCreditsState((prev) => ({ ...prev, loading: true, error: '' }));
        }
        const res = await api.getCredits(projectId);
        if (!alive) return;
        setCreditsState((prev) => ({
          ...prev,
          loading: false,
          items: res.items || [],
          error: '',
        }));
      } catch (err) {
        if (!alive) return;
        setCreditsState((prev) => ({
          ...prev,
          loading: false,
          error: err.message || 'Failed to load credits status.',
        }));
      }
    };
    fetchCredits();
    return () => {
      alive = false;
    };
  }, [project, projectId]);

  const handleStartNewUnit = async (e) => {
    e.preventDefault();
    if (!newUnitName.trim()) return;

    setIsSubmitting(true);
    try {
      const { data, error } = await supabase
        .from('units')
        .insert({
          project_id: projectId,
          name: newUnitName
        })
        .select()
        .single();

      if (error) throw error;
      
      setIsModalOpen(false);
      navigate(`/projects/${projectId}/story`, {
        state: {
          projectName: project.name,
          format: project.format,
          unitName: data.name,
          unitId: data.id,
          writerName: project.writer_name,
          narrationChoice: project.narration_choice,
          aiVoiceProvider: project.ai_voice_provider
        }
      });
    } catch (err) {
      console.error(err);
      alert('Failed to create new unit');
    } finally {
      setIsSubmitting(false);
    }
  };

  const getUnitWorkflowState = (unit) => {
    const unitStatus = unit.status || 'draft';
    const normalizedUnitStatus = String(unitStatus).toLowerCase();
    const isMastered = normalizedUnitStatus === 'mastered' || normalizedUnitStatus === 'done' || backendStatus === 'done';
    return {
      unitStatus,
      isMastered,
    };
  };

  const getDisplayedUnitRuntimeSeconds = (unit) => {
    const measured = unitDurations[unit.id];
    if (typeof measured === 'number' && Number.isFinite(measured) && measured >= 0) {
      return measured;
    }
    return getUnitRuntimeSeconds(unit);
  };

  const unitRuntimeSeconds = (project?.units || [])
    .map((unit) => getDisplayedUnitRuntimeSeconds(unit))
    .filter((seconds) => seconds != null);
  const totalRuntimeFromUnits = unitRuntimeSeconds.reduce((sum, seconds) => sum + seconds, 0);
  const fallbackProjectRuntimeSeconds = parseRuntimeToSeconds(project?.totalRuntime);
  const totalAudioLabel = totalRuntimeFromUnits > 0
    ? formatDuration(totalRuntimeFromUnits)
    : (fallbackProjectRuntimeSeconds != null ? formatDuration(fallbackProjectRuntimeSeconds) : '--');

  const openUnitOutput = (unit) => {
    navigate(`/projects/${projectId}/output`, {
      state: {
        unitId: unit.id,
        projectName: project.name,
        unitName: unit.name,
        format: project.format,
        narrationChoice: project.narration_choice,
        aiVoiceProvider: project.ai_voice_provider,
      },
    });
  };

  const continueUnitWorkflow = (unit) => {
    const target = project.format === 'drama' ? `/projects/${projectId}/drama-dashboard` : `/projects/${projectId}/story`;
    navigate(target, {
      state: {
        unitId: unit.id,
        projectName: project.name,
        unitName: unit.name,
        format: project.format,
        narrationChoice: project.narration_choice,
        aiVoiceProvider: project.ai_voice_provider,
        storyText: unit.story_text || '',
      },
    });
  };

  const handleTogglePreview = async (unit) => {
    setActionError('');

    if (previewState.unitId === unit.id) {
      if (previewState.url) {
        URL.revokeObjectURL(previewState.url);
      }
      setPreviewState({
        unitId: null,
        loading: false,
        url: '',
        error: '',
      });
      return;
    }

    if (previewState.url) {
      URL.revokeObjectURL(previewState.url);
    }

    setPreviewState({
      unitId: unit.id,
      loading: true,
      url: '',
      error: '',
    });

    try {
      const { blobUrl } = await api.getOutputAudioBlobUrl(projectId, unit.id, unit.name);
      if (!blobUrl) {
        throw new Error('Audio preview is not available yet.');
      }
      setPreviewState({
        unitId: unit.id,
        loading: false,
        url: blobUrl,
        error: '',
      });
    } catch (err) {
      setPreviewState({
        unitId: unit.id,
        loading: false,
        url: '',
        error: err.message || 'Failed to load audio preview.',
      });
    }
  };

  const handleDownload = async (unit) => {
    setActionError('');
    setActiveDownloadId(unit.id);
    let revokedUrl = null;
    try {
      const { blobUrl } = await api.getOutputAudioBlobUrl(projectId, unit.id, unit.name);
      if (!blobUrl) {
        throw new Error('Output audio is not available yet.');
      }
      revokedUrl = blobUrl;

      const safeProjectName = project.name.replace(/[^\w-]+/g, '_');
      const safeUnitName = unit.name.replace(/[^\w-]+/g, '_');
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = `${safeProjectName}-${safeUnitName || 'output'}.wav`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (err) {
      setActionError(err.message || 'Failed to download output audio.');
    } finally {
      if (revokedUrl) {
        URL.revokeObjectURL(revokedUrl);
      }
      setActiveDownloadId(null);
    }
  };

  const refreshCredits = async () => {
    const res = await api.getCredits(projectId);
    setCreditsState((prev) => ({
      ...prev,
      items: res.items || [],
      error: '',
    }));
  };

  const handleGenerateCredits = async () => {
    if (project?.format !== 'book') return;
    setActionError('');
    setCreditsState((prev) => ({ ...prev, running: true, error: '' }));
    try {
      await api.runCredits(projectId);
      for (let attempt = 0; attempt < 180; attempt += 1) {
        const statusRes = await api.getStatus(projectId);
        setBackendStatus(statusRes.status);
        if (statusRes.status === 'failed') {
          throw new Error(statusRes.error || 'Credits generation failed.');
        }
        if (statusRes.status !== 'queued' && statusRes.status !== 'credits') {
          await refreshCredits();
          setCreditsState((prev) => ({ ...prev, running: false }));
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      throw new Error('Credits generation timed out. Please try again.');
    } catch (err) {
      setCreditsState((prev) => ({
        ...prev,
        running: false,
        error: err.message || 'Failed to generate credits.',
      }));
    }
  };

  const handlePreviewCredits = async (slot) => {
    if (creditsPreview.slot === slot) {
      if (creditsPreview.url) {
        URL.revokeObjectURL(creditsPreview.url);
      }
      setCreditsPreview({
        slot: null,
        loading: false,
        url: '',
        error: '',
      });
      return;
    }

    if (creditsPreview.url) {
      URL.revokeObjectURL(creditsPreview.url);
    }
    setCreditsPreview({
      slot,
      loading: true,
      url: '',
      error: '',
    });
    try {
      const blobUrl = await api.getCreditsAudioBlobUrl(projectId, slot);
      if (!blobUrl) {
        throw new Error('Credits audio is not available yet.');
      }
      setCreditsPreview({
        slot,
        loading: false,
        url: blobUrl,
        error: '',
      });
    } catch (err) {
      setCreditsPreview({
        slot,
        loading: false,
        url: '',
        error: err.message || 'Failed to load credits preview.',
      });
    }
  };

  const handleDownloadCredits = async (slot) => {
    setActiveCreditsDownloadSlot(slot);
    setCreditsState((prev) => ({ ...prev, error: '' }));
    let blobUrl = null;
    try {
      blobUrl = await api.getCreditsAudioBlobUrl(projectId, slot);
      if (!blobUrl) {
        throw new Error('Credits audio is not available yet.');
      }
      const link = document.createElement('a');
      const safeProjectName = project.name.replace(/[^\w-]+/g, '_');
      const suffix = slot === 'opening' ? 'opening_credits' : 'ending_credits';
      link.href = blobUrl;
      link.download = `${safeProjectName}-${suffix}.wav`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (err) {
      setCreditsState((prev) => ({
        ...prev,
        error: err.message || 'Failed to download credits audio.',
      }));
    } finally {
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
      setActiveCreditsDownloadSlot(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="animate-spin text-violet-500" size={40} />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4">
        <h2 className="text-2xl text-zinc-900 font-bold">Project not found</h2>
        <Link to="/profile" className="text-violet-400 hover:text-violet-800">Return to Profile</Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background relative overflow-hidden">
      {/* Top Bar Navigation Component */}
      <div className="w-full bg-surface/80 backdrop-blur-xl border-b border-border sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <Link to="/profile" className="flex items-center gap-2 text-textSecondary hover:text-zinc-900 transition-colors cursor-pointer group">
            <ArrowLeft size={18} className="group-hover:-translate-x-1 transition-transform" />
            <span className="font-semibold">Back to Profile</span>
          </Link>
          <div className="flex items-center gap-2 font-bold text-lg">
            <div className="w-8 h-8 rounded-lg bg-violet-600 flex items-center justify-center shadow-lg">
              <AudioLines size={18} className="text-zinc-900" />
            </div>
            <span className="text-textPrimary tracking-tight">
              Aud<span className="text-violet-900 font-bold">Stories</span>
            </span>
          </div>
        </div>
      </div>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">

        {/* Project Hero Header */}
        <div className="relative overflow-hidden rounded-3xl border border-zinc-200 p-8 sm:p-12 animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="absolute inset-0 bg-violet-50" />
          <div className="absolute -top-32 -right-32 w-96 h-96 bg-violet-600/30 rounded-full blur-[100px] pointer-events-none" />

          <div className="relative z-10 flex flex-col md:flex-row md:items-end justify-between gap-6">
            <div>
              <div className="flex items-center gap-3 mb-4">
                <span className="text-xs font-bold bg-violet-500/20 text-violet-800 border border-violet-500/30 px-3 py-1 rounded-full uppercase tracking-widest">
                  {project.format === 'drama' ? 'Audio Drama' : 'Audio Book'}
                </span>
                {project.narration_choice === 'ai' && (
                  <span className="text-xs font-bold bg-violet-500/10 text-violet-400 border border-violet-500/20 px-3 py-1 rounded-full uppercase tracking-widest flex items-center gap-1.5">
                    <CheckCircle2 size={14} /> {project.ai_voice_provider === 'elevenlabs' ? 'ElevenLabs AI' : 'Google AI'}
                  </span>
                )}
              </div>
              <h1 className="text-4xl sm:text-5xl font-extrabold text-zinc-900 mb-2 tracking-tight">{project.name}</h1>
              <p className="text-textSecondary text-lg font-medium flex items-center gap-2">
                Written by <span className="text-zinc-900">{project.writer_name || 'Anonymous'}</span>
              </p>
            </div>

            <div className="flex gap-3">
              <button className="btn-primary py-3 px-6 text-sm flex items-center shadow-sm opacity-60 cursor-not-allowed" disabled title="Project settings coming soon">
                <Settings size={18} className="mr-2" /> Settings
              </button>
            </div>
          </div>
        </div>

        <div className="flex flex-col lg:flex-row gap-10">
          {/* Main Content Area: Units List */}
          <div className="flex-1 space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500 delay-150 fill-mode-both">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-zinc-200 pb-4">
              <h2 className="text-xl font-bold text-zinc-900 tracking-wide">
                {project.format === 'drama' ? 'Episodes' : 'Chapters'}
              </h2>

              <button
                onClick={() => setIsModalOpen(true)}
                className="bg-white hover:bg-zinc-200 text-zinc-900 font-semibold py-2.5 px-5 rounded-xl transition-all border border-zinc-200 hover:border-violet-500/50 flex items-center gap-2 text-sm"
              >
                <Plus size={18} /> Add New {project.format === 'drama' ? 'Episode' : 'Chapter'}
              </button>
            </div>

            <div className="space-y-4">
              {actionError && (
                <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                  {actionError}
                </div>
              )}
              {project.units && project.units.length > 0 ? project.units.map((unit) => {
                const workflowState = getUnitWorkflowState(unit);
                return (
                <div key={unit.id} className="space-y-3">
                  <div className="card p-5 flex flex-col sm:flex-row sm:items-center gap-4 hover:border-violet-500/40 transition-colors group">
                    <div className={`w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 shadow-lg ${workflowState.isMastered ? 'bg-violet-600 text-zinc-900' : 'bg-white text-zinc-600'}`}>
                      <Play size={20} className="ml-1" />
                    </div>

                    <div className="flex-1 min-w-0">
                      <h3 className="text-lg font-bold text-zinc-900 mb-1 truncate group-hover:text-violet-900 transition-colors">{unit.name}</h3>
                      <div className="flex items-center gap-4 text-xs font-medium text-textSecondary uppercase tracking-wider">
                        <span className="flex items-center gap-1.5"><Clock size={12} /> {formatDuration(getDisplayedUnitRuntimeSeconds(unit))}</span>
                        <span className={`px-2 py-0.5 rounded-md ${workflowState.isMastered ? 'bg-violet-500/10 text-violet-400 border border-violet-500/20' : 'bg-amber-500/10 text-amber-500 border border-amber-500/20'}`}>
                          {workflowState.unitStatus}
                        </span>
                      </div>
                    </div>

                    <div className="flex gap-2">
                      {workflowState.isMastered ? (
                        <>
                          <button
                            onClick={() => handleTogglePreview(unit)}
                            className="p-2 sm:px-4 sm:py-2.5 bg-white hover:bg-violet-500/20 text-zinc-600 hover:text-violet-800 rounded-lg border border-transparent hover:border-violet-500/30 transition-colors flex items-center gap-2 text-sm font-semibold"
                          >
                            {previewState.loading && previewState.unitId === unit.id ? (
                              <Loader2 size={16} className="animate-spin" />
                            ) : (
                              <Headphones size={18} />
                            )}
                            <span className="hidden sm:inline">
                              {previewState.unitId === unit.id ? 'Hide Player' : 'Listen'}
                            </span>
                          </button>
                          <button
                            onClick={() => handleDownload(unit)}
                            disabled={activeDownloadId === unit.id}
                            className="p-2 sm:px-4 sm:py-2.5 bg-white hover:bg-violet-500/20 text-zinc-600 hover:text-violet-800 rounded-lg border border-transparent hover:border-violet-500/30 transition-colors flex items-center gap-2 text-sm font-semibold disabled:opacity-60 disabled:cursor-not-allowed"
                          >
                            {activeDownloadId === unit.id ? <Loader2 size={16} className="animate-spin" /> : <Download size={18} />}
                            <span className="hidden sm:inline">{activeDownloadId === unit.id ? 'Preparing...' : 'Download'}</span>
                          </button>
                        </>
                      ) : (
                        <button 
                           onClick={() => continueUnitWorkflow(unit)}
                           className="p-2 sm:px-4 sm:py-2.5 bg-white hover:bg-white text-zinc-600 rounded-lg transition-colors flex items-center gap-2 text-sm font-semibold"
                        >
                          <Edit3 size={18} /> <span className="hidden sm:inline">Continue Workflow</span>
                        </button>
                      )}
                      <button
                        onClick={() => {
                          if (workflowState.isMastered && project.format !== 'drama') {
                            openUnitOutput(unit);
                          } else {
                            continueUnitWorkflow(unit);
                          }
                        }}
                        className="p-2.5 bg-white border border-zinc-200 hover:bg-white text-zinc-600 rounded-lg transition-colors"
                        aria-label={(workflowState.isMastered && project.format !== 'drama') ? `Open output for ${unit.name}` : `Continue workflow for ${unit.name}`}
                      >
                        <ChevronRight size={18} />
                      </button>
                    </div>
                  </div>

                  {workflowState.isMastered && previewState.unitId === unit.id && (
                    <div className="rounded-lg border border-violet-500/20 bg-violet-50/70 p-3">
                      <div className="text-[11px] font-semibold uppercase tracking-wider text-violet-800 mb-2">
                        Quick Preview
                      </div>
                      {previewState.loading ? (
                        <div className="flex items-center gap-2 text-sm text-violet-800">
                          <Loader2 size={14} className="animate-spin" />
                          Loading audio preview...
                        </div>
                      ) : previewState.error ? (
                        <div className="text-sm text-red-500">{previewState.error}</div>
                      ) : (
                        <audio controls preload="metadata" src={previewState.url} className="w-full" />
                      )}
                    </div>
                  )}
                </div>
                );
              }) : (
                <div className="card text-center py-10 bg-white border border-zinc-200">
                   <p className="text-textSecondary">No units created yet.</p>
                </div>
              )}
            </div>
          </div>

          {/* Sidebar / Statistics */}
          <div className="w-full lg:w-80 space-y-6 animate-in fade-in slide-in-from-right-8 duration-500 delay-300 fill-mode-both">
            <div className="card bg-white/60 p-6 border-zinc-200 relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-violet-500/10 rounded-full blur-3xl -mr-16 -mt-16 pointer-events-none" />
              <h3 className="font-bold text-zinc-900 mb-6 uppercase tracking-wider text-sm flex items-center gap-2">
                <BarChart2 size={16} className="text-violet-400" /> Project Status
              </h3>

              <div className="space-y-4 relative z-10">
                <div className="flex justify-between items-center py-2 border-b border-zinc-200">
                  <span className="text-textSecondary text-sm">Total Audio</span>
                  <span className="font-mono text-violet-400 font-bold">{totalAudioLabel}</span>
                </div>
                <div className="flex justify-between items-center py-2 border-b border-zinc-200">
                  <span className="text-textSecondary text-sm">Total Units</span>
                  <span className="font-mono text-zinc-900 font-bold">{project.units?.length || 0}</span>
                </div>
                <div className="flex justify-between items-center py-2">
                  <span className="text-textSecondary text-sm">Characters Mapped</span>
                  <span className="font-mono text-zinc-900 font-bold">{characterCount}</span>
                </div>
                <div className="flex justify-between items-center py-2 border-t border-zinc-200">
                  <span className="text-textSecondary text-sm">Pipeline</span>
                  <span className="font-mono text-zinc-900 font-bold uppercase">{backendStatus || 'idle'}</span>
                </div>
              </div>
            </div>

            {project.format === 'book' && (
              <div className="card bg-white/60 p-6 border-zinc-200 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-zinc-900 uppercase tracking-wider text-sm">Credits Audio</h3>
                  <button
                    onClick={handleGenerateCredits}
                    disabled={creditsState.running || creditsState.loading}
                    className="text-xs font-semibold uppercase tracking-wider px-3 py-1.5 rounded-md bg-violet-500/10 border border-violet-500/20 text-violet-800 hover:bg-violet-500/20 disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {creditsState.running ? 'Generating...' : 'Generate'}
                  </button>
                </div>

                {creditsState.error && (
                  <div className="text-xs text-red-500">{creditsState.error}</div>
                )}

                {(creditsState.items || []).map((item) => (
                  <div key={item.slot} className="rounded-lg border border-zinc-200 bg-white p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-zinc-900 capitalize">{item.slot} credits</span>
                      <span className={`text-[10px] uppercase tracking-wider px-2 py-1 rounded border ${item.available ? 'text-violet-800 bg-violet-500/10 border-violet-500/20' : 'text-amber-700 bg-amber-500/10 border-amber-500/20'}`}>
                        {item.available ? 'Ready' : 'Missing'}
                      </span>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handlePreviewCredits(item.slot)}
                        disabled={!item.available}
                        className="flex-1 text-xs font-semibold py-2 rounded-md border border-zinc-200 text-zinc-700 hover:bg-violet-500/10 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {creditsPreview.loading && creditsPreview.slot === item.slot ? 'Loading...' : creditsPreview.slot === item.slot ? 'Hide Preview' : 'Preview'}
                      </button>
                      <button
                        onClick={() => handleDownloadCredits(item.slot)}
                        disabled={!item.available || activeCreditsDownloadSlot === item.slot}
                        className="flex-1 text-xs font-semibold py-2 rounded-md border border-zinc-200 text-zinc-700 hover:bg-violet-500/10 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {activeCreditsDownloadSlot === item.slot ? 'Preparing...' : 'Download'}
                      </button>
                    </div>
                    {creditsPreview.slot === item.slot && (
                      <div className="pt-1">
                        {creditsPreview.loading ? (
                          <p className="text-xs text-zinc-600">Loading preview...</p>
                        ) : creditsPreview.error ? (
                          <p className="text-xs text-red-500">{creditsPreview.error}</p>
                        ) : (
                          <audio controls preload="metadata" src={creditsPreview.url} className="w-full" />
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div className="card bg-violet-50 border-violet-500/20">
              <h3 className="font-bold text-zinc-900 mb-3 text-sm flex items-center gap-2">💡 Quick Tip</h3>
              <p className="text-sm text-violet-900/70 font-medium leading-relaxed">
                Render multiple episodes to unlock bulk mastering capabilities for consistent LUFS across the entire series.
              </p>
            </div>
          </div>
        </div>
      </main>

      {/* Mini-Modal for creating a New Unit */}
      {isModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-violet-600/80 backdrop-blur-sm" onClick={() => setIsModalOpen(false)} />

          <div className="card relative z-10 w-full max-w-md animate-in fade-in zoom-in-95 duration-200">
            <h2 className="text-2xl font-bold text-zinc-900 mb-2 tracking-wide">
              New {project.format === 'drama' ? 'Episode' : 'Chapter'}
            </h2>
            <p className="text-sm text-textSecondary mb-6">Give it a title to start the creation wizard.</p>

            <form onSubmit={handleStartNewUnit}>
              <div>
                <label className="block text-xs font-semibold text-textSecondary uppercase tracking-wider mb-2">
                  Name
                </label>
                <input
                  type="text"
                  placeholder={project.format === 'drama' ? 'e.g. Episode 4 — The Trap' : 'e.g. Chapter 4'}
                  className="input-field mb-6"
                  value={newUnitName}
                  onChange={(e) => setNewUnitName(e.target.value)}
                  autoFocus
                  required
                />
              </div>
              <div className="flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-5 py-2.5 rounded-xl font-medium text-zinc-600 hover:text-zinc-900 hover:bg-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!newUnitName.trim() || isSubmitting}
                  className="btn-primary py-2.5 px-6 shadow-lg shadow-violet-500/25 flex items-center"
                >
                  {isSubmitting ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <>Start Workflow <ArrowRight size={16} className="ml-2" /></>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}
