import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import ProtectedRoute from './ProtectedRoute'

// Control what useAuth() returns per test.
const useAuthMock = vi.fn()
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => useAuthMock(),
}))

function renderGuarded() {
  return render(
    <MemoryRouter initialEntries={['/private']}>
      <Routes>
        <Route
          path="/private"
          element={
            <ProtectedRoute>
              <div>secret content</div>
            </ProtectedRoute>
          }
        />
        <Route path="/signin" element={<div>sign in page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProtectedRoute', () => {
  it('renders children when a user is authenticated', () => {
    useAuthMock.mockReturnValue({ user: { id: 'u1' } })

    renderGuarded()

    expect(screen.getByText('secret content')).toBeInTheDocument()
    expect(screen.queryByText('sign in page')).not.toBeInTheDocument()
  })

  it('redirects to /signin when unauthenticated', () => {
    useAuthMock.mockReturnValue({ user: null })

    renderGuarded()

    expect(screen.getByText('sign in page')).toBeInTheDocument()
    expect(screen.queryByText('secret content')).not.toBeInTheDocument()
  })
})
