import { BarChart3, BookOpen, Layers3, Plus } from 'lucide-react'
import type { Screen } from '../types'

interface NavigationProps {
  screen: Screen
  onNavigate: (screen: Screen) => void
}

const items = [
  { screen: 'decks' as const, label: 'Decks', Icon: Layers3 },
  { screen: 'session' as const, label: 'Study', Icon: BookOpen },
  { screen: 'stats' as const, label: 'Stats', Icon: BarChart3 },
  { screen: 'import' as const, label: 'Add', Icon: Plus }
]

export function Navigation({ screen, onNavigate }: NavigationProps) {
  return (
    <nav className="nav" aria-label="Primary navigation">
      {items.map(({ screen: target, label, Icon }) => (
        <button key={target} className={screen === target || (screen === 'detail' && target === 'decks') ? 'nav-item active' : 'nav-item'} onClick={() => onNavigate(target)} aria-current={screen === target ? 'page' : undefined}>
          <Icon size={19} strokeWidth={1.8} aria-hidden="true" />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  )
}
