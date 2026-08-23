import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function ProtectedRoute({ children }) {
  const { user } = useAuth();

  if (!user) {
    // Redirect them to the sign-in page, but save the current location they were trying to go to
    return <Navigate to="/signin" replace />;
  }

  return children;
}
