import { mockPosts, mockEvents } from '@/lib/mockData'
import PostCard from '@/components/community/PostCard'
import PostForm from '@/components/community/PostForm'
import Link from 'next/link'
import { TrendingUp, Calendar, Users } from 'lucide-react'

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

export default function CommunityPage() {
  const upcomingEvents = mockEvents.slice(0, 3)

  return (
    <div className="min-h-screen bg-[#F8F5F0]">
      {/* Header */}
      <div className="bg-[#1A1A1A] py-12 md:py-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3 mb-2">
            <Users className="w-5 h-5 text-[#CBA135]" />
            <p className="text-[#CBA135] text-sm font-semibold uppercase tracking-wider">
              Community
            </p>
          </div>
          <h1 className="text-3xl md:text-4xl font-black text-white">Car Enthusiast Feed</h1>
          <p className="text-gray-400 mt-2 text-sm">
            Connect with 8,000+ car enthusiasts across Cambodia
          </p>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Feed */}
          <div className="lg:col-span-2 space-y-5">
            {/* Post Form */}
            <PostForm isAuthenticated={false} />

            {/* Posts */}
            {mockPosts.map((post) => (
              <PostCard key={post.id} post={post} />
            ))}
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Stats */}
            <div className="bg-[#1A1A1A] rounded-2xl p-5 text-white">
              <h3 className="font-bold text-sm uppercase tracking-wide text-[#CBA135] mb-4">
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
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp className="w-4 h-4 text-[#CBA135]" />
                <h3 className="font-bold text-sm text-[#1A1A1A] uppercase tracking-wide">
                  Trending Topics
                </h3>
              </div>
              <div className="flex flex-wrap gap-2">
                {trendingTopics.map((topic) => (
                  <span
                    key={topic}
                    className="text-xs px-3 py-1.5 bg-gray-50 border border-gray-200 text-gray-600 rounded-full hover:bg-[#CBA135]/10 hover:border-[#CBA135] hover:text-[#CBA135] cursor-pointer transition-all"
                  >
                    #{topic.replace(/\s+/g, '')}
                  </span>
                ))}
              </div>
            </div>

            {/* Upcoming Events */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-[#CBA135]" />
                  <h3 className="font-bold text-sm text-[#1A1A1A] uppercase tracking-wide">
                    Upcoming Events
                  </h3>
                </div>
                <Link href="/events" className="text-xs text-[#CBA135] hover:underline font-medium">
                  See all
                </Link>
              </div>
              <div className="space-y-3">
                {upcomingEvents.map((event) => (
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
                      <p className="text-sm font-semibold text-[#1A1A1A] truncate group-hover:text-[#CBA135] transition-colors">
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
