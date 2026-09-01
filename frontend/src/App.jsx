import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import CreateProject from './pages/CreateProject';
import ProvideStory from './pages/ProvideStory';
import StoryAnalysis from './pages/StoryAnalysis';
import PlaceAssets from './pages/PlaceAssets';
import Output from './pages/Output';
import AudioDramaDashboard from './pages/AudioDramaDashboard';
import Home from './pages/Home';
import Profile from './pages/Profile';
import SignIn from './pages/SignIn';
import SignUp from './pages/SignUp';
import ProjectDetails from './pages/ProjectDetails';
import { AuthProvider } from './contexts/AuthProvider';
import ProtectedRoute from './components/ProtectedRoute';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Routes */}
          <Route path="/" element={<Home />} />
          <Route path="/signin" element={<SignIn />} />
          <Route path="/signup" element={<SignUp />} />

          {/* Protected Routes */}
          <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
          <Route path="/project/:projectId" element={<ProtectedRoute><ProjectDetails /></ProtectedRoute>} />
          <Route path="/new" element={<ProtectedRoute><CreateProject /></ProtectedRoute>} />
          <Route path="/projects/:id/story" element={<ProtectedRoute><ProvideStory /></ProtectedRoute>} />
          <Route path="/projects/:id/drama-dashboard" element={<ProtectedRoute><AudioDramaDashboard /></ProtectedRoute>} />
          <Route path="/projects/:id/analysis" element={<ProtectedRoute><StoryAnalysis /></ProtectedRoute>} />
          <Route path="/projects/:id/assets" element={<ProtectedRoute><PlaceAssets /></ProtectedRoute>} />
          <Route path="/projects/:id/output" element={<ProtectedRoute><Output /></ProtectedRoute>} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;