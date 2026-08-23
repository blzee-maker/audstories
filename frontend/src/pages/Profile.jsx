import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { AudioLines, LogOut, Plus, Clock, Settings, User, Play, ChevronRight, Loader2, Trash2 } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { supabase } from '../supabase';

export default function Profile() {
  const navigate = useNavigate();
  const { user, signOut } = useAuth();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deletingProjectId, setDeletingProjectId] = useState(null);
  const [projectPendingDelete, setProjectPendingDelete] = useState(null);
  const [deleteNotice, setDeleteNotice] = useState(null);

  useEffect(() => {
    async function fetchProjects() {
      if (!user) return;
      try {
        const { data, error } = await supabase
          .from('projects')
          .select(`
            *,
            units ( count )
          `)
          .eq('user_id', user.id)
          .order('created_at', { ascending: false });

        if (error) throw error;
        
        const formattedProjects = data.map(p => ({
          id: p.id,
          name: p.name,
          format: p.format,
          count: p.units[0]?.count || 0,
          lastEdited: new Date(p.updated_at).toLocaleDateString()
        }));

        setProjects(formattedProjects);
      } catch (err) {
        console.error("Error fetching projects:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchProjects();
  }, [user]);

  const handleSignOut = async () => {
    await signOut();
    navigate('/signin');
  };

  const requestProjectDelete = (event, project) => {
    event.stopPropagation();
    setDeleteNotice(null);
    setProjectPendingDelete(project);
  };

  const confirmProjectDelete = async () => {
    if (!projectPendingDelete) return;

    const { id: projectId, name: projectName } = projectPendingDelete;

    setDeletingProjectId(projectId);
    try {
      const { error } = await supabase
        .from('projects')
        .delete()
        .eq('id', projectId)
        .eq('user_id', user.id);

      if (error) throw error;

      setProjects((currentProjects) => currentProjects.filter((project) => project.id !== projectId));
      setDeleteNotice({ type: 'success', message: `"${projectName}" was deleted.` });
      setProjectPendingDelete(null);
    } catch (err) {
      console.error("Error deleting project:", err);
      setDeleteNotice({ type: 'error', message: `Failed to delete "${projectName}". Please try again.` });
    } finally {
      setDeletingProjectId(null);
    }
  };

  return (
    <div className="min-h-screen bg-background relative overflow-hidden">
      {/* Top Bar for Profile */}
      <div className="w-full bg-surface/80 backdrop-blur-xl border-b border-border sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2 font-bold text-lg">
            <div className="w-8 h-8 rounded-lg bg-violet-600 flex items-center justify-center shadow-lg">
              <AudioLines size={18} className="text-zinc-900" />
            </div>
            <span className="text-textPrimary tracking-tight">
              Aud<span className="text-violet-900 font-bold">Stories</span>
            </span>
          </div>
          <button
            onClick={handleSignOut}
            className="flex items-center gap-2 text-sm text-textSecondary hover:text-zinc-900 transition-colors p-2 rounded-lg hover:bg-white"
          >
            <LogOut size={16} />
            Sign Out
          </button>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">

        {/* User Card */}
        <div className="card flex items-start gap-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="w-24 h-24 rounded-full bg-violet-600 p-1">
            <div className="w-full h-full bg-white rounded-full flex items-center justify-center border-4 border-surface">
              <User size={40} className="text-violet-400" />
            </div>
          </div>
          <div className="flex-1 pt-2">
            <h1 className="text-3xl font-bold text-zinc-900 mb-1 tracking-wide">Welcome, {user?.user_metadata?.username || 'Creator'}!</h1>
            <p className="text-textSecondary text-sm mb-4">{user?.email}</p>
            <div className="flex gap-3">
              <button className="text-sm px-4 py-2 rounded-lg bg-white border border-zinc-200 text-zinc-900 transition-colors flex items-center gap-2 font-medium opacity-60 cursor-not-allowed" disabled title="Profile editing coming soon">
                <Settings size={16} /> Edit Profile
              </button>
            </div>
          </div>
        </div>

        {/* Start New Project Section */}
        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 delay-150 fill-mode-both">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold text-zinc-900 tracking-wide">Quick Actions</h2>
          </div>
          <div
            onClick={() => navigate('/new')}
            className="group relative overflow-hidden bg-violet-50 hover:from-violet-600/30 hover:to-violet-600/30 border border-violet-500/30 hover:border-violet-500/50 rounded-2xl p-8 cursor-pointer transition-all duration-500 shadow-lg hover:shadow-sm"
          >
            <div className="absolute inset-0 bg-violet-600 opacity-0 group-hover:opacity-10 transition-opacity duration-500" />
            <div className="flex items-center gap-6 relative z-10">
              <div className="w-16 h-16 rounded-2xl bg-violet-500/20 flex shrink-0 items-center justify-center group-hover:scale-110 group-hover:bg-violet-500/30 transition-all duration-300">
                <Plus size={32} className="text-violet-800" />
              </div>
              <div className="flex-1">
                <h3 className="text-2xl font-bold text-zinc-900 mb-1">Create New Project</h3>
                <p className="text-violet-900/70 text-sm">Start a new audio drama or audio book production workflow.</p>
              </div>
              <div className="w-12 h-12 rounded-full bg-white flex items-center justify-center group-hover:bg-violet-500 group-hover:text-zinc-900 transition-colors duration-300">
                <ChevronRight size={24} className="text-textSecondary group-hover:text-zinc-900" />
              </div>
            </div>
          </div>
        </div>

        {/* Recent Projects area */}
        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 delay-300 fill-mode-both">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold text-zinc-900 tracking-wide">Recent Projects</h2>
            <span className="text-sm text-textSecondary font-medium">Showing all</span>
          </div>
          {deleteNotice && (
            <div
              className={`mb-4 rounded-xl border px-4 py-3 text-sm ${
                deleteNotice.type === 'error'
                  ? 'border-red-300 bg-red-50 text-red-700'
                  : 'border-emerald-300 bg-emerald-50 text-emerald-700'
              }`}
            >
              {deleteNotice.message}
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {loading ? (
              <div className="col-span-full flex justify-center py-10">
                 <Loader2 className="animate-spin text-violet-500" size={32} />
              </div>
            ) : projects.length === 0 ? (
              <div className="col-span-full text-center py-10 text-textSecondary bg-white rounded-2xl border border-zinc-200">
                <p>No projects yet. Create your first one!</p>
              </div>
            ) : projects.map((proj) => (
              <div
                key={proj.id}
                onClick={() => navigate(`/project/${proj.id}`)}
                className="card group hover:border-violet-500/30 transition-all cursor-pointer p-5 flex flex-col h-full hover:shadow-[0_4px_20px_rgba(0,0,0,0.3)] hover:-translate-y-1"
              >
                <div className="flex justify-between items-start mb-4">
                  <div className="w-10 h-10 rounded-lg bg-white/80 flex items-center justify-center group-hover:bg-violet-500/20 transition-colors">
                    <Play size={18} className="text-textSecondary group-hover:text-violet-400 transition-colors" />
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-textSecondary bg-white px-2 py-1 rounded-md border border-border capitalize">
                      {proj.format === 'drama' ? 'Audio Drama' : 'Audio Book'}
                    </span>
                    <button
                      type="button"
                      onClick={(event) => requestProjectDelete(event, proj)}
                      disabled={deletingProjectId === proj.id}
                      className="p-1.5 rounded-md border border-zinc-200 bg-white text-zinc-500 hover:text-red-600 hover:border-red-300 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                      aria-label={`Delete ${proj.name}`}
                      title={`Delete ${proj.name}`}
                    >
                      {deletingProjectId === proj.id ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Trash2 size={14} />
                      )}
                    </button>
                  </div>
                </div>
                <h3 className="text-lg font-bold text-zinc-900 mb-1 group-hover:text-violet-900 transition-colors">{proj.name}</h3>
                <p className="text-sm text-zinc-600 font-medium mb-4">{proj.count} {proj.format === 'drama' ? 'Episode' : 'Chapter'}{proj.count !== 1 ? 's' : ''}</p>
                <div className="mt-auto pt-4 border-t border-border flex items-center justify-between text-xs text-textMuted font-medium">
                  <div className="flex items-center gap-1.5">
                    <Clock size={12} /> Last edited {proj.lastEdited}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>

      {projectPendingDelete && (
        <div className="fixed inset-0 z-100 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-violet-600/60 backdrop-blur-sm" onClick={() => setProjectPendingDelete(null)} />
          <div className="card relative z-10 w-full max-w-md animate-in fade-in zoom-in-95 duration-200">
            <h3 className="text-xl font-bold text-zinc-900 mb-2 tracking-wide">Delete project?</h3>
            <p className="text-sm text-textSecondary mb-6">
              Delete "{projectPendingDelete.name}"? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setProjectPendingDelete(null)}
                className="px-5 py-2.5 rounded-xl font-medium text-zinc-600 hover:text-zinc-900 hover:bg-white transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmProjectDelete}
                disabled={deletingProjectId === projectPendingDelete.id}
                className="px-5 py-2.5 rounded-xl font-medium text-white bg-red-600 hover:bg-red-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {deletingProjectId === projectPendingDelete.id && <Loader2 size={14} className="animate-spin" />}
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
