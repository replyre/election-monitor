import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import App from './App'
import { CONFIG } from './fixtures'
import { mockServer, signIn } from './test/server'
import { renderWithProviders } from './test/render'

const PUBLIC_ME = { user_id: 0, name: 'Public', role: 'public', block_id: null,
  sees_caste: false, daily_token_budget: 0 }
const ADMIN_ME = { user_id: 7, name: 'Admin', role: 'admin', block_id: null,
  sees_caste: true, daily_token_budget: 0 }

/** The page is served from the admin address when admin_url is this origin. */
const onAdminSite = { ...CONFIG, admin_url: window.location.origin }
const onPublicSite = { ...CONFIG, admin_url: 'https://admin.example.org' }

/**
 * The app shell. There is no login screen: everyone reads the site as the
 * public viewer, and on the admin address the Cloudflare Access sign-in is
 * exchanged for an app token.
 */
describe('App', () => {
  it('lets a visitor read the dashboard without signing in', async () => {
    const server = mockServer({ '/config': { body: onPublicSite }, '/auth/me': { body: PUBLIC_ME } })
    renderWithProviders(<App />)

    const admin = await screen.findAllByRole('link', { name: 'Admin' })
    expect(admin[0]).toHaveAttribute('href', 'https://admin.example.org')
    expect(screen.queryByRole('link', { name: 'Sign out' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
    await waitFor(() => expect(server.calls.some((c) => c.path === '/acs/32/summary')).toBe(true))
    expect(server.calls.some((c) => c.path === '/auth/access')).toBe(false)
  })

  it('drops a token left by an earlier build on the public address', async () => {
    const server = mockServer({ '/config': { body: onPublicSite }, '/auth/me': { body: PUBLIC_ME } })
    signIn(server)
    server.on('/auth/me', { body: PUBLIC_ME })
    renderWithProviders(<App />)

    await waitFor(() => expect(localStorage.getItem('giridih.token')).toBeNull())
  })

  it('signs an admin in on the admin address with no form', async () => {
    const server = mockServer({
      '/config': { body: onAdminSite },
      'POST /auth/access': {
        body: { access_token: 'admin-tok', role: 'admin', name: 'Admin', block_id: null },
      },
      '/auth/me': { body: ADMIN_ME },
    })
    localStorage.removeItem('giridih.token')
    renderWithProviders(<App />)

    expect((await screen.findAllByRole('link', { name: 'Sign out' }))[0])
      .toHaveAttribute('href', '/cdn-cgi/access/logout')
    expect(localStorage.getItem('giridih.token')).toBe('admin-tok')
    expect(server.calls.filter((c) => c.path === '/auth/access')).toHaveLength(1)
  })

  it('tells a signed-in email without admin access so, and how to switch', async () => {
    mockServer({
      '/config': { body: onAdminSite },
      'POST /auth/access': { status: 403, body: { detail: 'This email does not have admin access' } },
    })
    localStorage.removeItem('giridih.token')
    renderWithProviders(<App />)

    expect(await screen.findByText('This email does not have admin access')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign in with another email' }))
      .toHaveAttribute('href', '/cdn-cgi/access/logout')
  })

  it('exchanges again when an admin token expires, rather than showing a form', async () => {
    const server = mockServer({
      '/config': { body: onAdminSite },
      'POST /auth/access': {
        body: { access_token: 'fresh', role: 'admin', name: 'Admin', block_id: null },
      },
      '/auth/me': { body: ADMIN_ME },
    })
    localStorage.setItem('giridih.token', 'stale')
    server.on('/acs/32/summary', (_url, init) => {
      const auth = new Headers(init?.headers).get('Authorization')
      return auth === 'Bearer stale' ? { status: 401, body: { detail: 'expired' } } : { body: {} }
    })
    renderWithProviders(<App />)

    await waitFor(() => expect(localStorage.getItem('giridih.token')).toBe('fresh'))
    expect(server.calls.some((c) => c.path === '/auth/access')).toBe(true)
  })

  it('shows an error, not an endless spinner, when /config cannot be loaded', async () => {
    mockServer({ '/config': { status: 500, body: { detail: 'boom' } } })
    renderWithProviders(<App />)

    await waitFor(() =>
      expect(screen.getByText(/could not load the list of constituencies/i)).toBeInTheDocument())
  })
})
