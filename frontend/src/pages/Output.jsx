import React, { useEffect, useRef, useState } from 'react';
import { useParams, useLocation, Link } from 'react-router-dom';
import TopBar from '../components/TopBar';
import WaveSurfer from 'wavesurfer.js';
import { CheckCircle2, Play, Pause, Download, Volume2, ArrowRight, ArrowLeft } from 'lucide-react';
import { api } from '../api';

export default function Output() {
  const { id } = useParams();
  const location = useLocation();
  const projectName = location.state?.projectName || `Project ${id}`;
  const unitName = location.state?.unitName;
  const unitId = location.state?.unitId || '';
  const displayProjectName = unitName ? `${projectName} - ${unitName}` : projectName;
  const format = location.state?.format || 'drama';

  const waveformRef = useRef(null);
  const wavesurfer = useRef(null);
  const serverOutputDurationRef = useRef(null);
  
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [audioUrl, setAudioUrl] = useState('');
  const [error, setError] = useState('');
  const [isDownloading, setIsDownloading] = useState(false);
  const [trackSummary, setTrackSummary] = useState({
    voice: 0,
    music: 0,
    ambience: 0,
    sfx: 0,
  });

  useEffect(() => {
    if (waveformRef.current && audioUrl) {
      wavesurfer.current = WaveSurfer.create({
        container: waveformRef.current,
        waveColor: 'rgba(139, 92, 246, 0.4)', // violet-500 with opacity
        progressColor: '#a855f7', // purple-500
        cursorColor: '#f0abfc', // fuchsia-300
        barWidth: 3,
        barGap: 3,
        barRadius: 3,
        height: 100,
        normalize: true,
      });

      wavesurfer.current.load(audioUrl);

      wavesurfer.current.on('ready', () => {
        const decoded = wavesurfer.current.getDuration();
        const srv = serverOutputDurationRef.current;
        const merged =
          typeof srv === 'number' && Number.isFinite(srv) && srv > 0 ? Math.max(decoded, srv) : decoded;
        setDuration(merged);
      });
      wavesurfer.current.on('audioprocess', () => setCurrentTime(wavesurfer.current.getCurrentTime()));
      wavesurfer.current.on('play', () => setIsPlaying(true));
      wavesurfer.current.on('pause', () => setIsPlaying(false));
      wavesurfer.current.on('finish', () => setIsPlaying(false));
    }

    return () => wavesurfer.current?.destroy();
  }, [audioUrl]);

  useEffect(() => {
    let active = true;
    let createdBlobUrl = null;

    api
      .getRequirements(id)
      .then((res) => {
        if (!active) return;
        const next = { voice: 0, music: 0, ambience: 0, sfx: 0 };
        for (const item of (res?.items || [])) {
          const kind = item.asset_kind;
          if (Object.prototype.hasOwnProperty.call(next, kind)) {
            next[kind] += 1;
          }
        }
        setTrackSummary(next);
      })
      .catch(() => {
        if (!active) return;
        setTrackSummary({ voice: 0, music: 0, ambience: 0, sfx: 0 });
      });

    api
      .getOutputAudioBlobUrl(id, unitId, unitName || '')
      .then((result) => {
        if (!active) {
          if (result?.blobUrl) {
            URL.revokeObjectURL(result.blobUrl);
          }
          return;
        }
        if (result?.blobUrl) {
          serverOutputDurationRef.current =
            typeof result.durationSeconds === 'number' &&
            Number.isFinite(result.durationSeconds) &&
            result.durationSeconds > 0
              ? result.durationSeconds
              : null;
          createdBlobUrl = result.blobUrl;
          setAudioUrl(result.blobUrl);
        } else {
          serverOutputDurationRef.current = result?.durationSeconds ?? null;
          setError('Output is not ready yet.');
        }
      })
      .catch((err) => {
        if (!active) return;
        setError(err.message || 'Failed to load output');
      });

    return () => {
      active = false;
      if (createdBlobUrl) {
        URL.revokeObjectURL(createdBlobUrl);
      }
    };
  }, [id, unitId]);

  const togglePlay = () => wavesurfer.current?.playPause();

  const handleVolumeChange = (e) => {
    const val = parseFloat(e.target.value);
    setVolume(val);
    wavesurfer.current?.setVolume(val);
  };

  const formatTime = (secs) => {
    const minutes = Math.floor(secs / 60);
    const seconds = Math.floor(secs % 60);
    return `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
  };

  const formatTimeTotal = (secs) => {
    if (!Number.isFinite(secs) || secs <= 0) return '0:00';
    const rounded = Math.ceil(secs - 1e-6);
    const minutes = Math.floor(rounded / 60);
    const seconds = rounded % 60;
    return `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
  };

  const handleDownload = () => {
    if (!audioUrl) return;
    setIsDownloading(true);
    try {
      const safeName = displayProjectName.replace(/[^\w-]+/g, '_');
      const link = document.createElement('a');
      link.href = audioUrl;
      link.download = `${safeName || 'project'}-master.wav`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar projectName={displayProjectName} step={4} totalSteps={4} />
      
      <main className="flex-1 max-w-3xl mx-auto w-full px-4 sm:px-6 py-16 animate-in fade-in slide-in-from-bottom-8 duration-1000">
        
        {/* Success Header */}
        <div className="text-center mb-12">
          <div className="mb-5">
            <Link
              to={`/project/${id}`}
              className="inline-flex items-center gap-2 text-sm font-semibold text-zinc-600 hover:text-zinc-900 transition-colors"
            >
              <ArrowLeft size={16} /> Back to Chapters
            </Link>
          </div>
          <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-violet-500/10 border border-violet-500/30 mb-6 relative">
            <div className="absolute inset-0 bg-violet-500/20 rounded-full animate-ping opacity-75"></div>
            <CheckCircle2 className="w-12 h-12 text-violet-400 drop-shadow-sm relative z-10" />
          </div>
          <h1 className="text-4xl font-extrabold text-zinc-900 tracking-tight mb-4">Master Audio Ready</h1>
          <div className="inline-flex items-center gap-3 bg-white/60 border border-zinc-200 px-5 py-2.5 rounded-full backdrop-blur-md">
            <span className="font-bold text-zinc-900 tracking-wide">{displayProjectName}</span>
            <span className="w-1.5 h-1.5 rounded-full bg-zinc-600"></span>
            <span className="text-violet-800 font-medium uppercase tracking-wider text-xs">{format === 'drama' ? 'Audio Drama' : 'Audio Book'}</span>
            <span className="w-1.5 h-1.5 rounded-full bg-zinc-600"></span>
            <span className="font-mono text-violet-400 font-bold">{duration > 0 ? formatTimeTotal(duration) : '--:--'}</span>
          </div>
        </div>

        {/* Waveform Player */}
        <div className="card p-8 mb-10 border-violet-500/30 bg-white shadow-[0_20px_50px_rgba(124,58,237,0.15)] relative overflow-hidden">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-64 h-32 bg-violet-500/20 blur-[50px] rounded-full pointer-events-none"></div>
          
          <div ref={waveformRef} className="w-full mb-8 cursor-pointer relative z-10" />
          
          <div className="flex flex-col sm:flex-row items-center justify-between gap-6 relative z-10">
            <div className="flex items-center gap-6">
              <button 
                onClick={togglePlay}
                className="w-16 h-16 flex items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-violet-600 text-zinc-900 hover:from-violet-400 hover:to-violet-500 shadow-sm transition-all hover:scale-105 active:scale-95"
              >
                {isPlaying ? <Pause size={28} className="fill-current" /> : <Play size={28} className="fill-current ml-1.5" />}
              </button>
              <div className="font-mono text-2xl text-zinc-600 font-medium">
                <span className="text-zinc-900 drop-shadow-md">{formatTime(currentTime)}</span> 
                <span className="mx-2 text-zinc-600">/</span> 
                <span>{formatTimeTotal(duration)}</span>
              </div>
            </div>

            <div className="flex items-center gap-3 w-40 bg-violet-600/40 px-4 py-2.5 rounded-2xl border border-zinc-200 backdrop-blur-md">
              <Volume2 size={20} className={`transition-colors ${volume === 0 ? 'text-zinc-600' : 'text-violet-400'}`} />
              <input 
                type="range" 
                min="0" 
                max="1" 
                step="0.05"
                value={volume}
                onChange={handleVolumeChange}
                className="w-full accent-violet-500 h-1.5 bg-white rounded-lg appearance-none cursor-pointer"
              />
            </div>
          </div>
        </div>
        {error && <p className="text-red-400 text-sm mb-6 text-center">{error}</p>}

        {/* Track Summary & Download Info Grid */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-6 mb-12">
          {/* Summary */}
          <div className="md:col-span-3 grid grid-cols-2 gap-4">
            {[
              { label: 'Narrator', color: 'bg-rose-500', count: trackSummary.voice },
              { label: 'Music', color: 'bg-violet-500', count: trackSummary.music },
              { label: 'Ambience', color: 'bg-violet-500', count: trackSummary.ambience },
              { label: 'SFX', color: 'bg-amber-500', count: trackSummary.sfx },
            ].map((track, i) => (
              <div key={i} className="bg-white/40 border border-zinc-200 py-4 px-5 rounded-2xl backdrop-blur-sm hover:bg-white transition-colors">
                <div className="flex items-center gap-2.5 text-sm font-bold text-zinc-900 mb-1.5 tracking-wide">
                  <div className={`w-2.5 h-2.5 rounded-full ${track.color} shadow-[0_0_10px_currentColor]`}></div> {track.label}
                </div>
                <div className="text-sm font-mono text-zinc-600">{track.count} CLIPS</div>
              </div>
            ))}
          </div>
          
          {/* Download Action */}
          <div className="md:col-span-2 bg-gradient-to-br from-zinc-900/80 to-black/80 border border-zinc-200 rounded-2xl p-6 flex flex-col justify-center items-center backdrop-blur-sm relative overflow-hidden group">
            <div className="absolute inset-0 bg-violet-600/10 opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
            <button onClick={handleDownload} disabled={!audioUrl || isDownloading} className="btn-primary w-full py-4 shadow-[0_10px_30px_rgba(124,58,237,0.3)] hover:-translate-y-1 z-10 disabled:opacity-50 disabled:cursor-not-allowed">
              <Download size={20} className="mr-3" /> {isDownloading ? 'Preparing Download...' : 'Download WAV'}
            </button>
            <div className="mt-4 flex flex-wrap justify-center gap-2 z-10">
              {['48kHz', '16-bit', 'Stereo', '-20 LUFS'].map(tag => (
                <span key={tag} className="text-[10px] font-mono text-zinc-600 bg-white border border-zinc-200 px-2 py-1 rounded">
                  {tag}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="text-center pb-12">
          <Link to="/new" className="inline-flex items-center gap-2 text-sm font-bold text-zinc-600 hover:text-zinc-900 transition-colors py-3 px-6 rounded-full hover:bg-white">
            CREATE ANOTHER PROJECT <ArrowRight size={16} />
          </Link>
        </div>

      </main>
    </div>
  );
}
