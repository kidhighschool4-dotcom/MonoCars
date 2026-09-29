import { mockPosts, mockEvents } from '@/lib/mockData'
import { getPosts, getFeaturedEvents } from '@/lib/db'
import PostCard from '@/components/community/PostCard'
import PostForm from '@/components/community/PostForm'
import Link from 'next/link'
import { TrendingUp, Calendar } from 'lucide-react'
import PageHeader from '@/components/ui/PageHeader'

const trendingTopics = [
  'Toyota Fortuner',
  'EV in Cambodia',
  'Import Taxes 2026',
  'Used Car Tips',
  'BMW vs Lexus',
  'Honda Civic RS',
  'Land Cruiser',
  'Phnom Penh Traffic',
]

export default async function CommunityPage() {
  const [dbPosts, dbEvents] = await Promise.all([getPosts(20), getFeaturedEvents(3)])

  const posts    = dbPosts.length  ? dbPosts  : mockPosts
  const upcoming = dbEvents.length ? dbEvents : mockEvents.slice(0, 3)

  return (
    <div className="min-h-screen bg-paper">
      <PageHeader
        eyebrow="Community"
        title="The FBM community"
        description="Ask questions, share your car and get honest advice from 8,000+ drivers in Cambodia."
      />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Feed */}
          <div className="lg:col-span-2 space-y-5">
            <PostForm />
            {posts.map((post) => (
              <PostCard key={post.id} post={post} />
            ))}
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Stats */}
            <div className="bg-ink rounded-2xl p-5 text-white">
              <h3 className="font-bold text-sm uppercase tracking-wide text-brand mb-4">
                Community Stats
              </h3>
              <div className="space-y-3">
                {[
                  { label: 'Members', value: '8,240+' },
                  { label: 'Posts This Month', value: '1,420' },
                  { label: 'Questions Answered', value: '3,890' },
                ].map(({ label, value }) => (
                  <div key={label} className="flex justify-between items-center py-2 border-b border-gray-800 last:border-0">
                    <span className="text-gray-400 text-sm">{label}</span>
                    <span className="font-bold text-white">{value}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Trending Topics */}
            <div className="bg-white rounded-2xl shadow-sm border border-line p-5">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp className="w-4 h-4 text-brand" />
                <h3 className="font-bold text-sm text-ink uppercase tracking-wide">
                  Trending Topics
                </h3>
              </div>
              <div className="flex flex-wrap gap-2">
                {trendingTopics.map((topic) => (
                  <span
                    key={topic}
                    className="text-xs px-3 py-1.5 bg-paper border border-line text-muted rounded-full hover:bg-brand/10 hover:border-brand hover:text-brand cursor-pointer transition-all"
                  >
                    #{topic.replace(/\s+/g, '')}
                  </span>
                ))}
              </div>
            </div>

            {/* Upcoming Events */}
            <div className="bg-white rounded-2xl shadow-sm border border-line p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-brand" />
                  <h3 className="font-bold text-sm text-ink uppercase tracking-wide">
                    Upcoming Events
                  </h3>
                </div>
                <Link href="/events" className="text-xs text-brand hover:underline font-medium">
                  See all
                </Link>
              </div>
              <div className="space-y-3">
                {upcoming.map((event) => (
                  <Link
                    key={event.id}
                    href={`/events/${event.id}`}
                    className="flex gap-3 group"
                  >
                    <div className="w-12 h-12 rounded-xl overflow-hidden flex-shrink-0">
                      <img
                        src={event.image}
                        alt={event.title}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-ink truncate group-hover:text-brand transition-colors">
                        {event.title}
                      </p>
                      <p className="text-xs text-gray-400">
                        {new Date(event.date).toLocaleDateString('en-US', {
                          month: 'short',
                          day: 'numeric',
                        })}
                      </p>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
