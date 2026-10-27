// Skeleton shown instantly while /admin/social loads its data on the server (streamed by the loading.js convention)
const Bar = ({ className }: { className: string }) => <div className={`animate-pulse rounded-md bg-line/70 ${className}`} />

export default function Loading() {
  return (
    <div className="min-h-screen bg-paper/50" aria-busy="true" aria-label="Loading rental seekers">
      <header className="bg-surface border-b border-line">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div className="space-y-3">
              <Bar className="h-3 w-40" />
              <Bar className="h-9 w-80 max-w-full" />
              <Bar className="h-4 w-[28rem] max-w-full" />
            </div>
            <div className="flex divide-x divide-line rounded-xl border border-line bg-surface">
              {[0, 1, 2].map((i) => (
                <div key={i} className="px-5 py-3 space-y-2">
                  <Bar className="h-2.5 w-20" />
                  <Bar className="h-7 w-12" />
                </div>
              ))}
            </div>
          </div>
          <div className="mt-6 flex flex-wrap gap-2">
            {[0, 1, 2, 3, 4].map((i) => <Bar key={i} className="h-8 w-24 rounded-lg" />)}
          </div>
        </div>
      </header>

      <div className="sticky top-16 z-20 border-b border-line bg-surface/90">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2.5 flex items-center gap-2">
          <Bar className="h-8 w-72 rounded-lg" />
          <Bar className="ml-auto h-8 w-56 rounded-lg" />
        </div>
      </div>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="flex flex-col rounded-2xl border border-line bg-surface overflow-hidden">
              <Bar className="aspect-[16/10] w-full rounded-none" />
              <div className="p-4 space-y-3">
                <div className="flex gap-2"><Bar className="h-5 w-24" /><Bar className="ml-auto h-5 w-14" /></div>
                <Bar className="h-5 w-full" />
                <Bar className="h-5 w-2/3" />
                <div className="flex gap-2 pt-2"><Bar className="h-7 w-28 rounded-lg" /><Bar className="h-7 w-24 rounded-lg" /></div>
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  )
}
