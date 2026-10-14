import type { LucideIcon } from 'lucide-react'

interface EmptyStateProps {
  Icon: LucideIcon
  eyebrow: string
  title: string
  message: string
  action?: string
  onAction?: () => void
}

export function EmptyState({ Icon, eyebrow, title, message, action, onAction }: EmptyStateProps) {
  return (
    <section className="empty-state page-enter">
      <div className="empty-icon"><Icon size={28} strokeWidth={1.5} /></div>
      <p className="eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      <p className="muted body-copy">{message}</p>
      {action && onAction && <button className="primary-button" onClick={onAction}>{action}</button>}
    </section>
  )
}
