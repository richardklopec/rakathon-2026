// Who is working at this computer: shown in the header, sent with every change for the change log (X-Actor).
// Kept in localStorage so it survives a reload; there is no login in the hackathon version.
import { useSyncExternalStore } from 'react'
import { setActor } from './api'

const KEY = 'ainor.user'
const listeners = new Set<() => void>()

function load(): string {
  try {
    return localStorage.getItem(KEY) ?? ''
  } catch {
    return '' // storage blocked (private window): name lives only in memory
  }
}

let current = load()
setActor(current)

export const getUser = () => current

export function setUser(name: string) {
  current = name.trim()
  try {
    localStorage.setItem(KEY, current)
  } catch {
    /* not persisted */
  }
  setActor(current)
  listeners.forEach((l) => l())
}

export function useUser(): string {
  return useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => listeners.delete(cb) },
    () => current,
  )
}
