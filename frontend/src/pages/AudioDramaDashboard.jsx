import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import WaveSurfer from 'wavesurfer.js';
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  FolderOpen,
  FileAudio,
  List,
  Mic,
  Music,
  Pause,
  Play,
  Plus,
  Sparkles,
  Upload,
  Volume2,
} from 'lucide-react';
import { api } from '../api';
import { supabase } from '../supabase';

function formatClock(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/** Whole-second total length; rounds up so decoder timing (e.g. 5.9s) matches WAV header / tick labels. */
function formatClockTotal(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return '0:00';
  const totalWholeSec = Math.ceil(seconds - 1e-6);
  const mins = Math.floor(totalWholeSec / 60);
  const secs = totalWholeSec % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function statusTone(status) {
  if (status === 'done') return 'text-emerald-600 bg-emerald-50 border-emerald-200';
  if (status === 'failed') return 'text-rose-700 bg-rose-50 border-rose-200';
  if (status === 'awaiting_assets') return 'text-amber-700 bg-amber-50 border-amber-200';
  return 'text-zinc-700 bg-zinc-50 border-zinc-200';
}

function assetIcon(kind) {
  if (kind === 'voice') return <Mic size={16} />;
  if (kind === 'music') return <Music size={16} />;
  if (kind === 'sfx') return <Sparkles size={16} />;
  return <Volume2 size={16} />;
}

function categoryLabel(kind) {
  if (kind === 'all') return 'All';
  if (kind === 'sfx') return 'SFX';
  return kind.charAt(0).toUpperCase() + kind.slice(1);
}

function formatErrorMessage(message) {
  const raw = String(message || '').trim();
  if (!raw) return 'Something went wrong.';
  return raw.length > 240 ? `${raw.slice(0, 237)}...` : raw;
}

function ttsFailureMessage(result) {
  const chars = Array.isArray(result?.characters) ? result.characters : [];
  const firstFailure = chars
    .flatMap((entry) => (Array.isArray(entry?.failed) ? entry.failed : []))
    .find((item) => item && item.error);
  const raw = String(firstFailure?.error || '').toLowerCase();
  if (!raw) return `TTS failed for ${result?.total_failed || 0} clip(s). Check API logs for details.`;
  if (raw.includes('quota') || raw.includes('resource_exhausted') || raw.includes('429')) {
    const retryDelaySec =
      (() => {
        const original = String(firstFailure?.error || '');
        const retryInMatch = original.match(/retry in\s+(\d+(?:\.\d+)?)s?/i);
        if (retryInMatch?.[1]) return Math.ceil(Number(retryInMatch[1]));
        const retryDelayMatch = original.match(/"retryDelay"\s*:\s*"(\d+)s"/i);
        if (retryDelayMatch?.[1]) return Number(retryDelayMatch[1]);
        return null;
      })();
    if (Number.isFinite(retryDelaySec) && retryDelaySec > 0) {
      return `Gemini TTS quota/rate limit reached. Try again in about ${retryDelaySec}s, or use a billed API key.`;
    }
    return 'Gemini TTS quota/rate limit reached. Wait a bit or use a billed API key, then try Generate again.';
  }
  return formatErrorMessage(firstFailure.error);
}

function normalizeSpeakerName(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '');
}

function extractVoiceTrackId(requirementId) {
  const parts = String(requirementId || '').split(':');
  return parts.length >= 2 ? parts[1] : '';
}

function humanizeTrack(trackId) {
  return String(trackId || '')
    .replace(/^character_/i, '')
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

function chooseTickStep(totalSeconds) {
  if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) return 5;
  if (totalSeconds <= 30) return 5;
  if (totalSeconds <= 60) return 10;
  if (totalSeconds <= 120) return 15;
  if (totalSeconds <= 300) return 30;
  if (totalSeconds <= 600) return 60;
  if (totalSeconds <= 1800) return 300;
  return 600;
}

/** Supabase-backed unit rows + optional router state (may be absent after refresh). */
function resolveActiveEpisode(rows, routeUnitId, routeUnitName) {
  const list = Array.isArray(rows) ? rows : [];
  const first = list[0];
  if (!first) {
    return { id: '', name: '' };
  }
  const rid = typeof routeUnitId === 'string' ? routeUnitId.trim() : '';
  if (!rid) {
    return { id: first.id, name: first.name ? String(first.name).trim() : '' };
  }
  const hit = list.find((c) => String(c.id) === rid);
  if (!hit) {
    return { id: first.id, name: first.name ? String(first.name).trim() : '' };
  }
  const dbName = hit.name ? String(hit.name).trim() : '';
  const rn = typeof routeUnitName === 'string' ? routeUnitName.trim() : '';
  return { id: hit.id, name: dbName || rn };
}

export default function AudioDramaDashboard() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const waveformRef = useRef(null);
  const wavesurferRef = useRef(null);
  const outputDurationFromApiRef = useRef(null);

  const projectName = location.state?.projectName || `Project ${id}`;
  const routeStateUnitId =
    location.state?.unitId !== undefined && location.state?.unitId !== null && String(location.state.unitId).trim() !== ''
      ? String(location.state.unitId).trim()
      : '';
  const routeStateUnitName =
    typeof location.state?.unitName === 'string' && location.state.unitName.trim() !== ''
      ? location.state.unitName.trim()
      : '';
  const narrationChoice = location.state?.narrationChoice || 'self';

  const [activeUnitId, setActiveUnitId] = useState(routeStateUnitId);
  const [activeUnitName, setActiveUnitName] = useState(routeStateUnitName);

  const [scriptText, setScriptText] = useState(location.state?.storyText || '');
  const [status, setStatus] = useState('queued');
  const [requirements, setRequirements] = useState([]);
  const [error, setError] = useState('');

  const [saving, setSaving] = useState(false);
  const [runningStage1, setRunningStage1] = useState(false);
  const [runningStage2, setRunningStage2] = useState(false);
  const [uploadTarget, setUploadTarget] = useState(null);
  const [removingRequirementId, setRemovingRequirementId] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState('chapters');
  const [chapters, setChapters] = useState([]);
  const [chaptersLoading, setChaptersLoading] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [voiceMapState, setVoiceMapState] = useState({
    loading: false,
    error: '',
    defaultVoice: '',
    characters: [],
  });
  const [activeTtsSpeaker, setActiveTtsSpeaker] = useState('');
  const [generatingAllSpeakers, setGeneratingAllSpeakers] = useState(false);
  const [pacingState, setPacingState] = useState({ loading: false, error: '', scenes: [] });
  const [pacingEdits, setPacingEdits] = useState({});
  const [savingPacing, setSavingPacing] = useState(false);

  const [audioReady, setAudioReady] = useState(false);
  const [outputAudioUrl, setOutputAudioUrl] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  const groupedAssets = useMemo(() => {
    const groups = { voice: [], music: [], ambience: [], sfx: [] };
    for (const item of requirements) {
      if (groups[item.asset_kind]) groups[item.asset_kind].push(item);
    }
    return groups;
  }, [requirements]);

  const totalAssets = requirements.length;
  const readyAssets = requirements.filter((item) => item.status === 'ready').length;
  const assetsReady = totalAssets > 0 && readyAssets === totalAssets;
  const selectedAssets = selectedCategory === 'all' ? requirements : (groupedAssets[selectedCategory] || []);

  const voiceTrackStats = useMemo(() => {
    const stats = new Map();
    for (const item of groupedAssets.voice || []) {
      const trackId = extractVoiceTrackId(item.requirement_id);
      if (!trackId) continue;
      const prev = stats.get(trackId) || { trackId, total: 0, ready: 0 };
      prev.total += 1;
      if (item.status === 'ready') prev.ready += 1;
      stats.set(trackId, prev);
    }
    return Array.from(stats.values());
  }, [groupedAssets.voice]);

  const voiceCharacters = useMemo(() => {
    const statsByNorm = new Map();
    for (const stat of voiceTrackStats) {
      statsByNorm.set(normalizeSpeakerName(humanizeTrack(stat.trackId)), stat);
      statsByNorm.set(normalizeSpeakerName(stat.trackId), stat);
    }
    const fromMap = (voiceMapState.characters || []).map((entry) => {
      const speaker = String(entry.speaker || '').trim();
      const norm = normalizeSpeakerName(speaker);
      const stat = statsByNorm.get(norm);
      return {
        speaker,
        voice: String(entry.voice || ''),
        total: Number.isFinite(entry.clip_count) ? entry.clip_count : (stat?.total || 0),
        ready: stat?.ready || 0,
      };
    });
    if (fromMap.length > 0) return fromMap;
    return voiceTrackStats.map((stat) => ({
      speaker: humanizeTrack(stat.trackId),
      voice: '',
      total: stat.total,
      ready: stat.ready,
    }));
  }, [voiceMapState.characters, voiceTrackStats]);

  const timelineTicks = useMemo(() => {
    if (!Number.isFinite(duration) || duration <= 0) {
      return ['0:00', '0:05', '0:10', '0:15', '0:20', '0:25', '0:30'];
    }
    const roundedDuration = Math.ceil(duration);
    const step = chooseTickStep(roundedDuration);
    const ticks = [];
    for (let sec = 0; sec <= roundedDuration; sec += step) {
      ticks.push(formatClock(sec));
    }
    const lastLabel = formatClock(roundedDuration);
    if (ticks[ticks.length - 1] !== lastLabel) ticks.push(lastLabel);
    return ticks;
  }, [duration]);


  const loadPacing = async () => {
    setPacingState((prev) => ({ ...prev, loading: true, error: '' }));
    try {
      const result = await api.getPacing(id);
      setPacingState({
        loading: false,
        error: '',
        scenes: Array.isArray(result.scenes) ? result.scenes : [],
      });
      setPacingEdits((result.overrides && result.overrides.clips) || {});
    } catch (err) {
      setPacingState((prev) => ({
        ...prev,
        loading: false,
        error: formatErrorMessage(err.message || 'Failed to load pacing'),
      }));
    }
  };

  const loadVoiceMap = async () => {
    setVoiceMapState((prev) => ({ ...prev, loading: true, error: '' }));
    try {
      const result = await api.getVoiceMap(id);
      setVoiceMapState({
        loading: false,
        error: '',
        defaultVoice: result.default_voice || '',
        characters: Array.isArray(result.characters) ? result.characters : [],
      });
    } catch (err) {
      setVoiceMapState((prev) => ({
        ...prev,
        loading: false,
        error: formatErrorMessage(err.message || 'Failed to load voice map'),
      }));
    }
  };

  const loadStatusAndRequirements = async () => {
    const [statusRes, requirementsRes] = await Promise.all([api.getStatus(id), api.getRequirements(id)]);
    setStatus(statusRes.status || 'queued');
    setRequirements(requirementsRes.items || []);
    if (statusRes.status === 'failed' && statusRes.error) {
      setError(formatErrorMessage(statusRes.error));
    } else {
      setError('');
    }
  };

  const loadOutputAudio = async (isStale = () => false) => {
    if (!activeUnitId.trim()) {
      if (isStale()) return;
      outputDurationFromApiRef.current = null;
      setOutputAudioUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      setAudioReady(false);
      return;
    }

    const { blobUrl, durationSeconds } = await api.getOutputAudioBlobUrl(id, activeUnitId, activeUnitName);
    outputDurationFromApiRef.current =
      typeof durationSeconds === 'number' && Number.isFinite(durationSeconds) && durationSeconds > 0 ? durationSeconds : null;
    if (isStale()) {
      if (blobUrl) URL.revokeObjectURL(blobUrl);
      return;
    }
    setOutputAudioUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return blobUrl;
    });
    setAudioReady(!!blobUrl);
  };

  useLayoutEffect(() => {
    const url = outputAudioUrl;
    const container = waveformRef.current;

    if (!url) {
      wavesurferRef.current?.destroy();
      wavesurferRef.current = null;
      setDuration(0);
      setCurrentTime(0);
      setIsPlaying(false);
      return;
    }

    if (!container) {
      return;
    }

    wavesurferRef.current?.destroy();

    const ws = WaveSurfer.create({
      container,
      waveColor: 'rgba(24, 24, 27, 0.2)',
      progressColor: '#18181b',
      cursorColor: '#3f3f46',
      height: 58,
      barWidth: 2,
      barGap: 2,
      barRadius: 2,
      normalize: true,
    });

    ws.on('ready', () => {
      const decoded = ws.getDuration();
      const srv = outputDurationFromApiRef.current;
      const merged =
        typeof srv === 'number' && Number.isFinite(srv) && srv > 0 ? Math.max(decoded, srv) : decoded;
      setDuration(merged);
    });
    ws.on('audioprocess', () => setCurrentTime(ws.getCurrentTime()));
    ws.on('play', () => setIsPlaying(true));
    ws.on('pause', () => setIsPlaying(false));
    ws.on('finish', () => setIsPlaying(false));
    ws.load(url);
    wavesurferRef.current = ws;

    return () => {
      ws.destroy();
      if (wavesurferRef.current === ws) {
        wavesurferRef.current = null;
      }
    };
  }, [outputAudioUrl]);

  useEffect(() => {
    let active = true;
    const init = async () => {
      try {
        setError('');
        await loadStatusAndRequirements();
        await loadVoiceMap();
        await loadPacing();
        await loadOutputAudio(() => !active);
      } catch (err) {
        if (!active) return;
        setError(formatErrorMessage(err.message || 'Failed to load dashboard'));
      }
    };
    init();

    return () => {
      active = false;
      wavesurferRef.current?.destroy();
      wavesurferRef.current = null;
    };
  }, [id, activeUnitId, activeUnitName]);

  useEffect(() => {
    return () => {
      setOutputAudioUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      setAudioReady(false);
    };
  }, []);

  useEffect(() => {
    if (selectedCategory === 'all' || selectedCategory === 'chapters') return;
    if ((groupedAssets[selectedCategory] || []).length > 0) return;
    setSelectedCategory('chapters');
  }, [groupedAssets, selectedCategory]);

  useEffect(() => {
    let alive = true;
    const loadChapters = async () => {
      setChaptersLoading(true);
      try {
        const { data, error: dbError } = await supabase
          .from('units')
          .select('id,name,created_at,status')
          .eq('project_id', id)
          .order('created_at', { ascending: true });
        if (dbError) throw dbError;
        if (alive) setChapters(data || []);
      } catch {
        if (alive) setChapters([]);
      } finally {
        if (alive) setChaptersLoading(false);
      }
    };
    loadChapters();
    return () => {
      alive = false;
    };
  }, [id]);

  useEffect(() => {
    if (chaptersLoading) return;
    const next = resolveActiveEpisode(chapters, routeStateUnitId, routeStateUnitName);
    setActiveUnitId((prev) => (prev === next.id ? prev : next.id));
    setActiveUnitName((prev) => (prev === next.name ? prev : next.name));
  }, [chapters, chaptersLoading, routeStateUnitId, routeStateUnitName]);

  const saveScript = async () => {
    if (!activeUnitId.trim()) {
      setError('Missing unit id. Open this dashboard from the project page.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await api.saveStory(id, {
        unit_id: activeUnitId,
        unit_name: activeUnitName,
        story_text: scriptText,
      });
    } catch (err) {
      setError(formatErrorMessage(err.message || 'Failed to save script'));
    } finally {
      setSaving(false);
    }
  };

  const runStage1 = async () => {
    if (!activeUnitId.trim()) {
      setError('Missing unit id. Open this dashboard from the project page.');
      return;
    }
    setRunningStage1(true);
    setError('');
    try {
      await saveScript();
      await api.runStage1(id);
      for (let attempt = 0; attempt < 60; attempt += 1) {
        const st = await api.getStatus(id);
        setStatus(st.status || 'queued');
        if (st.status === 'awaiting_assets' || st.status === 'stage2' || st.status === 'done') {
          break;
        }
        if (st.status === 'failed') {
          throw new Error(st.error || 'Stage 1 failed');
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      await loadStatusAndRequirements();
      await loadVoiceMap();
      await loadPacing();
    } catch (err) {
      setError(formatErrorMessage(err.message || 'Stage 1 failed'));
    } finally {
      setRunningStage1(false);
    }
  };

  const runStage2 = async () => {
    setRunningStage2(true);
    setError('');
    try {
      await api.runStage2(id);
      for (let attempt = 0; attempt < 60; attempt += 1) {
        const st = await api.getStatus(id);
        setStatus(st.status || 'queued');
        if (st.status === 'done') break;
        if (st.status === 'failed') {
          throw new Error(st.error || 'Stage 2 failed');
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      await loadStatusAndRequirements();
      await loadOutputAudio();
    } catch (err) {
      setError(formatErrorMessage(err.message || 'Stage 2 failed'));
    } finally {
      setRunningStage2(false);
    }
  };

  const triggerUpload = (requirement) => {
    setUploadTarget(requirement);
    fileInputRef.current?.click();
  };

  const onFileChange = async (event) => {
    const file = event.target.files?.[0];
    if (!file || !uploadTarget) return;
    setError('');
    try {
      await api.uploadAsset(id, uploadTarget.folder, file);
      await loadStatusAndRequirements();
    } catch (err) {
      setError(formatErrorMessage(err.message || 'Upload failed'));
    } finally {
      setUploadTarget(null);
      event.target.value = '';
    }
  };

  const removeAsset = async (requirement) => {
    setRemovingRequirementId(requirement.requirement_id);
    setError('');
    try {
      await api.removeAsset(id, requirement.folder);
      await loadStatusAndRequirements();
    } catch (err) {
      setError(formatErrorMessage(err.message || 'Remove failed'));
    } finally {
      setRemovingRequirementId(null);
    }
  };

  const runCharacterTts = async (speaker) => {
    setActiveTtsSpeaker(speaker);
    setError('');
    try {
      const result = await api.generateDramaTts(id, { character: speaker });
      if (result?.total_failed > 0) {
        throw new Error(ttsFailureMessage(result));
      }
      await loadStatusAndRequirements();
      await loadVoiceMap();
      await loadPacing();
    } catch (err) {
      setError(formatErrorMessage(err.message || 'Character TTS failed'));
    } finally {
      setActiveTtsSpeaker('');
    }
  };

  const runAllCharacterTts = async () => {
    setGeneratingAllSpeakers(true);
    setError('');
    try {
      const result = await api.generateDramaTts(id);
      if (result?.total_failed > 0) {
        throw new Error(ttsFailureMessage(result));
      }
      await loadStatusAndRequirements();
      await loadVoiceMap();
      await loadPacing();
    } catch (err) {
      setError(formatErrorMessage(err.message || 'TTS generation failed'));
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
    setError('');
    try {
      await api.savePacing(id, pacingEdits);
      await loadPacing();
    } catch (err) {
      setError(formatErrorMessage(err.message || 'Failed to save pacing'));
    } finally {
      setSavingPacing(false);
    }
  };

  const goToOutput = () => {
    navigate(`/projects/${id}/output`, {
      state: {
        ...location.state,
        projectName,
        unitId: activeUnitId,
        unitName: activeUnitName,
      },
    });
  };

  return (
    <div className="min-h-screen bg-background text-textPrimary flex flex-col">
      <header className="h-12 border-b border-border bg-surface px-4 flex items-center justify-between">
        <div className="relative flex items-center">
          <button
            onClick={() => setMenuOpen((prev) => !prev)}
            className="h-8 w-8 rounded-md border border-border bg-white hover:bg-surfaceHover inline-flex items-center justify-center"
            aria-label="Open project menu"
          >
            <List size={16} />
          </button>
          {menuOpen && (
            <div className="absolute top-10 left-0 z-50 w-56 rounded-xl border border-border bg-white shadow-lg py-1 text-sm">
              <button
                onClick={() => {
                  setMenuOpen(false);
                  navigate('/profile');
                }}
                className="w-full text-left px-3 py-2 hover:bg-surfaceHover"
              >
                Back to projects
              </button>
              <button
                onClick={() => {
                  setMenuOpen(false);
                  navigate(`/project/${id}`);
                }}
                className="w-full text-left px-3 py-2 hover:bg-surfaceHover"
              >
                Project details
              </button>
            </div>
          )}
        </div>
        <div className="text-sm font-medium truncate max-w-[40vw]">{projectName}</div>
        <div className="w-24 flex justify-end">
          <button
            onClick={() => navigate(`/project/${id}`)}
            className="h-8 px-3 text-xs rounded-md border border-border bg-white hover:bg-surfaceHover"
          >
            Back
          </button>
        </div>
      </header>

      <input ref={fileInputRef} type="file" accept="audio/*,.wav,.mp3,.flac,.ogg,.m4a" className="hidden" onChange={onFileChange} />

      <div className="flex flex-1 overflow-hidden">
        <aside className="w-16 bg-surface border-r border-border flex flex-col items-center py-4 gap-3">
          <button
            onClick={() => setSelectedCategory('chapters')}
            className={`w-9 h-9 rounded-lg flex items-center justify-center border ${
              selectedCategory === 'chapters' ? 'bg-accent text-white border-accent' : 'border-border text-textSecondary'
            }`}
            title="Chapters"
          >
            <FolderOpen size={16} />
          </button>
          <button
            onClick={() => setSelectedCategory('voice')}
            className={`w-9 h-9 rounded-lg flex items-center justify-center border ${
              selectedCategory === 'voice' ? 'bg-accent text-white border-accent' : 'border-border text-textSecondary'
            }`}
            title="Voice assets"
          >
            <Mic size={16} />
          </button>
          <button
            onClick={() => setSelectedCategory('sfx')}
            className={`w-9 h-9 rounded-lg flex items-center justify-center border ${
              selectedCategory === 'sfx' ? 'bg-accent text-white border-accent' : 'border-border text-textSecondary'
            }`}
            title="SFX assets"
          >
            <Sparkles size={16} />
          </button>
          <button
            onClick={() => setSelectedCategory('music')}
            className={`w-9 h-9 rounded-lg flex items-center justify-center border ${
              selectedCategory === 'music' ? 'bg-accent text-white border-accent' : 'border-border text-textSecondary'
            }`}
            title="Music assets"
          >
            <Music size={16} />
          </button>
          <button
            onClick={() => setSelectedCategory('ambience')}
            className={`w-9 h-9 rounded-lg flex items-center justify-center border ${
              selectedCategory === 'ambience' ? 'bg-accent text-white border-accent' : 'border-border text-textSecondary'
            }`}
            title="Ambience assets"
          >
            <Volume2 size={16} />
          </button>
        </aside>

        <aside className="w-[320px] bg-surface border-r border-border p-4 overflow-y-auto flex flex-col">
          {selectedCategory === 'chapters' ? (
            <div className="bg-white border border-border rounded-xl p-3 flex-1 flex flex-col min-h-0">
              <div className="flex items-center justify-between mb-2 shrink-0">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider">
                  <FolderOpen size={16} />
                  Chapters
                </div>
                <span className="text-xs text-textMuted">{chapters.length}</span>
              </div>
              <div className="space-y-2 overflow-y-auto flex-1 min-h-[200px]">
                {chaptersLoading && <p className="text-xs text-textMuted">Loading chapters...</p>}
                {!chaptersLoading && chapters.length === 0 && <p className="text-xs text-textMuted">No chapters found.</p>}
                {chapters.map((chapter) => (
                  <button
                    key={chapter.id}
                    onClick={() =>
                      navigate(`/projects/${id}/story`, {
                        state: {
                          ...location.state,
                          unitId: chapter.id,
                          unitName: chapter.name,
                          projectName,
                          narrationChoice,
                        },
                      })
                    }
                    className={`w-full border rounded-lg p-2 text-left hover:bg-surfaceHover ${
                      chapter.id === activeUnitId ? 'border-accent bg-accent/10' : 'border-border bg-white'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold truncate">{chapter.name}</span>
                      <ChevronRight size={14} className="text-textMuted shrink-0" />
                    </div>
                    <div className="mt-1 text-[10px] uppercase tracking-wider text-textMuted">{chapter.status || 'draft'}</div>
                  </button>
                ))}
                <button
                  onClick={() => navigate(`/project/${id}`)}
                  className="w-full border border-dashed border-border rounded-lg p-2 text-xs text-textSecondary hover:bg-surfaceHover inline-flex items-center justify-center gap-1"
                >
                  <Plus size={12} />
                  Add chapter
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className={`inline-flex items-center gap-2 text-xs border rounded-full px-3 py-1 mb-4 ${statusTone(status)}`}>
                <span className="w-1.5 h-1.5 rounded-full bg-current" />
                {status}
              </div>

              <div className="bg-white border border-border rounded-xl p-4 mb-4">
                <div className="text-xs uppercase tracking-wider text-textMuted mb-2">Assets</div>
                <div className="text-sm font-semibold">
                  {readyAssets} / {totalAssets} ready
                </div>
                {totalAssets > 0 && !assetsReady && (
                  <p className="text-xs text-amber-700 mt-2">Upload missing files, then run Stage 2.</p>
                )}
              </div>

              {selectedCategory === 'voice' && (
                <>
                  <div className="bg-white border border-border rounded-xl p-3 mb-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="text-xs font-semibold uppercase tracking-wider">Character Voice (AI TTS)</div>
                      <button
                        onClick={runAllCharacterTts}
                        disabled={generatingAllSpeakers || voiceCharacters.length === 0}
                        className="text-[10px] uppercase tracking-wider border border-border rounded px-2 py-1 hover:bg-surfaceHover disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {generatingAllSpeakers ? 'Generating...' : 'Generate All'}
                      </button>
                    </div>
                    {voiceMapState.defaultVoice && (
                      <p className="text-[11px] text-textMuted mb-2">Fallback voice: {voiceMapState.defaultVoice}</p>
                    )}
                    {voiceMapState.loading ? (
                      <p className="text-xs text-textMuted">Loading voice map...</p>
                    ) : voiceCharacters.length === 0 ? (
                      <p className="text-xs text-textMuted">Run Stage 1 to discover character voice clips.</p>
                    ) : (
                      <div className="space-y-2 max-h-52 overflow-y-auto">
                        {voiceCharacters.map((entry) => (
                          <div key={entry.speaker} className="border border-border rounded-lg p-2">
                            <div className="flex items-center justify-between gap-2">
                              <div>
                                <div className="text-xs font-semibold truncate">{entry.speaker}</div>
                                <div className="text-[10px] text-textMuted">
                                  {entry.ready}/{entry.total} ready{entry.voice ? ` • ${entry.voice}` : ''}
                                </div>
                              </div>
                              <button
                                onClick={() => runCharacterTts(entry.speaker)}
                                disabled={activeTtsSpeaker === entry.speaker}
                                className="text-[10px] uppercase tracking-wider border border-border rounded px-2 py-1 hover:bg-surfaceHover disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
                              >
                                {activeTtsSpeaker === entry.speaker ? 'Generating...' : 'Generate'}
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    {voiceMapState.error && <p className="mt-2 text-xs text-red-500">{voiceMapState.error}</p>}
                    <p className="mt-2 text-[11px] text-textMuted">
                      You can generate AI voice per character, then replace/remove any clip manually.
                    </p>
                  </div>

                  <div className="bg-white border border-border rounded-xl p-3 mb-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="text-xs font-semibold uppercase tracking-wider">Pacing Review</div>
                      <button
                        onClick={savePacing}
                        disabled={savingPacing || pacingState.loading}
                        className="text-[10px] uppercase tracking-wider border border-border rounded px-2 py-1 hover:bg-surfaceHover disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {savingPacing ? 'Saving...' : 'Save'}
                      </button>
                    </div>
                    {pacingState.loading ? (
                      <p className="text-xs text-textMuted">Loading pacing...</p>
                    ) : pacingState.scenes.length === 0 ? (
                      <p className="text-xs text-textMuted">Run Stage 1 to generate pacing clips.</p>
                    ) : (
                      <div className="space-y-3 max-h-64 overflow-y-auto">
                        {pacingState.scenes.map((scene) => (
                          <div key={scene.scene_id} className="border border-border rounded-lg p-2">
                            <div className="text-[11px] font-semibold mb-1">
                              {scene.scene_name} - {scene.estimated_duration_s}s / floor {scene.floor_s}s
                            </div>
                            <div className="space-y-2">
                              {(scene.clips || []).map((clip) => {
                                const override = pacingEdits[clip.requirement_id] || {};
                                const preValue = override.pre_silence_s ?? clip.pre_silence_s ?? 0;
                                const postValue = override.post_silence_s ?? clip.post_silence_s ?? 0;
                                return (
                                  <div key={clip.requirement_id} className="rounded border border-border p-2">
                                    <div className="text-[10px] text-textMuted mb-1">
                                      {clip.dramatic_function || 'dialogue'} - {clip.speaker}
                                    </div>
                                    <div className="text-xs mb-1 truncate">{clip.line_text}</div>
                                    <label className="text-[10px] text-textMuted">Pre ({Math.round(preValue * 1000)}ms)</label>
                                    <input
                                      type="range"
                                      min="0"
                                      max="5"
                                      step="0.1"
                                      value={preValue}
                                      onChange={(e) => updatePacingField(clip.requirement_id, 'pre_silence_s', Number(e.target.value))}
                                      className="w-full"
                                    />
                                    <label className="text-[10px] text-textMuted">Post ({Math.round(postValue * 1000)}ms)</label>
                                    <input
                                      type="range"
                                      min="0"
                                      max="5"
                                      step="0.1"
                                      value={postValue}
                                      onChange={(e) => updatePacingField(clip.requirement_id, 'post_silence_s', Number(e.target.value))}
                                      className="w-full"
                                    />
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    {pacingState.error && <p className="mt-2 text-xs text-red-500">{pacingState.error}</p>}
                  </div>
                </>
              )}

              <div className="bg-white border border-border rounded-xl p-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider">
                    {assetIcon(selectedCategory)}
                    {`${categoryLabel(selectedCategory)} Assets`}
                  </div>
                  <span className="text-xs text-textMuted">{selectedAssets.length}</span>
                </div>
                <div className="space-y-2 max-h-[460px] overflow-y-auto">
                  {selectedAssets.length === 0 && <p className="text-xs text-textMuted">No items yet.</p>}
                  {selectedAssets.map((item) => (
                    <div key={item.requirement_id} className="border border-border rounded-lg p-2">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[10px] uppercase tracking-wider text-textMuted">{categoryLabel(item.asset_kind)}</span>
                        <span
                          className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded ${
                            item.status === 'ready' ? 'bg-emerald-100 text-emerald-700' : 'bg-subtle text-textSecondary'
                          }`}
                        >
                          {item.status}
                        </span>
                      </div>
                      <p className="text-xs text-textSecondary wrap-break-word">{item.tts_text || item.descriptor}</p>
                      <div className="mt-2 flex justify-end gap-2">
                        {item.status === 'ready' && (
                          <button
                            onClick={() => removeAsset(item)}
                            disabled={removingRequirementId === item.requirement_id}
                            className="text-[10px] uppercase tracking-wider border border-border rounded px-2 py-1 hover:bg-surfaceHover disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {removingRequirementId === item.requirement_id ? 'Removing...' : 'Remove'}
                          </button>
                        )}
                        <button
                          onClick={() => triggerUpload(item)}
                          className="text-[10px] uppercase tracking-wider border border-border rounded px-2 py-1 hover:bg-surfaceHover"
                        >
                          <Upload size={11} className="inline mr-1" />
                          {item.status === 'ready' ? 'Replace' : 'Upload'}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </aside>

        <main className="flex-1 flex flex-col overflow-hidden bg-background">
          <header className="h-14 border-b border-border bg-background px-5 flex items-center justify-between">
            <div className="text-sm font-semibold truncate inline-flex items-center gap-2">
              <span>{projectName} · {activeUnitName || 'Episode'}</span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent text-white uppercase tracking-wider">Drama</span>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={saveScript} disabled={saving} className="text-xs border border-border px-3 py-1.5 rounded hover:bg-surfaceHover">
                {saving ? 'Saving...' : 'Save'}
              </button>
              <button
                onClick={runStage1}
                disabled={runningStage1 || !scriptText.trim()}
                className="text-xs border border-accent bg-accent text-white px-3 py-1.5 rounded hover:bg-accentHover"
              >
                {runningStage1 ? 'Running Stage 1...' : 'Run Stage 1'}
              </button>
              <button
                onClick={runStage2}
                disabled={runningStage2 || (!assetsReady && totalAssets > 0)}
                className="text-xs border border-accent bg-accent text-white px-3 py-1.5 rounded hover:bg-accentHover disabled:opacity-50"
              >
                {runningStage2 ? 'Rendering...' : 'Run Stage 2'}
              </button>
            </div>
          </header>

          {error && (
            <div className="mx-5 mt-4 border border-rose-200 bg-rose-50 text-rose-700 rounded-lg px-3 py-2 text-sm flex items-center gap-2">
              <AlertCircle size={16} />
              {error}
            </div>
          )}

          <section className="flex-1 overflow-y-auto p-5">
            <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-5 h-full">
              <div className="bg-white border border-zinc-300 rounded-xl p-4 flex flex-col">
                <div className="flex items-center justify-between mb-3 border-b border-zinc-200 pb-3">
                  <h3 className="text-sm font-semibold inline-flex items-center gap-2">
                    <Sparkles size={14} />
                    Script Workspace
                  </h3>
                  <span className="text-xs text-zinc-500">{scriptText.length.toLocaleString()} chars</span>
                </div>
                <textarea
                  className="w-full min-h-[420px] flex-1 resize-none rounded-lg border border-zinc-300 bg-zinc-50 p-3 font-mono text-sm leading-6 outline-none focus:border-zinc-500"
                  placeholder="Write or paste your Fountain script here..."
                  value={scriptText}
                  onChange={(e) => setScriptText(e.target.value)}
                />
              </div>

              <div className="space-y-4">
                <div className="bg-white border border-border rounded-xl p-4">
                  <h3 className="text-sm font-semibold mb-2">Pipeline</h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-zinc-500">Stage 1</span>
                      <span className="font-medium">{status === 'queued' ? 'pending' : 'processed'}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-zinc-500">Assets</span>
                      <span className="font-medium">{readyAssets}/{totalAssets}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-zinc-500">Stage 2</span>
                      <span className="font-medium">{status === 'done' ? 'rendered' : 'waiting'}</span>
                    </div>
                  </div>
                  {status === 'done' && (
                    <button
                      onClick={goToOutput}
                      className="mt-3 w-full border border-accent bg-accent text-white rounded-lg py-2 text-sm hover:bg-accentHover"
                    >
                      Open Output Page
                    </button>
                  )}
                </div>
                <div className="bg-white border border-border rounded-xl p-4">
                  <h3 className="text-sm font-semibold mb-2">Session</h3>
                  <div className="text-xs text-zinc-600 space-y-2">
                    <div className="flex items-center justify-between">
                      <span>Narration</span>
                      <span className="font-medium">{narrationChoice}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Project</span>
                      <span className="font-medium truncate max-w-[170px] text-right">{projectName}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Episode</span>
                      <span className="font-medium truncate max-w-[170px] text-right">{activeUnitName || 'Episode'}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </main>
      </div>

      <footer className="h-[128px] bg-white border-t border-border px-5 py-3">
        <div className="h-full grid grid-cols-[auto_1fr_220px] items-center gap-2">
          <div>
            <p className="text-xs uppercase tracking-wider text-zinc-500">Play</p>
            <div className="mt-2 flex items-center gap-2">
              <button
                onClick={() => wavesurferRef.current?.playPause()}
                disabled={!audioReady}
                  className="w-11 h-11 rounded-full border border-border flex items-center justify-center hover:bg-surfaceHover disabled:opacity-40"
              >
                {isPlaying ? <Pause size={18} /> : <Play size={18} className="ml-0.5" />}
              </button>
            </div>
          </div>

          <div className="space-y-1 min-w-0">
            {!audioReady && (
              <div className="h-[58px] rounded-lg border border-dashed border-border bg-surfaceHover flex items-center px-3 text-xs text-textMuted">
                <FileAudio size={14} className="mr-2 shrink-0" />
                Run Stage 2 to generate output waveform.
              </div>
            )}
            <div className={`w-full h-4 text-[10px] text-zinc-500 flex items-center justify-between px-1 ${audioReady ? '' : 'opacity-40'}`}>
              {timelineTicks.map((tick, idx) => (
                <span key={`${tick}-${idx}`}>{tick}</span>
              ))}
            </div>
            <div ref={waveformRef} className={`w-full min-h-[58px] ${audioReady ? '' : 'opacity-40 pointer-events-none'}`} />
          </div>

          <div className="text-right">
            <p className="text-xs uppercase tracking-wider text-zinc-500">Time</p>
            <p className="text-lg font-semibold">
              {formatClock(currentTime)} <span className="text-zinc-500">/ {formatClockTotal(duration)}</span>
            </p>
            {status === 'done' && (
              <p className="text-xs text-emerald-700 mt-1 inline-flex items-center gap-1">
                <CheckCircle2 size={12} />
                Render complete
              </p>
            )}
          </div>
        </div>
      </footer>
    </div>
  );
}
