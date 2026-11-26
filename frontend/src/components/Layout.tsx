import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import AcSwitcher from './AcSwitcher'
import NavMenu from './NavMenu'
import type { NavItem } from './NavMenu'
import ThemeToggle from './ThemeToggle'
import type { AcState } from '../lib/ac'
import type { Me } from '../lib/api'

interface Props {
  me?: Me
  ac: AcState
  /** The Access-protected admin address; null when none is configured. */
  adminUrl: string | null
  /** True on the admin hostname, where the account link signs out. */
  adminHost: boolean
  children: React.ReactNode
}

/** There is no login form: public visitors get a link to the admin address,
 *  where Cloudflare Access asks for the email; admins get Access's sign-out. */
function AccountLink({ adminUrl, adminHost, className }:
  { adminUrl: string | null; adminHost: boolean; className: string }) {
  const { t } = useTranslation()
  if (adminHost) {
    return <a className={className} href="/cdn-cgi/access/logout">{t('common.signOut')}</a>
  }
  if (!adminUrl) return null
  return <a className={className} href={adminUrl}>{t('common.adminSignIn')}</a>
}

export default function Layout({ me, ac, adminUrl, adminHost, children }: Props) {
  const { t, i18n } = useTranslation()
  const [navOpen, setNavOpen] = useState(false)

  // Item 8. Seventeen flat links filled the header and wrapped onto a second
  // row, so the page title competed with the navigation and no link had any
  // visible relationship to any other. Five groups, plus Overview kept as a
  // direct link because it is the landing page and burying it behind a menu
  // would add a click to the most common destination.
  //
  // The caste pages are still gated on `sees_caste` and Admin on the admin
  // role: a group whose every item is hidden renders nothing at all, rather
  // than an empty menu that opens onto a blank panel.
  const analyst = me?.role === 'admin' || me?.role === 'strategist'
  const groups: Array<{ id: string; key: string; items: NavItem[] }> = [
    {
      id: 'nav-results',
      key: 'groupResults',
      items: [
        { to: '/results', key: 'results' },
        { to: '/booths', key: 'booths' },
        { to: '/map', key: 'map' },
      ],
    },
    {
      id: 'nav-voters',
      key: 'groupVoters',
      items: [
        { to: '/voters', key: 'voters' },
        ...(me?.sees_caste
          ? [{ to: '/caste', key: 'caste' }, { to: '/caste-scatter', key: 'casteScatter' }]
          : []),
      ],
    },
    {
      id: 'nav-places',
      key: 'groupPlaces',
      items: [{ to: '/directory', key: 'directory' }],
    },
    {
      id: 'nav-politics',
      key: 'groupPolitics',
      items: [
        { to: '/candidates', key: 'candidates' },
        { to: '/local-politics', key: 'localPolitics' },
        { to: '/local', key: 'local' },
        { to: '/news', key: 'news' },
      ],
    },
    {
      id: 'nav-analysis',
      key: 'groupAnalysis',
      items: [
        // Transfer and Scenario are admin/strategist routes in the API; a
        // block user who followed these links got a 403 page.
        ...(analyst ? [{ to: '/transfer', key: 'transfer' }] : []),
        { to: '/factors', key: 'factors' },
        { to: '/compare', key: 'compare' },
        ...(analyst ? [{ to: '/scenario', key: 'scenario' }] : []),
      ],
    },
    ...(me?.role === 'admin'
      ? [{ id: 'nav-admin', key: 'groupAdmin', items: [{ to: '/admin', key: 'admin' }] }]
      : []),
  ].filter((group) => group.items.length > 0)

  /** Every link, flattened - the narrow-screen sheet lists them all rather
   *  than nesting menus inside a menu. */
  const links: NavItem[] = [
    { to: '/', key: 'overview' },
    ...groups.flatMap((group) => group.items),
  ]

  const toggleLanguage = () => void i18n.changeLanguage(i18n.language === 'hi' ? 'en' : 'hi')

  return (
    <div className="min-h-screen">
      <header
        className="sticky top-0 z-30 border-b"
        style={{ background: 'var(--surface-1)', borderColor: 'var(--gridline)' }}
      >
        <div className="mx-auto flex max-w-[1600px] items-center gap-3 px-4 py-2.5">
          <button
            className="btn px-2 py-1 md:hidden"
            onClick={() => setNavOpen((v) => !v)}
            aria-label={t('nav.menu')}
            aria-expanded={navOpen}
          >
            ☰
          </button>
          {/* Item 7. This read "Giridih Monitor" with the constituency name
              beneath it, which was wrong twice over: the product serves six
              constituencies, and the one in view is the switcher's job to
              state. Two places naming the constituency meant one of them was
              always about to disagree with the other. */}
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{t('app.platform')}</div>
          </div>

          <nav className="ml-4 hidden flex-1 flex-wrap items-center gap-0.5 md:flex"
               aria-label={t('nav.label')}>
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                `rounded-lg px-2.5 py-1.5 text-sm transition-colors ${
                  isActive ? 'font-semibold' : ''
                }`
              }
              style={({ isActive }) => ({
                background: isActive ? 'var(--surface-2)' : 'transparent',
                color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
              })}
            >
              {t('nav.overview')}
            </NavLink>
            {groups.map((group) => (
              <NavMenu
                key={group.id}
                id={group.id}
                label={t(`nav.${group.key}`)}
                items={group.items}
              />
            ))}
            {/* The field-team screens are a separate app at /field/. */}
            <a href="/field/" className="rounded-lg px-2.5 py-1.5 text-sm"
               style={{ color: 'var(--text-secondary)' }}>
              {t('nav.field')}
            </a>
          </nav>

          <div className="ml-auto flex items-center gap-1.5">
            <AcSwitcher state={ac} />
            <button className="btn px-2 py-1 text-2xs" onClick={toggleLanguage}>
              {t('common.language')}
            </button>
            <ThemeToggle />
            <div className="hidden items-center gap-1.5 sm:flex">
              {me && me.role !== 'public' && (
                <span className="chip" title={me.role}>
                  {me.name}
                </span>
              )}
              <AccountLink adminUrl={adminUrl} adminHost={adminHost}
                           className="btn px-2 py-1 text-2xs" />
            </div>
          </div>
        </div>

        {navOpen && (
          <nav className="flex flex-wrap gap-1 border-t px-4 py-2 md:hidden"
               style={{ borderColor: 'var(--gridline)' }}>
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.to === '/'}
                onClick={() => setNavOpen(false)}
                className="rounded-lg px-2.5 py-1.5 text-sm"
                style={{ color: 'var(--text-secondary)' }}
              >
                {t(`nav.${link.key}`)}
              </NavLink>
            ))}
            <a href="/field/" className="rounded-lg px-2.5 py-1.5 text-sm"
               style={{ color: 'var(--text-secondary)' }}>
              {t('nav.field')}
            </a>
            {/* The header's account link is hidden below 640 px, the width
                field staff use on their phones, so it is repeated here. */}
            <AccountLink adminUrl={adminUrl} adminHost={adminHost}
                         className="btn ml-auto px-2.5 py-1.5 text-sm" />
          </nav>
        )}
      </header>

      <div className="mx-auto flex max-w-[1600px] gap-4 px-4 py-4">
        <main className="min-w-0 flex-1">{children}</main>
      </div>

      <footer
        className="mx-auto max-w-[1600px] px-4 pb-6 pt-2 text-2xs"
        style={{ color: 'var(--text-muted)' }}
      >
        Community figures are estimates with confidence scores, not facts. No individual voter
        records are held. Review every figure for accuracy and completeness before relying on it.
      </footer>
    </div>
  )
}
