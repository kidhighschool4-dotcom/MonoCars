export interface Car {
  id: string
  make: string
  model: string
  year: number
  price: number
  priceLabel: 'Good Deal' | 'Fair' | 'Overpriced'
  type: 'Sedan' | 'SUV' | 'Pickup' | 'Hatchback' | 'Van' | 'Coupe' | 'Crossover' | string
  mileage: number
  location: string
  images: string[]
  description: string
  pros: string[]
  cons: string[]
  sellerName: string
  sellerPhone: string
  estimatedValue: number
  source: 'scraped' | 'user'
  createdAt: string
  // Extended fields from DB
  fuel?: string
  transmission?: string
  color?: string
  seats?: number
  engineCc?: number
}

export interface CarEvent {
  id: string
  title: string
  location: string
  date: string
  description: string
  image: string
  category: string
  attendees: number
}

export interface Post {
  id: string
  userId: string
  userName: string
  userAvatar: string
  content: string
  images: string[]
  likes: number
  comments: Comment[]
  createdAt: string
  type: 'question' | 'photo' | 'discussion'
}

export interface Comment {
  id: string
  userId: string
  userName: string
  content: string
  createdAt: string
}

export interface PriceAnalysis {
  estimatedValue: number
  askingPrice: number
  difference: number
  label: 'Good Deal' | 'Fair' | 'Overpriced'
  confidence: number
}
