// Hash routing (#/hlaseni, #/vytezovani/<id>, ...): no server config needed, links and the back button work.
import { useEffect, useState } from 'react'

export type TabId = 'domu' | 'hlaseni' | 'relaps' | 'novy' | 'ciselniky' | 'vytezovani' | 'dokumentace'

export interface Route {
  tab: TabId
  id: string | null // case id for #/vytezovani/<id> and #/relaps/<id>
  query: URLSearchParams
}

const TAB_IDS: TabId[] = ['domu', 'hlaseni', 'relaps', 'novy', 'ciselniky', 'vytezovani', 'dokumentace']

export function parse(hash: string): Route {
  const [path, qs = ''] = hash.replace(/^#\/?/, '').split('?')
  const [tab, id] = path.split('/')
  return {
    tab: TAB_IDS.includes(tab as TabId) ? (tab as TabId) : 'domu',
    id: id ? decodeURIComponent(id) : null,
    query: new URLSearchParams(qs),
  }
}

export const href = (tab: TabId, id?: string | null, query?: Record<string, string>) =>
  `#/${tab}${id ? `/${encodeURIComponent(id)}` : ''}${query ? `?${new URLSearchParams(query)}` : ''}`

export const go = (tab: TabId, id?: string | null, query?: Record<string, string>) => {
  location.hash = href(tab, id, query)
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(location.hash))
  useEffect(() => {
    const onHash = () => {
      setRoute(parse(location.hash))
      window.scrollTo({ top: 0 })
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  return route
}
