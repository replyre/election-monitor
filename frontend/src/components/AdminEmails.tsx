import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { ErrorState, Loading } from './States'
import { api, type AdminEntry } from '../lib/api'
import { dateShort } from '../lib/format'

/** The admin allow-list. An email here, once Cloudflare Access has proved it,
 *  signs in to the admin address with read and write access. */
export default function AdminEmails({ selfId }: { selfId: number | undefined }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')

  const list = useQuery<{ admins: AdminEntry[] }>({
    queryKey: ['admins'], queryFn: () => api.get('/admins'),
  })
  const refresh = () => void client.invalidateQueries({ queryKey: ['admins'] })
  const add = useMutation({
    mutationFn: () => api.post('/admins', { email, name }),
    onSuccess: () => {
      setEmail('')
      setName('')
      refresh()
    },
  })
  const remove = useMutation({
    mutationFn: (userId: number) => api.delete(`/admins/${userId}`),
    onSuccess: refresh,
  })

  if (list.isLoading) return <Loading />
  if (list.isError) return <ErrorState error={list.error} onRetry={() => void list.refetch()} />
  const active = (list.data?.admins ?? []).filter((a) => a.is_active)

  return (
    <section className="card space-y-3">
      <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{t('admins.explain')}</p>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-2xs" style={{ color: 'var(--text-muted)' }}>
            <th className="py-1">{t('admins.email')}</th>
            <th className="py-1">{t('admins.name')}</th>
            <th className="py-1">{t('admins.lastSignIn')}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {active.map((a) => (
            <tr key={a.user_id} className="border-t" style={{ borderColor: 'var(--gridline)' }}>
              <td className="py-1.5">{a.email}</td>
              <td className="py-1.5">{a.name}</td>
              <td className="py-1.5">{a.last_login_at ? dateShort(a.last_login_at) : '—'}</td>
              <td className="py-1.5 text-right">
                {a.user_id !== selfId && (
                  <button className="btn text-2xs" disabled={remove.isPending}
                          onClick={() => {
                            if (window.confirm(t('admins.confirmRemove', { email: a.email }))) {
                              remove.mutate(a.user_id)
                            }
                          }}>
                    {t('admins.remove')}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {remove.isError && <p className="text-sm text-red-600">{String(remove.error.message)}</p>}

      <form className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              add.mutate()
            }}>
        <label className="text-2xs">
          {t('admins.email')}
          <input className="input block" type="email" required maxLength={254} value={email}
                 onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="text-2xs">
          {t('admins.name')}
          <input className="input block" required maxLength={80} value={name}
                 onChange={(e) => setName(e.target.value)} />
        </label>
        <button className="btn btn-primary" type="submit" disabled={add.isPending}>
          {t('admins.add')}
        </button>
      </form>
      {add.isError && <p className="text-sm text-red-600">{String(add.error.message)}</p>}
    </section>
  )
}
