// Icons for all tabs: authored SVG on a 24px grid, 1.75 stroke, currentColor.
import type { ReactNode, SVGProps } from 'react'

// a plain function, not a component, so this module exports only the Icon map (fast refresh)
function svg(p: SVGProps<SVGSVGElement>, children: ReactNode) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth={1.75}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...p}>
      {children}
    </svg>
  )
}

type IconProps = SVGProps<SVGSVGElement>
export const Icon = {
  home: (p: IconProps) => svg(p, <><path d="M3 10.5 12 3l9 7.5" /><path d="M5.5 9v12h4.5v-6h4v6h4.5V9" /></>),
  list: (p: IconProps) => svg(p, <><path d="M9 6h11M9 12h11M9 18h11" /><path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01" strokeWidth={2.5} /></>),
  relapse: (p: IconProps) => svg(p, <><path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1" /><path d="M3.5 3.5V9H9" /><path d="M12 8v4.5l3 1.5" /></>),
  userPlus: (p: IconProps) => svg(p, <><circle cx="9" cy="8" r="4" /><path d="M2 21a7 7 0 0 1 14 0" /><path d="M19 8v6M16 11h6" /></>),
  book: (p: IconProps) => svg(p, <><path d="M4 19.5V5a2 2 0 0 1 2-2h14v15H6a2 2 0 0 0-2 2v0a2 2 0 0 0 2 2h14" /><path d="M8.5 7.5h7M8.5 11h5" /></>),
  extract: (p: IconProps) => svg(p, <><path d="M14 3H6.5A2.5 2.5 0 0 0 4 5.5v13A2.5 2.5 0 0 0 6.5 21h11a2.5 2.5 0 0 0 2.5-2.5V9z" /><path d="M14 3v6h6" /><path d="M8 13.5h8M8 17h5" /></>),
  docs: (p: IconProps) => svg(p, <><path d="M2.5 5H9a3 3 0 0 1 3 3v12a2.5 2.5 0 0 0-2.5-2.5h-7z" /><path d="M21.5 5H15a3 3 0 0 0-3 3v12a2.5 2.5 0 0 1 2.5-2.5h7z" /></>),
  upload: (p: IconProps) => svg(p, <><path d="M12 15V3.5M7 8.5l5-5 5 5" /><path d="M4 15v3.5A2.5 2.5 0 0 0 6.5 21h11a2.5 2.5 0 0 0 2.5-2.5V15" /></>),
  search: (p: IconProps) => svg(p, <><circle cx="11" cy="11" r="7" /><path d="m20.5 20.5-4.5-4.5" /></>),
  x: (p: IconProps) => svg(p, <><path d="M6 6l12 12M18 6 6 18" /></>),
  chevron: (p: IconProps) => svg(p, <><path d="m9 5.5 6.5 6.5L9 18.5" /></>),
  file: (p: IconProps) => svg(p, <><path d="M14 3H6.5A2.5 2.5 0 0 0 4 5.5v13A2.5 2.5 0 0 0 6.5 21h11a2.5 2.5 0 0 0 2.5-2.5V9z" /><path d="M14 3v6h6" /></>),
  check: (p: IconProps) => svg(p, <><path d="m4.5 12.5 5 5 10-11" /></>),
  alert: (p: IconProps) => svg(p, <><path d="M10.3 4 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 4a2 2 0 0 0-3.4 0z" /><path d="M12 9.5v4M12 17h.01" /></>),
  plus: (p: IconProps) => svg(p, <><path d="M12 5v14M5 12h14" /></>),
  trash: (p: IconProps) => svg(p, <><path d="M4 7h16M10 11v6M14 11v6" /><path d="M6 7l1 12.5A1.5 1.5 0 0 0 8.5 21h7a1.5 1.5 0 0 0 1.5-1.5L18 7M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7" /></>),
}

