'use client'

import { useState, useEffect } from 'react'
import { Plus, Minus, CheckCircle } from 'lucide-react'
import { estimatePrice, getPriceLabel } from '@/lib/priceEstimation'
import Input from '@/components/ui/Input'
import Button from '@/components/ui/Button'
import Badge from '@/components/ui/Badge'

const makes = ['Toyota', 'Honda', 'Lexus', 'BMW', 'Mercedes', 'Hyundai', 'Kia', 'Ford', 'Other']
const types = ['Sedan', 'SUV', 'Truck', 'Hatchback', 'Van', 'Coupe']
const locations = ['Phnom Penh', 'Siem Reap', 'Battambang', 'Kampot', 'Sihanoukville', 'Other']

export default function SubmitPage() {
  const [submitted, setSubmitted] = useState(false)
  const [pros, setPros] = useState([''])
  const [cons, setCons] = useState([''])
  const [estimatedValue, setEstimatedValue] = useState<number | null>(null)
  const [priceLabel, setPriceLabel] = useState<'Good Deal' | 'Fair' | 'Overpriced' | null>(null)

  const [form, setForm] = useState({
    make: '',
    model: '',
    year: '',
    price: '',
    mileage: '',
    type: '',
    location: '',
    description: '',
    sellerName: '',
    sellerPhone: '',
    imageUrl: '',
  })

  // Real-time price estimation
  useEffect(() => {
    if (form.make && form.year && form.mileage && form.price) {
      const year = parseInt(form.year)
      const mileage = parseInt(form.mileage)
      const price = parseInt(form.price)
      if (!isNaN(year) && !isNaN(mileage) && !isNaN(price)) {
        const est = estimatePrice(form.make, form.model, year, mileage)
        setEstimatedValue(est)
        setPriceLabel(getPriceLabel(price, est))
      }
    } else {
      setEstimatedValue(null)
      setPriceLabel(null)
    }
  }, [form.make, form.model, form.year, form.mileage, form.price])

  const handleFormChange = (key: string, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitted(true)
  }

  const updatePro = (idx: number, value: string) => {
    const updated = [...pros]
    updated[idx] = value
    setPros(updated)
  }

  const updateCon = (idx: number, value: string) => {
    const updated = [...cons]
    updated[idx] = value
    setCons(updated)
  }

  if (submitted) {
    return (
      <div className="min-h-screen bg-[#F8F5F0] flex items-center justify-center px-4">
        <div className="bg-white rounded-3xl shadow-lg border border-gray-100 p-10 max-w-md w-full text-center">
          <div className="w-16 h-16 rounded-full bg-emerald-50 flex items-center justify-center mx-auto mb-5">
            <CheckCircle className="w-9 h-9 text-emerald-500" />
          </div>
          <h2 className="text-2xl font-black text-[#1A1A1A] mb-3">Listing Submitted!</h2>
          <p className="text-gray-500 text-sm leading-relaxed mb-6">
            Your car listing has been received and will be reviewed by our team. You&apos;ll be
            notified once it goes live on MonoCars.
          </p>
          <Button variant="primary" size="lg" fullWidth onClick={() => setSubmitted(false)}>
            Submit Another
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#F8F5F0]">
      {/* Header */}
      <div className="bg-[#1A1A1A] py-12 md:py-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-[#CBA135] text-sm font-semibold uppercase tracking-wider mb-2">
            List Your Car
          </p>
          <h1 className="text-3xl md:text-4xl font-black text-white">Submit a Listing</h1>
          <p className="text-gray-400 mt-2 text-sm">
            Get smart pricing insights and reach thousands of buyers across Cambodia
          </p>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <form onSubmit={handleSubmit} className="space-y-8">
          {/* Car Information */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="font-bold text-[#1A1A1A] text-lg mb-5 pb-4 border-b border-gray-100">
              Car Information
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              {/* Make */}
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-[#1A1A1A]">Make *</label>
                <div className="relative">
                  <select
                    value={form.make}
                    onChange={(e) => handleFormChange('make', e.target.value)}
                    required
                    className="w-full px-4 py-2.5 rounded-xl border border-gray-200 text-[#1A1A1A] bg-white text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-[#CBA135] focus:border-[#CBA135]"
                  >
                    <option value="">Select Make</option>
                    {makes.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                  <div className="pointer-events-none absolute inset-y-0 right-3 flex items-center">
                    <svg className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </div>
              </div>

              <Input
                label="Model *"
                placeholder="e.g. Camry, CR-V, 3 Series"
                value={form.model}
                onChange={(e) => handleFormChange('model', e.target.value)}
                required
              />

              <Input
                label="Year *"
                type="number"
                placeholder="e.g. 2020"
                min="1990"
                max="2025"
                value={form.year}
                onChange={(e) => handleFormChange('year', e.target.value)}
                required
              />

              <Input
                label="Asking Price (USD) *"
                type="number"
                placeholder="e.g. 18500"
                min="500"
                value={form.price}
                onChange={(e) => handleFormChange('price', e.target.value)}
                required
              />

              <Input
                label="Mileage (km) *"
                type="number"
                placeholder="e.g. 45000"
                min="0"
                value={form.mileage}
                onChange={(e) => handleFormChange('mileage', e.target.value)}
                required
              />

              {/* Type */}
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-[#1A1A1A]">Car Type *</label>
                <div className="relative">
                  <select
                    value={form.type}
                    onChange={(e) => handleFormChange('type', e.target.value)}
                    required
                    className="w-full px-4 py-2.5 rounded-xl border border-gray-200 text-[#1A1A1A] bg-white text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-[#CBA135] focus:border-[#CBA135]"
                  >
                    <option value="">Select Type</option>
                    {types.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                  <div className="pointer-events-none absolute inset-y-0 right-3 flex items-center">
                    <svg className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </div>
              </div>

              {/* Location */}
              <div className="flex flex-col gap-1.5 sm:col-span-2">
                <label className="text-sm font-medium text-[#1A1A1A]">Location *</label>
                <div className="relative">
                  <select
                    value={form.location}
                    onChange={(e) => handleFormChange('location', e.target.value)}
                    required
                    className="w-full px-4 py-2.5 rounded-xl border border-gray-200 text-[#1A1A1A] bg-white text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-[#CBA135] focus:border-[#CBA135]"
                  >
                    <option value="">Select Location</option>
                    {locations.map((l) => (
                      <option key={l} value={l}>{l}</option>
                    ))}
                  </select>
                  <div className="pointer-events-none absolute inset-y-0 right-3 flex items-center">
                    <svg className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </div>
              </div>
            </div>

            {/* Price Estimation Preview */}
            {estimatedValue !== null && priceLabel !== null && (
              <div className="mt-5 p-4 bg-gray-50 rounded-xl border border-gray-200">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
                  Real-Time Price Estimate
                </p>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div>
                      <p className="text-xs text-gray-400">Estimated Market Value</p>
                      <p className="text-lg font-black text-[#CBA135]">
                        ${estimatedValue.toLocaleString()}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-400">Your Price</p>
                      <p className="text-lg font-black text-[#1A1A1A]">
                        ${parseInt(form.price).toLocaleString()}
                      </p>
                    </div>
                  </div>
                  <Badge label={priceLabel} />
                </div>
              </div>
            )}
          </div>

          {/* Description */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="font-bold text-[#1A1A1A] text-lg mb-5 pb-4 border-b border-gray-100">
              Description
            </h2>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-[#1A1A1A]">Car Description *</label>
              <textarea
                placeholder="Describe your car in detail — condition, history, features, why you're selling..."
                rows={4}
                value={form.description}
                onChange={(e) => handleFormChange('description', e.target.value)}
                required
                className="w-full px-4 py-2.5 rounded-xl border border-gray-200 text-[#1A1A1A] bg-white text-sm focus:outline-none focus:ring-2 focus:ring-[#CBA135] focus:border-[#CBA135] resize-none placeholder:text-gray-400"
              />
            </div>
          </div>

          {/* Pros & Cons */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="font-bold text-[#1A1A1A] text-lg mb-5 pb-4 border-b border-gray-100">
              Pros &amp; Cons
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              {/* Pros */}
              <div>
                <p className="text-sm font-semibold text-emerald-700 mb-3">Pros</p>
                <div className="space-y-2">
                  {pros.map((pro, idx) => (
                    <div key={idx} className="flex gap-2">
                      <input
                        type="text"
                        value={pro}
                        onChange={(e) => updatePro(idx, e.target.value)}
                        placeholder={`Pro ${idx + 1}`}
                        className="flex-1 px-3 py-2 text-sm rounded-xl border border-gray-200 focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:border-emerald-400"
                      />
                      {pros.length > 1 && (
                        <button
                          type="button"
                          onClick={() => setPros(pros.filter((_, i) => i !== idx))}
                          className="p-2 text-gray-400 hover:text-red-500 transition-colors"
                        >
                          <Minus className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  ))}
                  {pros.length < 6 && (
                    <button
                      type="button"
                      onClick={() => setPros([...pros, ''])}
                      className="flex items-center gap-1.5 text-xs text-emerald-600 hover:text-emerald-700 transition-colors mt-1"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Add Pro
                    </button>
                  )}
                </div>
              </div>

              {/* Cons */}
              <div>
                <p className="text-sm font-semibold text-red-700 mb-3">Cons</p>
                <div className="space-y-2">
                  {cons.map((con, idx) => (
                    <div key={idx} className="flex gap-2">
                      <input
                        type="text"
                        value={con}
                        onChange={(e) => updateCon(idx, e.target.value)}
                        placeholder={`Con ${idx + 1}`}
                        className="flex-1 px-3 py-2 text-sm rounded-xl border border-gray-200 focus:outline-none focus:ring-2 focus:ring-red-300 focus:border-red-300"
                      />
                      {cons.length > 1 && (
                        <button
                          type="button"
                          onClick={() => setCons(cons.filter((_, i) => i !== idx))}
                          className="p-2 text-gray-400 hover:text-red-500 transition-colors"
                        >
                          <Minus className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  ))}
                  {cons.length < 6 && (
                    <button
                      type="button"
                      onClick={() => setCons([...cons, ''])}
                      className="flex items-center gap-1.5 text-xs text-red-600 hover:text-red-700 transition-colors mt-1"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Add Con
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Contact Info */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="font-bold text-[#1A1A1A] text-lg mb-5 pb-4 border-b border-gray-100">
              Contact Information
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              <Input
                label="Your Name *"
                placeholder="Full name"
                value={form.sellerName}
                onChange={(e) => handleFormChange('sellerName', e.target.value)}
                required
              />
              <Input
                label="Phone Number *"
                type="tel"
                placeholder="+855 12 345 678"
                value={form.sellerPhone}
                onChange={(e) => handleFormChange('sellerPhone', e.target.value)}
                required
              />
            </div>
          </div>

          {/* Images */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="font-bold text-[#1A1A1A] text-lg mb-5 pb-4 border-b border-gray-100">
              Images
            </h2>
            <Input
              label="Image URL"
              type="url"
              placeholder="https://example.com/car-photo.jpg"
              value={form.imageUrl}
              onChange={(e) => handleFormChange('imageUrl', e.target.value)}
              helperText="Paste a direct link to your car photo (from Google Drive, Imgur, etc.)"
            />
            {form.imageUrl && (
              <div className="mt-3 rounded-xl overflow-hidden aspect-video max-w-sm">
                <img
                  src={form.imageUrl}
                  alt="Preview"
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    ;(e.target as HTMLImageElement).style.display = 'none'
                  }}
                />
              </div>
            )}
          </div>

          {/* Submit */}
          <div className="flex items-center justify-between bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <p className="text-xs text-gray-500 max-w-xs">
              By submitting, you agree to our terms of service. Listings are reviewed within 24 hours.
            </p>
            <Button type="submit" variant="primary" size="lg">
              Submit Listing
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
