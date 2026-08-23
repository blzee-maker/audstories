import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import WaveSurfer from 'wavesurfer.js';
import { ArrowRight, FileText, Loader2, Pause, Play, Sparkles } from 'lucide-react';
import TopBar from '../components/TopBar';
import { api } from '../api';

function RequirementWaveTrack({ projectId, requirement }) {
  const waveRef = useRef(null);
  const waveSurferRef = useRef(null);
  const blobUrlRef = useRef(null);
  const [loading, setLoading] = useState(requirement.status === 'ready');
  const [isPlaying, setIsPlaying] = useState(false);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    let alive = true;
    let instance = null;

    async function loadTrack() {
      if (requirement.status !== 'ready') {
        setLoading(false);
        return;
      }
      try {
        setLoading(true);
        const blobUrl = await api.getRequirementAudioBlobUrl(projectId, requirement.requirement_id);
        if (!alive) {
          URL.revokeObjectURL(blobUrl);
          return;
        }
        blobUrlRef.current = blobUrl;
        instance = WaveSurfer.create({
          container: waveRef.current,
          waveColor: 'rgba(124, 58, 237, 0.25)',
          progressColor: '#8b5cf6',
          cursorColor: '#c4b5fd',
          barWidth: 2,
          barGap: 2,
          barRadius: 2,
          height: 48,
          normalize: true,
          interact: true,
        });
        waveSurferRef.current = instance;
        instance.on('play', () => setIsPlaying(true));
        instance.on('pause', () => setIsPlaying(false));
        instance.on('finish', () => setIsPlaying(false));
        instance.load(blobUrl);
      } catch (error) {
        if (alive) {
          setLoadError(error.message || 'Failed to load track');
        }
      } finally {
        if (alive) {
          setLoading(false);
        }
      }
    }

    loadTrack();

    return () => {
      alive = false;
      if (instance) {
        instance.destroy();
      } else if (waveSurferRef.current) {
        waveSurferRef.current.destroy();
      }
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
    };
  }, [projectId, requirement.requirement_id, requirement.status]);

  if (requirement.status !== 'ready') {
    return (
      <div className="w-full h-12 rounded-lg border border-dashed border-zinc-200 bg-white/40 flex items-center px-3 text-xs text-zinc-500 uppercase tracking-wider">
        Audio not uploaded yet
      </div>
    );
  }

  return (
    <div className="w-full">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => waveSurferRef.current?.playPause()}
          disabled={loading || !!loadError}
          className="w-9 h-9 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-700 hover:bg-violet-500/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
          title={isPlaying ? 'Pause track' : 'Play track'}
        >
          {isPlaying ? <Pause size={16} /> : <Play size={16} className="ml-0.5" />}
        </button>
        <div className="flex-1 min-w-0">
          {loading ? (
            <div className="w-full h-12 rounded-lg border border-zinc-200 bg-white/40 flex items-center px-3 text-xs text-zinc-500 uppercase tracking-wider">
              Loading waveform...
            </div>
          ) : loadError ? (
            <div className="w-full h-12 rounded-lg border border-red-200 bg-red-50 flex items-center px-3 text-xs text-red-500">
              {loadError}
            </div>
          ) : (
            <div ref={waveRef} className="w-full" />
          )}
        </div>
      </div>
    </div>
  );
}

export default function StoryAnalysis() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const projectName = location.state?.projectName || `Project ${id}`;
  const unitName = location.state?.unitName;
  const displayProjectName = unitName ? `${projectName} - ${unitName}` : projectName;
  const narrationChoice = location.state?.narrationChoice || 'self';

  const [requirements, setRequirements] = useState([]);
  const [status, setStatus] = useState('queued');
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');

  const storyText = location.state?.storyText || '';

  const voiceRequirements = useMemo(
    () => requirements.filter((item) => item.asset_kind === 'voice'),
    [requirements]
  );
  const readyVoiceCount = voiceRequirements.filter((item) => item.status === 'ready').length;
  const missingCount = requirements.filter((item) => item.status === 'missing').length;
  const needsAssets = narrationChoice !== 'ai' && missingCount > 0;

  const analysisSummary = useMemo(() => {
    const summary = { voice: 0, music: 0, ambience: 0, sfx: 0 };
    for (const item of requirements) {
      if (summary[item.asset_kind] !== undefined) {
        summary[item.asset_kind] += 1;
      }
    }
    return summary;
  }, [requirements]);

  useEffect(() => {
    let alive = true;

    async function loadAnalysis(isInitialLoad = false) {
      try {
        if (isInitialLoad) {
          setLoading(true);
        } else {
          setIsRefreshing(true);
        }
        const [reqRes, statusRes] = await Promise.all([api.getRequirements(id), api.getStatus(id)]);
        if (!alive) return;
        setRequirements(reqRes.items || []);
        setStatus(statusRes.status || 'queued');
        if (statusRes.status === 'failed' && statusRes.error) {
          setError(statusRes.error);
        } else if (statusRes.status !== 'failed') {
          setError('');
        }
      } catch (loadErr) {
        if (!alive) return;
        setError((prev) => prev || loadErr.message || 'Failed to load analysis');
      } finally {
        if (alive) {
          if (isInitialLoad) {
            setLoading(false);
          } else {
            setIsRefreshing(false);
          }
        }
      }
    }

    loadAnalysis(true);
    return () => {
      alive = false;
    };
  }, [id]);

  const handleGenerateAudio = async () => {
    if (status === 'done') {
      navigate(`/projects/${id}/output`, { state: { ...location.state } });
      return;
    }

    if (needsAssets) {
      navigate(`/projects/${id}/assets`, { state: { ...location.state } });
      return;
    }

    setGenerating(true);
    setError('');
    try {
      await api.runStage2(id);
      for (let attempt = 0; attempt < 300; attempt += 1) {
        const jobStatus = await api.getStatus(id);
        setStatus(jobStatus.status);
        if (jobStatus.status === 'done') {
          navigate(`/projects/${id}/output`, { state: { ...location.state } });
          return;
        }
        if (jobStatus.status === 'failed') {
          throw new Error(jobStatus.error || 'Audio generation failed');
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      throw new Error('Audio generation is taking too long. Please try again.');
    } catch (runErr) {
      setError(runErr.message || 'Failed to generate audio');
      setStatus('failed');
      setGenerating(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar projectName={displayProjectName} step={2} totalSteps={4} />

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-10 space-y-8">
        <div className="flex flex-col lg:flex-row lg:items-start gap-4 lg:gap-8 justify-between">
          <div>
            <h1 className="text-3xl font-extrabold text-zinc-900 tracking-tight flex items-center gap-3">
              <Sparkles className="text-violet-500" /> Story Analysis
            </h1>
            <p className="text-textSecondary mt-2">
              Review extracted tracks and details before generating final audio.
            </p>
          </div>

          <button
            type="button"
            onClick={handleGenerateAudio}
            disabled={generating || loading}
            className="btn-primary py-2.5 px-4 text-sm self-start"
          >
            {generating ? (
              <>
                <Loader2 className="animate-spin mr-2" size={16} />
                Generating...
              </>
            ) : (
              <>
                {status === 'done' ? 'Open Output' : needsAssets ? 'Add Missing Assets' : 'Generate Audio'}
                <ArrowRight className="ml-2" size={16} />
              </>
            )}
          </button>
        </div>

        <div className="flex items-center gap-4">
          {isRefreshing && !loading && (
            <p className="text-xs text-textSecondary uppercase tracking-wider">Refreshing analysis...</p>
          )}
          {!loading && (
            <button
              type="button"
              onClick={async () => {
                setIsRefreshing(true);
                try {
                  const [reqRes, statusRes] = await Promise.all([api.getRequirements(id), api.getStatus(id)]);
                  setRequirements(reqRes.items || []);
                  setStatus(statusRes.status || 'queued');
                  if (statusRes.status === 'failed' && statusRes.error) {
                    setError(statusRes.error);
                  }
                } catch (refreshErr) {
                  setError(refreshErr.message || 'Failed to refresh analysis');
                } finally {
                  setIsRefreshing(false);
                }
              }}
              className="text-xs uppercase tracking-wider text-violet-700 hover:text-violet-800 border border-violet-500/30 bg-violet-500/10 px-3 py-1.5 rounded-md"
            >
              Refresh
            </button>
          )}
        </div>

        {error && (
          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="card text-center py-16">
            <Loader2 className="animate-spin inline-block text-violet-500 mb-3" />
            <p className="text-textSecondary">Loading analysis...</p>
          </div>
        ) : (
          <>
            <section className="grid grid-cols-1 xl:grid-cols-3 gap-6">
              <div className="card xl:col-span-2">
                <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-900 mb-4 flex items-center gap-2">
                  <FileText size={16} className="text-violet-500" /> Story Text
                </h2>
                <div className="max-h-[360px] overflow-auto rounded-xl border border-zinc-200 bg-white p-4 text-sm leading-7 text-zinc-700 whitespace-pre-wrap">
                  {storyText || 'No story text available.'}
                </div>
              </div>

              <div className="card space-y-4">
                <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-900">Analysis Details</h2>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between text-textSecondary">
                    <span>Status</span>
                    <span className="font-semibold text-zinc-900 uppercase">{status}</span>
                  </div>
                  <div className="flex justify-between text-textSecondary">
                    <span>Total clips</span>
                    <span className="font-semibold text-zinc-900">{requirements.length}</span>
                  </div>
                  <div className="flex justify-between text-textSecondary">
                    <span>Voice clips</span>
                    <span className="font-semibold text-zinc-900">{analysisSummary.voice}</span>
                  </div>
                  <div className="flex justify-between text-textSecondary">
                    <span>Ready voice clips</span>
                    <span className="font-semibold text-zinc-900">{readyVoiceCount}</span>
                  </div>
                  <div className="flex justify-between text-textSecondary">
                    <span>Missing assets</span>
                    <span className="font-semibold text-zinc-900">{missingCount}</span>
                  </div>
                </div>

                <div className="pt-2 border-t border-zinc-200 text-xs text-textSecondary uppercase tracking-wider space-y-1">
                  <div>Music: {analysisSummary.music}</div>
                  <div>Ambience: {analysisSummary.ambience}</div>
                  <div>SFX: {analysisSummary.sfx}</div>
                </div>
              </div>
            </section>

            <section className="card">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-900">
                  Audio Files Waveform Track
                </h2>
                <span className="text-xs text-textSecondary uppercase tracking-wider">
                  {voiceRequirements.length} voice clips
                </span>
              </div>

              {voiceRequirements.length === 0 ? (
                <p className="text-sm text-textSecondary">No voice clips extracted yet.</p>
              ) : (
                <div className="space-y-4">
                  {voiceRequirements.map((item) => (
                    <div key={item.requirement_id} className="rounded-xl border border-zinc-200 bg-white p-3">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                        <div className="text-sm font-semibold text-zinc-900 truncate">
                          {item.tts_text || item.descriptor}
                        </div>
                        <span
                          className={`text-[11px] uppercase tracking-wider px-2 py-1 rounded-md border ${
                            item.status === 'ready'
                              ? 'bg-violet-500/10 border-violet-500/20 text-violet-700'
                              : 'bg-amber-500/10 border-amber-500/20 text-amber-700'
                          }`}
                        >
                          {item.status}
                        </span>
                      </div>
                      <RequirementWaveTrack projectId={id} requirement={item} />
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
