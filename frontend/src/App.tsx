import { lazy, Suspense, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import ErrorBoundary from './components/ErrorBoundary'
import Layout from './components/Layout'
import { ErrorState, Loading } from './components/States'
import { useAc } from './lib/ac'
import {
  ApiError, exchangeAccess, getConfig, getMe, getToken, onAdminHost, setSession,
  type AppConfig, type Me,
} from './lib/api'
import { useTranslation } from 'react-i18next'

// Overview is the landing page for everyone: start its (charts-heavy) chunk at
// once rather than after the config and role round trips.
const loadOverview = () => import('./pages/Overview')
void loadOverview()
const Overview = lazy(loadOverview)
const MapExplorer = lazy(() => import('./pages/MapExplorer'))
const Results = lazy(() => import('./pages/Results'))
const Voters = lazy(() => import('./pages/Voters'))
const Caste = lazy(() => import('./pages/Caste'))
const Transfer = lazy(() => import('./pages/Transfer'))
const LocalPolls = lazy(() => import('./pages/LocalPolls'))
const News = lazy(() => import('./pages/News'))
const Factors = lazy(() => import('./pages/Factors'))
const Scenario = lazy(() => import('./pages/Scenario'))
const Admin = lazy(() => import('./pages/Admin'))
const Compare = lazy(() => import('./pages/Compare'))
const Booths = lazy(() => import('./pages/Booths'))
const CasteScatter = lazy(() => import('./pages/CasteScatter'))
const Candidates = lazy(() => import('./pages/Candidates'))
const LocalPolitics = lazy(() => import('./pages/LocalPolitics'))
const Directory = lazy(() => import('./pages/Directory'))

/** Where the admin sign-in stands. Public visitors never leave 'none'. */
type Access = 'none' | 'pending' | 'ok' | 'denied'

export default function App() {
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const location = useLocation()

  /** Constituency list and the admin address, fetched once: they only change
   *  when the server restarts. */
  const config = useQuery<AppConfig>({
    queryKey: ['config'],
    queryFn: getConfig,
    staleTime: Infinity,
    retry: false,
  })

  // There is no login screen. Everyone reads the site as the public viewer;
  // on the admin hostname Cloudflare Access has already checked the email, and
  // that sign-in is traded for an app token here, again whenever it expires.
  const adminHost = onAdminHost(config.data)
  const [access, setAccess] = useState<Access>(() => (getToken() ? 'ok' : 'none'))
  const [denied, setDenied] = useState<string | null>(null)

  useEffect(() => {
    if (!config.data) return
    if (!adminHost) {
      // A token from an earlier build of this origin must not outlive it.
      if (getToken()) setSession(null)
      setAccess('none')
      return
    }
    if (access !== 'none') return
    setAccess('pending')
    exchangeAccess()
      .then(() => {
        setAccess('ok')
        void queryClient.invalidateQueries({ queryKey: ['me'] })
      })
      .catch((error: unknown) => {
        setDenied(error instanceof ApiError ? error.message : String(error))
        setAccess('denied')
      })
  }, [config.data, adminHost, access, queryClient])

  // An expired admin token: drop cached data and exchange again.
  useEffect(() => {
    const onUnauthorised = () => {
      queryClient.clear()
      setAccess('none')
    }
    window.addEventListener('giridih:unauthorised', onUnauthorised)
    return () => window.removeEventListener('giridih:unauthorised', onUnauthorised)
  }, [queryClient])

  const me = useQuery<Me>({
    queryKey: ['me', access],
    queryFn: getMe,
    enabled: config.isSuccess && (!adminHost || access === 'ok'),
  })

  /** Selected constituency: ?ac= in the URL, then localStorage, then the first
   *  AC /config lists. Every page takes it so nothing can query unscoped.
   *
   *  Called before the signed-out early return, never after it: hooks must run
   *  in the same order on every render. It once sat below an early return,
   *  so signing in through the form, signing out, or any 401 changed the hook
   *  count between renders and React unmounted the whole tree - a blank page. */
  const ac = useAc(config.data)

  const adminUrl = config.data?.admin_url ?? null

  // /config is fetched once with retry off; on failure there is no AC list and
  // every page would wait on it forever. Say so instead.
  if (config.isError) {
    return (
      <Layout me={me.data} ac={ac} adminUrl={adminUrl} adminHost={adminHost}>
        <ErrorState error={new Error(t('common.configFailed'))} onRetry={() => void config.refetch()} />
      </Layout>
    )
  }

  // N14. The role-gated routes below are registered conditionally, and the
  // catch-all redirects anything unmatched to "/". So a direct navigation to
  // /admin - typing it, a bookmark, a hard refresh - arrived before `me`
  // resolved, matched nothing, and bounced to the Overview. It looked like the
  // page did not exist. Holding the route table until the role is known is
  // enough; the query is already in flight and takes one round trip.
  // Admin and strategist only, matching the API's role checks.
  const analyst = me.data?.role === 'admin' || me.data?.role === 'strategist'

  if (adminHost && access === 'denied') {
    return (
      <Layout me={undefined} ac={ac} adminUrl={adminUrl} adminHost={adminHost}>
        <section className="card mx-auto max-w-lg space-y-3">
          <h1 className="text-base font-semibold">{t('access.deniedTitle')}</h1>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{denied}</p>
          <a className="btn" href="/cdn-cgi/access/logout">{t('access.useAnotherEmail')}</a>
        </section>
      </Layout>
    )
  }

  if (me.isLoading || (adminHost && access === 'pending')) {
    return (
      <Layout me={undefined} ac={ac} adminUrl={adminUrl} adminHost={adminHost}>
        <Loading />
      </Layout>
    )
  }

  return (
    <Layout me={me.data} ac={ac} adminUrl={adminUrl} adminHost={adminHost}>
      <ErrorBoundary resetKey={`${location.pathname}|${ac.acNumber}`}>
      <Suspense fallback={<Loading />}>
      {/* Keyed by AC: switching constituency remounts the page, so filters
          picked for one AC (a block, an area, an election) do not carry over
          and select nothing in the next. */}
      <Routes key={ac.acNumber ?? 'none'}>
        <Route
          path="/"
          element={<Overview ac={ac} isAdmin={me.data?.role === 'admin'}
                            seesCaste={Boolean(me.data?.sees_caste)} />}
        />
        <Route path="/map" element={<MapExplorer ac={ac} />} />
        <Route path="/booths" element={<Booths ac={ac} />} />
        <Route path="/results" element={<Results ac={ac} />} />
        <Route path="/results/:electionLabel" element={<Results ac={ac} />} />
        <Route path="/voters" element={<Voters ac={ac} />} />
        {me.data?.sees_caste && <Route path="/caste" element={<Caste ac={ac} />} />}
        {analyst && <Route path="/transfer" element={<Transfer ac={ac} />} />}
        <Route path="/directory" element={<Directory ac={ac} />} />
        <Route path="/local" element={<LocalPolls ac={ac} />} />
        <Route path="/news" element={<News ac={ac} />} />
        <Route path="/factors" element={<Factors ac={ac} />} />
        {analyst && <Route path="/scenario" element={<Scenario ac={ac} />} />}
        <Route path="/compare" element={<Compare />} />
        <Route path="/candidates" element={<Candidates ac={ac} />} />
        <Route path="/local-politics" element={<LocalPolitics ac={ac} />} />
        {me.data?.sees_caste && (
          <Route path="/caste-scatter" element={<CasteScatter ac={ac} />} />
        )}
        {me.data?.role === 'admin' && <Route path="/admin" element={<Admin ac={ac} selfId={me.data?.user_id} />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </Suspense>
      </ErrorBoundary>
    </Layout>
  )
}
