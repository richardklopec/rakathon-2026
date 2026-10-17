// Documentation page (button "Dokumentace" in the header). Content lives in ai-nor/docs/, edit it there.
import { useState, type ReactNode } from 'react'
import funkceRaw from '../../docs/funkce.json?raw'
import navod from '../../docs/navod.md?raw'

type Stav = 'hotovo' | 'castecne' | 'plan'
type Polozka = { nazev: string; sluzba: string; k_cemu: string; kde: string; stav: Stav }
type Kategorie = { nazev: string; polozky: Polozka[] }

const funkce = (JSON.parse(funkceRaw) as { kategorie: Kategorie[] }).kategorie

const STAV: Record<Stav, [string, string]> = {
  hotovo: ['hotovo', 'bg-green-100 text-green-800'],
  castecne: ['částečně', 'bg-amber-100 text-amber-800'],
  plan: ['plán', 'bg-slate-100 text-slate-600'],
}

const TABS = [
  ['funkce', 'Využité funkce'],
  ['navod', 'Návod pro obsluhu'],
] as const

type Tab = (typeof TABS)[number][0]

export default function Docs() {
  const [tab, setTab] = useState<Tab>('funkce')
  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="mb-4 text-xl font-semibold text-fno-950">Dokumentace</h1>
      <div className="mb-5 flex gap-1 border-b border-slate-200" role="tablist">
        {TABS.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
            className={`-mb-px border-b-[3px] px-4 py-2 text-sm font-medium transition-colors duration-150 ${tab === id ? 'border-fno-sky text-fno-900' : 'border-transparent text-slate-600 hover:text-fno-800'}`}>
            {label}
          </button>
        ))}
      </div>
      {tab === 'funkce' ? <Funkce /> : <article className="max-w-3xl rounded-lg border border-slate-200 bg-white p-6 text-slate-800">{markdown(navod)}</article>}
    </div>
  )
}

function Funkce() {
  const all = funkce.flatMap((k) => k.polozky)
  const count = (s: Stav) => all.filter((p) => p.stav === s).length
  return (
    <div className="space-y-6">
      <p className="text-sm text-slate-600">
        {all.length} funkcí a služeb v {funkce.length} oblastech · hotovo <b>{count('hotovo')}</b> · částečně <b>{count('castecne')}</b> · v plánu <b>{count('plan')}</b>
      </p>
      {funkce.map((k) => (
        <section key={k.nazev} className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <h2 className="border-b border-slate-200 bg-fno-50 px-4 py-2 text-sm font-semibold text-fno-900">{k.nazev}</h2>
          <table className="w-full min-w-[760px] table-fixed text-left text-sm">
            <thead className="text-xs text-slate-500">
              <tr>
                <th className="w-[19%] px-4 py-2 font-medium">Funkce</th>
                <th className="w-[20%] px-4 py-2 font-medium">Služba / technologie</th>
                <th className="px-4 py-2 font-medium">K čemu slouží</th>
                <th className="w-[18%] px-4 py-2 font-medium">Kde v kódu</th>
                <th className="w-24 px-4 py-2 font-medium">Stav</th>
              </tr>
            </thead>
            <tbody>
              {k.polozky.map((p) => (
                <tr key={p.nazev} className="border-t align-top [overflow-wrap:anywhere]">
                  <td className="px-4 py-2 font-medium">{p.nazev}</td>
                  <td className="px-4 py-2">{p.sluzba}</td>
                  <td className="px-4 py-2 text-slate-700">{p.k_cemu}</td>
                  <td className="break-all px-4 py-2 font-mono text-xs text-slate-500">{p.kde}</td>
                  <td className="px-4 py-2">
                    <span className={`whitespace-nowrap rounded px-1.5 py-0.5 text-xs ${STAV[p.stav][1]}`}>{STAV[p.stav][0]}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  )
}

/** Minimal Markdown (headings, paragraphs, lists, quotes, **bold**, `code`); enough for docs/navod.md. */
function markdown(src: string): ReactNode[] {
  const out: ReactNode[] = []
  const lines = src.replace(/\r\n/g, '\n').split('\n')
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const key = out.length
    if (!line.trim()) { i++; continue }
    const h = /^(#{1,3})\s+(.*)$/.exec(line)
    if (h) {
      const cls = ['mb-4 text-2xl font-semibold', 'mb-2 mt-6 text-lg font-semibold', 'mb-1 mt-4 font-semibold'][h[1].length - 1]
      const Tag = (['h2', 'h3', 'h4'] as const)[h[1].length - 1]
      out.push(<Tag key={key} className={cls}>{inline(h[2])}</Tag>)
      i++
      continue
    }
    const block = (re: RegExp) => {
      const items: string[] = []
      while (i < lines.length && (re.test(lines[i]) || /^\s+\S/.test(lines[i]))) {
        if (re.test(lines[i])) items.push(lines[i].replace(re, ''))
        else items[items.length - 1] += ' ' + lines[i].trim()
        i++
      }
      return items
    }
    if (/^\s*[-*]\s/.test(line) && !/^\s+/.test(line)) {
      const [items, next] = bulletList(lines, i)
      i = next
      out.push(<ul key={key} className="mb-3 list-disc space-y-1 pl-6">{items}</ul>)
      continue
    }
    if (/^\d+\.\s/.test(line)) {
      out.push(<ol key={key} className="mb-3 list-decimal space-y-1 pl-6">{block(/^\d+\.\s/).map((t, j) => <li key={j}>{inline(t)}</li>)}</ol>)
      continue
    }
    if (line.startsWith('>')) {
      const text: string[] = []
      while (i < lines.length && lines[i].startsWith('>')) text.push(lines[i++].replace(/^>\s?/, ''))
      out.push(<blockquote key={key} className="mb-3 rounded border-l-4 border-amber-400 bg-amber-50 px-3 py-2">{inline(text.join(' '))}</blockquote>)
      continue
    }
    const text: string[] = []
    while (i < lines.length && lines[i].trim() && !/^(#|>|\d+\.\s|[-*]\s)/.test(lines[i])) text.push(lines[i++])
    out.push(<p key={key} className="mb-3 leading-relaxed">{inline(text.join(' '))}</p>)
  }
  return out
}

/** Bullet list where indented "- " lines form a nested list under the previous item. */
function bulletList(lines: string[], start: number): [ReactNode[], number] {
  const items: { text: string; sub: string[] }[] = []
  let i = start
  while (i < lines.length) {
    const top = /^[-*]\s+(.*)$/.exec(lines[i])
    const sub = /^\s+[-*]\s+(.*)$/.exec(lines[i])
    if (top) items.push({ text: top[1], sub: [] })
    else if (sub && items.length) items[items.length - 1].sub.push(sub[1])
    else break
    i++
  }
  const nodes = items.map((it, j) => (
    <li key={j}>
      {inline(it.text)}
      {it.sub.length > 0 && <ul className="mt-1 list-[circle] space-y-0.5 pl-6">{it.sub.map((s, k) => <li key={k}>{inline(s)}</li>)}</ul>}
    </li>
  ))
  return [nodes, i]
}

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean).map((part, j) =>
    part.startsWith('**') ? <b key={j}>{part.slice(2, -2)}</b>
      : part.startsWith('`') ? <code key={j} className="rounded bg-slate-100 px-1 text-[0.9em]">{part.slice(1, -1)}</code>
        : part,
  )
}
