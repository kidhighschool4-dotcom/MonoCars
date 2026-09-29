interface PageHeaderProps {
  eyebrow: string
  title: string
  description?: string
  children?: React.ReactNode
}

/** Light page header shared by the inner pages (Cars, Events, Community…). */
export default function PageHeader({ eyebrow, title, description, children }: PageHeaderProps) {
  return (
    <div className="bg-surface border-b border-line">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-12 pb-10 md:pt-16">
        <p className="inline-flex items-center gap-2 text-sm font-medium text-muted mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-brand" />
          {eyebrow}
        </p>
        <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-3 text-lg text-muted max-w-2xl">{description}</p>}
        {children}
      </div>
    </div>
  )
}
