import { createContext, useContext } from 'react';

// The context and its hook live in this file, apart from the provider in
// AuthProvider.jsx, so that neither file exports both a component and a
// non-component. Mixing the two breaks Vite's Fast Refresh, which can only
// hot-swap a module whose exports are all components
// (eslint react-refresh/only-export-components).
export const AuthContext = createContext({});

export const useAuth = () => {
  return useContext(AuthContext);
};
