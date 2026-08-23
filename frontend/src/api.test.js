import { describe, it, expect, vi, beforeEach } from 'vitest'

// api.js imports ./supabase, which constructs a real Supabase client and reads
// the session for the auth header. Mock it so tests are hermetic.
const getSession = vi.fn()
vi.mock('./supabase', () => ({
  supabase: { auth: { getSession: (...args) => getSession(...args) } },
}))

import { api } from './api'

function jsonResponse(body, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
    text: async () => JSON.stringify(body),
  }
}

describe('api client', () => {
  beforeEach(() => {
    getSession.mockReset()
    getSession.mockResolvedValue({ data: { session: { access_token: 'tok-123' } }, error: null })
    global.fetch = vi.fn()
  })

  it('targets the configured base URL', () => {
    expect(api.baseUrl).toBe('http://localhost:8000')
  })

  it('attaches the bearer token and JSON content-type on JSON requests', async () => {
    fetch.mockResolvedValue(jsonResponse({ id: 'p1' }))

    const res = await api.createProject({ project_id: 'p1' })

    expect(res).toEqual({ id: 'p1' })
    const [url, opts] = fetch.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/projects')
    expect(opts.method).toBe('POST')
    expect(opts.headers.get('Authorization')).toBe('Bearer tok-123')
    expect(opts.headers.get('Content-Type')).toBe('application/json')
    expect(opts.body).toBe(JSON.stringify({ project_id: 'p1' }))
  })

  it('omits the Authorization header when there is no session', async () => {
    getSession.mockResolvedValue({ data: { session: null }, error: null })
    fetch.mockResolvedValue(jsonResponse({ ok: true }))

    await api.getStatus('p1')

    const [, opts] = fetch.mock.calls[0]
    expect(opts.headers.has('Authorization')).toBe(false)
  })

  it('throws the server "detail" message on a non-ok response', async () => {
    fetch.mockResolvedValue(jsonResponse({ detail: 'bad input' }, { ok: false, status: 400 }))

    await expect(api.runStage1('p1')).rejects.toThrow('bad input')
  })

  it('falls back to a status-coded message when the error body is unparseable', async () => {
    fetch.mockResolvedValue({
      ok: false,
      status: 500,
      headers: new Headers({ 'content-type': 'text/plain' }),
      json: async () => {
        throw new Error('not json')
      },
    })

    await expect(api.runStage1('p1')).rejects.toThrow('Request failed (500)')
  })

  it('does not force a Content-Type for FormData uploads (lets the browser set the boundary)', async () => {
    fetch.mockResolvedValue(jsonResponse({ status: 'ready' }))

    const file = new File(['x'], 'clip.wav')
    await api.uploadAsset('p1', '/assets/sfx/x', file)

    const [, opts] = fetch.mock.calls[0]
    expect(opts.headers.has('Content-Type')).toBe(false)
    expect(opts.body).toBeInstanceOf(FormData)
  })

  it('cache-busts polling reads with a _ts query param', async () => {
    fetch.mockResolvedValue(jsonResponse({ items: [] }))

    await api.getRequirements('p1')

    const [url] = fetch.mock.calls[0]
    expect(url).toMatch(/\/api\/projects\/p1\/requirements\?_ts=\d+$/)
  })

  it('builds the output query string from unit params', async () => {
    fetch.mockResolvedValue(jsonResponse({}))

    await api.getOutput('p1', 'u1', 'Episode 1')

    const [url] = fetch.mock.calls[0]
    expect(url).toContain('unit_id=u1')
    expect(url).toContain('unit_name=Episode+1')
  })

  it('emits no query string for output when unit params are absent', async () => {
    fetch.mockResolvedValue(jsonResponse({}))

    await api.getOutput('p1')

    const [url] = fetch.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/projects/p1/output')
  })
})
