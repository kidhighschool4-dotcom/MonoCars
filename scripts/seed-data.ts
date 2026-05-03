/**
 * MonoCars seed script — run after schema-only.sql is applied in Supabase SQL Editor
 * Usage: npx tsx scripts/seed-data.ts
 */

import { createClient } from '@supabase/supabase-js'

const SUPABASE_URL = 'https://kxsnwdvpkfbyuklflcvf.supabase.co'
const SERVICE_ROLE_KEY =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt4c253ZHZwa2ZieXVrbGZsY3ZmIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzc4MTk5NSwiZXhwIjoyMDkzMzU3OTk1fQ.j15UPZFSq2bnAJ3pEL4LW-dDmalMmFgauR2zz3pgTLo'

const sb = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
  auth: { autoRefreshToken: false, persistSession: false },
})

// ─── Lookup Data ─────────────────────────────────────────────────────────────

const BRANDS = [
  { name: 'Toyota',        country: 'Japan' },
  { name: 'Honda',         country: 'Japan' },
  { name: 'Lexus',         country: 'Japan' },
  { name: 'BMW',           country: 'Germany' },
  { name: 'Mercedes-Benz', country: 'Germany' },
  { name: 'Hyundai',       country: 'South Korea' },
  { name: 'Kia',           country: 'South Korea' },
  { name: 'Ford',          country: 'United States' },
  { name: 'Mitsubishi',    country: 'Japan' },
  { name: 'Nissan',        country: 'Japan' },
  { name: 'Mazda',         country: 'Japan' },
  { name: 'Audi',          country: 'Germany' },
  { name: 'Isuzu',         country: 'Japan' },
  { name: 'Land Rover',    country: 'United Kingdom' },
  { name: 'Porsche',       country: 'Germany' },
]

const CAR_TYPES    = ['Sedan', 'SUV', 'Pickup', 'Hatchback', 'Van', 'Coupe', 'Crossover']
const FUEL_TYPES   = ['Gasoline', 'Diesel', 'Hybrid', 'Plug-in Hybrid', 'Electric']
const TRANSMISSIONS = ['Automatic', 'Manual', 'CVT', 'Semi-Automatic']

// ─── Car Listings ─────────────────────────────────────────────────────────────

const CARS = [
  {
    title: '2022 Toyota Land Cruiser 300 GR Sport',
    brand: 'Toyota', model: 'Land Cruiser 300', year: 2022,
    type: 'SUV', fuel: 'Gasoline', transmission: 'Automatic',
    price: 95000, estimated: 108000, label: 'Good Deal',
    mileage: 8200, color: 'Pearl White', cc: 3500, seats: 7,
    location: 'Phnom Penh', source: 'scraped', featured: true,
    seller: 'Sopheak Mao', phone: '+855 12 888 001',
    description: 'Flagship Toyota Land Cruiser 300 GR Sport imported from Japan, full Toyota warranty remaining. Twin-turbocharged V6 engine delivers effortless power on any terrain. Panoramic moonroof, 14-speaker JBL audio, Toyota Safety Sense 3.0. The undisputed king of Cambodia roads.',
    images: [
      { url: 'https://images.unsplash.com/photo-1619767886558-efdc259cde1a?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?w=800', primary: false, order: 1 },
      { url: 'https://images.unsplash.com/photo-1551830820-41e5f6cfc2a1?w=800', primary: false, order: 2 },
    ],
    pros: ['Twin-turbo V6 with massive torque', 'Full Toyota warranty still active', 'Advanced Multi-Terrain Select 4WD', 'Panoramic moonroof + JBL audio'],
    cons: ['High fuel consumption in city', 'Large size — tight for city parking'],
  },
  {
    title: '2021 Toyota Fortuner 2.4G 4WD',
    brand: 'Toyota', model: 'Fortuner', year: 2021,
    type: 'SUV', fuel: 'Diesel', transmission: 'Automatic',
    price: 38500, estimated: 40000, label: 'Fair',
    mileage: 32000, color: 'Attitude Black', cc: 2400, seats: 7,
    location: 'Phnom Penh', source: 'user', featured: true,
    seller: 'Rith Vanna', phone: '+855 17 456 002',
    description: 'Well-maintained Toyota Fortuner 2.4G in excellent condition. Single owner, always serviced at Toyota dealer. Diesel engine is perfect for long-distance trips to Siem Reap or Sihanoukville. 7 seats, leather interior, parking sensors, reverse camera.',
    images: [
      { url: 'https://images.unsplash.com/photo-1551830820-41e5f6cfc2a1?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1580273916550-e323be2ae537?w=800', primary: false, order: 1 },
    ],
    pros: ['Fuel-efficient 2.4L diesel engine', '7-seat capacity with leather interior', 'Full Toyota dealer service history', 'Excellent resale value'],
    cons: ['Older entertainment system', 'Diesel harder to find in some provinces'],
  },
  {
    title: '2023 Toyota Camry 2.5 Hybrid',
    brand: 'Toyota', model: 'Camry', year: 2023,
    type: 'Sedan', fuel: 'Hybrid', transmission: 'CVT',
    price: 36000, estimated: 43000, label: 'Good Deal',
    mileage: 5500, color: 'Midnight Blue', cc: 2500, seats: 5,
    location: 'Phnom Penh', source: 'user', featured: false,
    seller: 'Bopha Chan', phone: '+855 93 123 003',
    description: 'Near-new Toyota Camry Hybrid with only 5,500km. Extremely fuel efficient — averaging 5.5L/100km in city traffic. Perfect executive sedan for business use. Full Toyota warranty, 12.3" touchscreen, wireless Apple CarPlay and Android Auto, Toyota Safety Sense.',
    images: [
      { url: 'https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1542362567-b07e54358753?w=800', primary: false, order: 1 },
    ],
    pros: ['Excellent fuel economy — 5.5L/100km', 'Almost new, full Toyota warranty', 'Wireless Apple CarPlay + Android Auto', 'Quiet and smooth ride'],
    cons: ['Premium fuel required', 'Higher price than petrol equivalent'],
  },
  {
    title: '2020 Toyota Hilux Revo 2.4G 4x4',
    brand: 'Toyota', model: 'Hilux Revo', year: 2020,
    type: 'Pickup', fuel: 'Diesel', transmission: 'Automatic',
    price: 26500, estimated: 27500, label: 'Fair',
    mileage: 56000, color: 'Silver Metallic', cc: 2400, seats: 5,
    location: 'Siem Reap', source: 'user', featured: false,
    seller: 'Dara Keo', phone: '+855 17 234 004',
    description: 'Reliable Toyota Hilux Revo 2.4G with 4x4 capability. Used for business deliveries — all serviced. Dual-cab with work liner, tow bar, snorkel fitted. Great for travel between provinces. Honest seller, no hidden issues.',
    images: [
      { url: 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1519641471654-76ce0107ad1b?w=800', primary: false, order: 1 },
    ],
    pros: ['4x4 capability for off-road', 'Snorkel and tow bar fitted', 'Durable diesel engine', 'Dual-cab with work liner'],
    cons: ['Higher mileage — 56,000km', 'Ride rougher than SUV for passengers'],
  },
  {
    title: '2022 Honda CR-V 1.5 Turbo AWD',
    brand: 'Honda', model: 'CR-V', year: 2022,
    type: 'SUV', fuel: 'Gasoline', transmission: 'CVT',
    price: 29500, estimated: 34000, label: 'Good Deal',
    mileage: 18500, color: 'Lunar Silver', cc: 1500, seats: 5,
    location: 'Phnom Penh', source: 'user', featured: false,
    seller: 'Srey Leak', phone: '+855 12 567 005',
    description: 'Stylish Honda CR-V 1.5 Turbo with AWD. Lady owner, garage kept, non-smoker. Turbocharged engine feels punchy yet returns excellent fuel economy. Honda Sensing suite (collision mitigation, lane keep, adaptive cruise). Perfect family SUV for Phnom Penh.',
    images: [
      { url: 'https://images.unsplash.com/photo-1606016159991-dfe4f2746ad5?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1617654112368-307921291f42?w=800', primary: false, order: 1 },
    ],
    pros: ['Honda Sensing safety suite', 'AWD for rainy season confidence', 'Excellent fuel economy for turbo', 'Lady owner — immaculate condition'],
    cons: ['CVT can feel sluggish in sport mode', 'Smaller boot than competitors'],
  },
  {
    title: '2021 Honda Accord 1.5 Turbo',
    brand: 'Honda', model: 'Accord', year: 2021,
    type: 'Sedan', fuel: 'Gasoline', transmission: 'CVT',
    price: 27000, estimated: 28500, label: 'Fair',
    mileage: 29000, color: 'Platinum White Pearl', cc: 1500, seats: 5,
    location: 'Phnom Penh', source: 'user', featured: false,
    seller: 'Michael Chen', phone: '+855 96 888 006',
    description: 'Elegant Honda Accord imported from Singapore. Turbocharged 1.5L produces 192hp — surprisingly quick. 10.2" touchscreen, wireless phone charging, heated seats, sunroof, Honda Sensing. Driven by expat returning home. Complete service records.',
    images: [
      { url: 'https://images.unsplash.com/photo-1617654112368-307921291f42?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=800', primary: false, order: 1 },
    ],
    pros: ['192hp turbo — fun to drive', 'Wireless charging + heated seats', 'Full Singapore service records', 'Spacious rear cabin'],
    cons: ['Higher maintenance than Japanese average', 'Small turbo engine for highway cruising'],
  },
  {
    title: '2023 Lexus RX 350h F-Sport',
    brand: 'Lexus', model: 'RX 350h', year: 2023,
    type: 'SUV', fuel: 'Hybrid', transmission: 'Automatic',
    price: 72000, estimated: 75000, label: 'Fair',
    mileage: 6500, color: 'Sonic Titanium', cc: 2500, seats: 5,
    location: 'Phnom Penh', source: 'scraped', featured: true,
    seller: 'Import KH Auto', phone: '+855 23 777 007',
    description: 'Nearly new Lexus RX 350h F-Sport in stunning Sonic Titanium. Self-charging hybrid with 246 combined horsepower. Lexus Safety System+, 14" touchscreen, Mark Levinson 21-speaker audio, panoramic roof. Purchased by expat relocating. Perfect flagship for business executives.',
    images: [
      { url: 'https://images.unsplash.com/photo-1617654112368-307921291f42?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1580273916550-e323be2ae537?w=800', primary: false, order: 1 },
    ],
    pros: ['Self-charging hybrid — no plug needed', '21-speaker Mark Levinson audio', 'F-Sport with adaptive suspension', 'Only 6,500km — essentially new'],
    cons: ['Premium service costs more than Toyota', 'Parts supply slower than mainstream brands'],
  },
  {
    title: '2022 Mercedes-Benz GLC 300 AMG Line',
    brand: 'Mercedes-Benz', model: 'GLC 300', year: 2022,
    type: 'SUV', fuel: 'Gasoline', transmission: 'Automatic',
    price: 65000, estimated: 61000, label: 'Overpriced',
    mileage: 14000, color: 'Obsidian Black', cc: 2000, seats: 5,
    location: 'Phnom Penh', source: 'scraped', featured: false,
    seller: 'Luxury Auto PH', phone: '+855 23 999 008',
    description: 'Mercedes-Benz GLC 300 AMG Line in premium condition. MBUX touchscreen with voice control, Burmester sound system, 19" AMG wheels, ambient lighting package. Imported via Singapore dealer. All maintenance at Mercedes dealer Phnom Penh.',
    images: [
      { url: 'https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?w=800', primary: false, order: 1 },
    ],
    pros: ['AMG Line styling package', 'MBUX AI voice control system', 'Burmester surround sound', 'Strong brand prestige'],
    cons: ['Priced above market value', 'High maintenance and parts cost'],
  },
  {
    title: '2021 BMW 320i M Sport',
    brand: 'BMW', model: '320i', year: 2021,
    type: 'Sedan', fuel: 'Gasoline', transmission: 'Automatic',
    price: 42000, estimated: 43500, label: 'Fair',
    mileage: 38000, color: 'Alpine White', cc: 2000, seats: 5,
    location: 'Phnom Penh', source: 'user', featured: false,
    seller: 'Panha Lim', phone: '+855 77 345 009',
    description: 'Sporty BMW 320i M Sport with the perfect balance of performance and luxury. 184hp 2.0 TwinPower Turbo, 8-speed automatic. M Sport suspension, 18" M wheels, sport seats with heating. iDrive 7 with 10.25" display, BMW Live Cockpit. Fun to drive daily.',
    images: [
      { url: 'https://images.unsplash.com/photo-1555215695-3004980ad54e?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1494976388531-d1058494cdd8?w=800', primary: false, order: 1 },
    ],
    pros: ['M Sport package — sharper dynamics', 'Heated sport seats front and rear', 'BMW ConnectedDrive + wireless CarPlay', 'Exciting to drive on open roads'],
    cons: ['Higher than average running costs', 'Firm M Sport ride on rough roads'],
  },
  {
    title: '2022 Hyundai Tucson 1.6 Turbo Premium',
    brand: 'Hyundai', model: 'Tucson', year: 2022,
    type: 'SUV', fuel: 'Gasoline', transmission: 'Automatic',
    price: 25000, estimated: 29500, label: 'Good Deal',
    mileage: 21000, color: 'Phantom Black', cc: 1600, seats: 5,
    location: 'Phnom Penh', source: 'user', featured: false,
    seller: 'Nary Sok', phone: '+855 12 678 010',
    description: 'Excellent value Hyundai Tucson 1.6 Turbo — one of the best mid-size SUVs available. Panoramic sunroof, Bose 8-speaker audio, heated and ventilated front seats, 360° camera system, blind spot warning. Selling below market due to owner upgrading.',
    images: [
      { url: 'https://images.unsplash.com/photo-1590510296227-13d7aac29736?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1619767886558-efdc259cde1a?w=800', primary: false, order: 1 },
    ],
    pros: ['Priced well below market value', 'Panoramic sunroof + Bose audio', '360° camera for easy parking', 'Heated and ventilated front seats'],
    cons: ['Less prestigious brand than Japanese rivals', 'Resale value slightly lower than Toyota/Honda'],
  },
  {
    title: '2022 Kia Sportage 1.6 Turbo',
    brand: 'Kia', model: 'Sportage', year: 2022,
    type: 'SUV', fuel: 'Gasoline', transmission: 'Automatic',
    price: 22500, estimated: 27000, label: 'Good Deal',
    mileage: 25500, color: 'Snow White Pearl', cc: 1600, seats: 5,
    location: 'Kampot', source: 'user', featured: false,
    seller: 'James Walker', phone: '+855 96 234 011',
    description: 'Brand new generation Kia Sportage with bold design. 1.6 turbo engine with smooth 7-speed DCT. 12.3" panoramic display, wireless phone charging, KIA Drive Wise safety suite. Living in Kampot, moving to Phnom Penh, selling to avoid shipping cost. Priced to sell fast.',
    images: [
      { url: 'https://images.unsplash.com/photo-1606611013016-969c19ba27bb?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1590510296227-13d7aac29736?w=800', primary: false, order: 1 },
    ],
    pros: ['Significantly below market price', 'Latest generation with bold styling', '12.3" panoramic dual display', 'KIAS Drive Wise safety suite'],
    cons: ['Located in Kampot — may need transport', 'DCT can shudder at low speed'],
  },
  {
    title: '2021 Ford Ranger Wildtrak 2.0 Bi-Turbo',
    brand: 'Ford', model: 'Ranger Wildtrak', year: 2021,
    type: 'Pickup', fuel: 'Diesel', transmission: 'Automatic',
    price: 30000, estimated: 31500, label: 'Fair',
    mileage: 43000, color: 'Meteor Grey', cc: 2000, seats: 5,
    location: 'Sihanoukville', source: 'user', featured: false,
    seller: 'Tom Richards', phone: '+855 96 777 012',
    description: 'Ford Ranger Wildtrak Bi-Turbo — the premium pickup. 213hp twin-turbo diesel, best-in-class towing 3,500kg. 10" SYNC 4 touchscreen, 360° camera, FordPass Connect. Used for coastal property development. Serviced every 5,000km at Ford dealer. All receipts kept.',
    images: [
      { url: 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1519641471654-76ce0107ad1b?w=800', primary: false, order: 1 },
    ],
    pros: ['3,500kg tow rating — class leading', '360° camera system', 'Full Ford dealer service history', 'Best payload capacity in segment'],
    cons: ['Located in Sihanoukville', 'High-spec trim has more electronics to maintain'],
  },
  {
    title: '2022 Mitsubishi Pajero Sport 2.4 GT',
    brand: 'Mitsubishi', model: 'Pajero Sport', year: 2022,
    type: 'SUV', fuel: 'Diesel', transmission: 'Automatic',
    price: 33000, estimated: 35000, label: 'Fair',
    mileage: 22000, color: 'Graphite Grey', cc: 2400, seats: 7,
    location: 'Phnom Penh', source: 'user', featured: false,
    seller: 'Vanna Chea', phone: '+855 88 456 013',
    description: 'Tough and capable Mitsubishi Pajero Sport GT with 7 seats. 181hp diesel with Super Select 4WD-II — locks into 4L for true off-road. 8" touchscreen with Apple CarPlay, powered tailgate, Mitsubishi e-Assist safety. Popular with NGO workers for province travel.',
    images: [
      { url: 'https://images.unsplash.com/photo-1554843231-0b5fb3f24dc8?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1551830820-41e5f6cfc2a1?w=800', primary: false, order: 1 },
    ],
    pros: ['Super Select 4WD-II — true off-road', '7-seat capacity — great for family', 'Powered tailgate for convenience', 'Strong resale value in Cambodia'],
    cons: ['Older interior design vs competitors', 'Long body — harder to maneuver in city'],
  },
  {
    title: '2021 Mazda CX-5 2.5 Turbo AWD',
    brand: 'Mazda', model: 'CX-5', year: 2021,
    type: 'SUV', fuel: 'Gasoline', transmission: 'Automatic',
    price: 24500, estimated: 28000, label: 'Good Deal',
    mileage: 31000, color: 'Machine Grey Metallic', cc: 2500, seats: 5,
    location: 'Phnom Penh', source: 'user', featured: false,
    seller: 'Kimheng Rin', phone: '+855 85 234 014',
    description: 'Beautiful Mazda CX-5 2.5 Turbo in the iconic Machine Grey Metallic. KODO design is stunning inside and out. 227hp turbo feels like a sports SUV. Bose 10-speaker audio, 360° view monitor, i-ACTIVSENSE safety. Mazda is underrated in Cambodia — buy at a discount, enjoy premium quality.',
    images: [
      { url: 'https://images.unsplash.com/photo-1591073113125-e46713c829ed?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1606016159991-dfe4f2746ad5?w=800', primary: false, order: 1 },
    ],
    pros: ['227hp turbo — most powerful in class', 'Premium Bose 10-speaker audio', 'Stunning KODO design inside and out', 'Priced below market — great value'],
    cons: ['Mazda parts slightly harder to find', 'Lower resale vs Toyota/Honda'],
  },
  {
    title: '2019 Nissan Navara 2.5 VL 4WD',
    brand: 'Nissan', model: 'Navara', year: 2019,
    type: 'Pickup', fuel: 'Diesel', transmission: 'Automatic',
    price: 16500, estimated: 19000, label: 'Good Deal',
    mileage: 69000, color: 'Burning Red', cc: 2500, seats: 5,
    location: 'Battambang', source: 'user', featured: false,
    seller: 'Sophal Men', phone: '+855 92 123 015',
    description: 'Reliable Nissan Navara VL with top-spec features. Leather seats, 7" touchscreen, forward collision warning, lane departure. 4WD for wet season dirt roads. Honest seller — buying a house, need cash. Can arrange delivery to Phnom Penh for serious buyer.',
    images: [
      { url: 'https://images.unsplash.com/photo-1519641471654-76ce0107ad1b?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800', primary: false, order: 1 },
    ],
    pros: ['VL top-spec — leather and all features', 'Priced significantly below market', '4WD for all Cambodia terrain', 'Seller motivated — price negotiable'],
    cons: ['Higher mileage — 69,000km', 'Located in Battambang'],
  },
  {
    title: '2023 BMW X5 xDrive40i',
    brand: 'BMW', model: 'X5', year: 2023,
    type: 'SUV', fuel: 'Gasoline', transmission: 'Automatic',
    price: 88000, estimated: 95000, label: 'Good Deal',
    mileage: 7000, color: 'Black Sapphire', cc: 3000, seats: 7,
    location: 'Phnom Penh', source: 'scraped', featured: true,
    seller: 'Euro Auto KH', phone: '+855 23 456 016',
    description: 'Near-new BMW X5 xDrive40i — the ultimate luxury SUV. 340hp inline-6, 0-100 in 5.5 seconds. BMW Live Cockpit Professional (dual 12.3" screens), Harman Kardon audio, panoramic sky lounge roof, air suspension. 7-seat configuration, massage front seats. Importer stock at below-retail price.',
    images: [
      { url: 'https://images.unsplash.com/photo-1535732820275-9a2a3f5e5d93?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1555215695-3004980ad54e?w=800', primary: false, order: 1 },
    ],
    pros: ['340hp — 0 to 100km/h in 5.5 seconds', 'Air suspension adapts to any road', 'Massage front seats + panoramic roof', 'Priced below retail for quick sale'],
    cons: ['Very high purchase price', 'Premium fuel and high maintenance costs'],
  },
  {
    title: '2020 Audi A4 2.0 TFSI S Line',
    brand: 'Audi', model: 'A4', year: 2020,
    type: 'Sedan', fuel: 'Gasoline', transmission: 'Automatic',
    price: 32000, estimated: 33000, label: 'Fair',
    mileage: 45000, color: 'Navarra Blue', cc: 2000, seats: 5,
    location: 'Phnom Penh', source: 'user', featured: false,
    seller: 'Hans Müller', phone: '+855 96 567 017',
    description: 'Sophisticated Audi A4 S Line with Quattro AWD. Virtual Cockpit 12.3" digital cluster, MMI Navigation Plus, B&O sound system, adaptive LED matrix headlights. S Line body kit gives sporty presence. German precision engineering for those who appreciate refinement.',
    images: [
      { url: 'https://images.unsplash.com/photo-1616788494707-ec28f08d05a1?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1542362567-b07e54358753?w=800', primary: false, order: 1 },
    ],
    pros: ['Quattro AWD for all-weather confidence', 'B&O premium sound system', 'Virtual Cockpit — stunning digital dash', 'S Line body — sporty European look'],
    cons: ['Audi parts expensive in Cambodia', 'Service intervals shorter than Japanese cars'],
  },
  {
    title: '2022 Isuzu D-Max 3.0 Hi-Lander 4WD',
    brand: 'Isuzu', model: 'D-Max', year: 2022,
    type: 'Pickup', fuel: 'Diesel', transmission: 'Automatic',
    price: 28000, estimated: 30000, label: 'Fair',
    mileage: 28000, color: 'Onyx Grey', cc: 3000, seats: 5,
    location: 'Siem Reap', source: 'user', featured: false,
    seller: 'Chan Virak', phone: '+855 12 456 018',
    description: 'Workhorse Isuzu D-Max 3.0 Hi-Lander — the most reliable pickup in Cambodia. 190hp diesel with 450Nm torque, 3,500kg tow capacity. 9" touchscreen, Apple CarPlay, ISUZU BIG 9 safety system. Popular with construction, agriculture, and province work. Huge parts availability nationwide.',
    images: [
      { url: 'https://images.unsplash.com/photo-1563720223185-11003d516935?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800', primary: false, order: 1 },
    ],
    pros: ['450Nm torque — outstanding towing', 'Isuzu parts available across Cambodia', 'Most reliable diesel pickup engine', '9" touchscreen with Apple CarPlay'],
    cons: ['Ride comfort less than SUV', 'Located in Siem Reap'],
  },
  {
    title: '2021 Hyundai Santa Fe 2.5T Premium AWD',
    brand: 'Hyundai', model: 'Santa Fe', year: 2021,
    type: 'SUV', fuel: 'Gasoline', transmission: 'Automatic',
    price: 34500, estimated: 38000, label: 'Good Deal',
    mileage: 23000, color: 'Creme White', cc: 2500, seats: 7,
    location: 'Phnom Penh', source: 'user', featured: false,
    seller: 'Meng Channara', phone: '+855 77 890 019',
    description: 'Family-perfect Hyundai Santa Fe 2.5 Turbo AWD with 7 seats. 281hp — more power than most competitors. Relaxation front seats (14-way powered), Bose premium sound, 8" rear entertainment displays for kids. Remote smart parking. Private sale — no dealer markup.',
    images: [
      { url: 'https://images.unsplash.com/photo-1590510296227-13d7aac29736?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1619767886558-efdc259cde1a?w=800', primary: false, order: 1 },
    ],
    pros: ['281hp — most powerful in 7-seat segment', 'Rear entertainment for children', '14-way powered relaxation front seats', 'Private sale — below dealer pricing'],
    cons: ['Hyundai lower resale than Toyota', 'Turbo petrol drinks more in traffic'],
  },
  {
    title: '2023 Toyota bZ4X Electric AWD',
    brand: 'Toyota', model: 'bZ4X', year: 2023,
    type: 'SUV', fuel: 'Electric', transmission: 'Automatic',
    price: 45000, estimated: 48000, label: 'Good Deal',
    mileage: 12000, color: 'Wind Chill Pearl', cc: null, seats: 5,
    location: 'Phnom Penh', source: 'scraped', featured: true,
    seller: 'EV Cambodia', phone: '+855 23 111 020',
    description: 'Cambodia first pure electric Toyota SUV. 218hp dual-motor AWD, 0-100 in 6.9 seconds. 71.4kWh battery — 460km real-world range. Solar charging roof adds up to 1,800km/year free. 12.3" touchscreen, Toyota Safety Sense 3.0. The future is here.',
    images: [
      { url: 'https://images.unsplash.com/photo-1628297437426-55510e68c432?w=800', primary: true,  order: 0 },
      { url: 'https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=800', primary: false, order: 1 },
    ],
    pros: ['Zero fuel cost — fully electric', 'Solar roof adds free range daily', '460km range — enough for any Cambodia trip', 'AWD with instant electric torque'],
    cons: ['Charging infrastructure still developing in Cambodia', 'Higher upfront cost vs petrol equivalent'],
  },
]

// ─── Seed runner ──────────────────────────────────────────────────────────────

async function seed() {
  console.log('Starting seed...\n')

  // 1. Lookup tables
  console.log('Inserting brands...')
  const { error: bErr } = await sb.from('brands').upsert(BRANDS, { onConflict: 'name' })
  if (bErr) { console.error('Brands:', bErr.message); process.exit(1) }

  console.log('Inserting car types...')
  const { error: tErr } = await sb.from('car_types').upsert(CAR_TYPES.map((name) => ({ name })), { onConflict: 'name' })
  if (tErr) { console.error('Car types:', tErr.message); process.exit(1) }

  console.log('Inserting fuel types...')
  const { error: fErr } = await sb.from('fuel_types').upsert(FUEL_TYPES.map((name) => ({ name })), { onConflict: 'name' })
  if (fErr) { console.error('Fuel types:', fErr.message); process.exit(1) }

  console.log('Inserting transmissions...')
  const { error: trErr } = await sb.from('transmissions').upsert(TRANSMISSIONS.map((name) => ({ name })), { onConflict: 'name' })
  if (trErr) { console.error('Transmissions:', trErr.message); process.exit(1) }

  // 2. Fetch IDs
  const { data: brands }   = await sb.from('brands').select('id, name')
  const { data: types }    = await sb.from('car_types').select('id, name')
  const { data: fuels }    = await sb.from('fuel_types').select('id, name')
  const { data: trans }    = await sb.from('transmissions').select('id, name')

  const brandMap = Object.fromEntries((brands ?? []).map((r: { id: string; name: string }) => [r.name, r.id]))
  const typeMap  = Object.fromEntries((types  ?? []).map((r: { id: string; name: string }) => [r.name, r.id]))
  const fuelMap  = Object.fromEntries((fuels  ?? []).map((r: { id: string; name: string }) => [r.name, r.id]))
  const transMap = Object.fromEntries((trans  ?? []).map((r: { id: string; name: string }) => [r.name, r.id]))

  // 3. Insert cars
  console.log('\nInserting cars...')
  let inserted = 0

  for (const car of CARS) {
    const carRow = {
      title:               car.title,
      brand_id:            brandMap[car.brand],
      model:               car.model,
      year:                car.year,
      car_type_id:         typeMap[car.type],
      fuel_type_id:        fuelMap[car.fuel],
      transmission_id:     transMap[car.transmission],
      price_usd:           car.price,
      estimated_value_usd: car.estimated,
      price_label:         car.label,
      mileage_km:          car.mileage,
      color:               car.color,
      engine_cc:           car.cc,
      seats:               car.seats,
      location:            car.location,
      description:         car.description,
      source:              car.source,
      is_featured:         car.featured,
      seller_name:         car.seller,
      seller_phone:        car.phone,
    }

    const { data: carData, error: carErr } = await sb
      .from('cars')
      .insert(carRow)
      .select('id')
      .single()

    if (carErr || !carData) {
      console.error(`  ✗ ${car.title}: ${carErr?.message}`)
      continue
    }

    const carId = carData.id

    // Images
    const { error: imgErr } = await sb.from('car_images').insert(
      car.images.map((img) => ({
        car_id: carId, url: img.url, is_primary: img.primary, display_order: img.order,
      }))
    )
    if (imgErr) console.error(`    ✗ images: ${imgErr.message}`)

    // Features
    const features = [
      ...car.pros.map((f) => ({ car_id: carId, feature: f, is_pro: true })),
      ...car.cons.map((f) => ({ car_id: carId, feature: f, is_pro: false })),
    ]
    const { error: featErr } = await sb.from('car_features').insert(features)
    if (featErr) console.error(`    ✗ features: ${featErr.message}`)

    console.log(`  ✓ ${car.title}`)
    inserted++
  }

  console.log(`\n✅ Cars: inserted ${inserted}/${CARS.length}`)

  // 4. Insert events
  console.log('\nInserting events...')
  const EVENTS = [
    {
      title: 'Phnom Penh Motor Show 2026',
      location: 'Diamond Island Convention & Exhibition Center, Phnom Penh',
      event_date: '2026-06-15T09:00:00+07:00',
      description: "Cambodia's biggest automotive showcase featuring the latest models from top brands. Test drives, special promotions, and entertainment for the whole family.",
      image_url: 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=800',
      category: 'Motor Show',
      attendee_count: 5200,
      is_published: true,
    },
    {
      title: 'Sunday Classic Car Meet',
      location: 'Riverside Park, Phnom Penh',
      event_date: '2026-06-08T07:00:00+07:00',
      description: 'Monthly gathering of classic and vintage car enthusiasts. Show off your restored classics, swap stories, and enjoy breakfast together.',
      image_url: 'https://images.unsplash.com/photo-1568605117036-5fe5e7bab0b7?w=800',
      category: 'Car Meet',
      attendee_count: 340,
      is_published: true,
    },
    {
      title: 'Siem Reap Speed Festival',
      location: 'Siem Reap Circuit, Siem Reap',
      event_date: '2026-07-20T08:00:00+07:00',
      description: 'Annual motorsport festival in Siem Reap. Drag racing, drift exhibition, and autocross competitions. Open to all skill levels.',
      image_url: 'https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?w=800',
      category: 'Racing',
      attendee_count: 1800,
      is_published: true,
    },
    {
      title: 'Electric Vehicle Showcase',
      location: 'Aeon Mall Sen Sok, Phnom Penh',
      event_date: '2026-07-28T10:00:00+07:00',
      description: 'Discover the future of mobility in Cambodia. EV test drives, charging infrastructure demos, and talks from leading EV importers.',
      image_url: 'https://images.unsplash.com/photo-1617654112368-307921291f42?w=800',
      category: 'EV Show',
      attendee_count: 920,
      is_published: true,
    },
    {
      title: 'Kampot Coastal Drive',
      location: 'Starting from Kampot Town, Kampot',
      event_date: '2026-08-12T06:30:00+07:00',
      description: 'Scenic coastal group drive from Kampot to Kep and back. Open to all car types. Beautiful route through rural Cambodia with stunning views.',
      image_url: 'https://images.unsplash.com/photo-1552519507-da3b142c6e3d?w=800',
      category: 'Group Drive',
      attendee_count: 215,
      is_published: true,
    },
    {
      title: 'Cambodia 4x4 Off-Road Challenge',
      location: 'Kirirom National Park, Kampong Speu',
      event_date: '2026-08-25T07:00:00+07:00',
      description: "The ultimate off-road adventure through Kirirom's challenging terrain. Participants must have 4WD capable vehicles. Recovery gear required.",
      image_url: 'https://images.unsplash.com/photo-1494976388531-d1058494cdd8?w=800',
      category: 'Off-Road',
      attendee_count: 156,
      is_published: true,
    },
  ]

  const { error: evErr } = await sb.from('events').upsert(EVENTS, { onConflict: 'title' })
  if (evErr) console.error('Events:', evErr.message)
  else console.log(`✅ Events: inserted ${EVENTS.length}`)

  console.log('\nNext step: run embeddings')
  console.log('  curl -X POST http://localhost:3000/api/embed')
}

seed().catch((err) => {
  console.error('Fatal:', err)
  process.exit(1)
})
