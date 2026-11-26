import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import Layout from './Layout'
import { fakeAc, renderWithProviders } from '../test/render'

const me = { user_id: 1, name: 'Block user', role: 'block' as const, block_id: 3202,
  sees_caste: false, daily_token_budget: 1 }
const viewer = { user_id: 0, name: 'Public', role: 'public' as const, block_id: null,
  sees_caste: false, daily_token_budget: 0 }
const site = { adminUrl: 'https://admin.example.org', adminHost: false }

describe('Layout', () => {
  it('offers the admin address, not a sign-out, to a public visitor - on phones too', async () => {
    renderWithProviders(<Layout me={viewer} ac={fakeAc(32)} {...site}>x</Layout>)
    expect(screen.queryByRole('link', { name: 'Sign out' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Menu' }))
    const sheets = screen.getAllByRole('navigation')
    expect(within(sheets[sheets.length - 1]).getByRole('link', { name: 'Admin' }))
      .toHaveAttribute('href', 'https://admin.example.org')
  })

  it('signs an admin out through Cloudflare Access', () => {
    renderWithProviders(
      <Layout me={{ ...me, role: 'admin', sees_caste: true }} ac={fakeAc(32)}
              adminUrl="https://admin.example.org" adminHost>x</Layout>)
    expect(screen.getAllByRole('link', { name: 'Sign out' })[0])
      .toHaveAttribute('href', '/cdn-cgi/access/logout')
  })

  it('shows no account link when no admin address is configured', () => {
    renderWithProviders(<Layout me={viewer} ac={fakeAc(32)} adminUrl={null} adminHost={false}>x</Layout>)
    expect(screen.queryByRole('link', { name: 'Admin' })).not.toBeInTheDocument()
  })

  it('links to the field-team screens', () => {
    renderWithProviders(<Layout me={viewer} ac={fakeAc(32)} {...site}>x</Layout>)
    expect(screen.getAllByRole('link', { name: 'Field team' })[0]).toHaveAttribute('href', '/field/')
  })

  it('hides the caste and admin menus from the public and a block user', () => {
    for (const who of [viewer, me]) {
      const { unmount } = renderWithProviders(<Layout me={who} ac={fakeAc(32)} {...site}>x</Layout>)
      expect(screen.queryByRole('button', { name: /^admin$/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('link', { name: /caste|community/i })).not.toBeInTheDocument()
      unmount()
    }
  })

  it('hides the strategist-only pages from a block user', async () => {
    renderWithProviders(<Layout me={me} ac={fakeAc(32)} {...site}>x</Layout>)
    await userEvent.click(screen.getByRole('button', { name: 'Menu' }))
    expect(screen.queryByRole('link', { name: 'LS vs VS' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Scenarios' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Compare' }).length).toBeGreaterThan(0)
  })

  it('shows them to a strategist', async () => {
    renderWithProviders(
      <Layout me={{ ...me, role: 'strategist', sees_caste: true }} ac={fakeAc(32)} {...site}>x</Layout>)
    await userEvent.click(screen.getByRole('button', { name: 'Menu' }))
    expect(screen.getAllByRole('link', { name: 'Scenarios' }).length).toBeGreaterThan(0)
  })
})
