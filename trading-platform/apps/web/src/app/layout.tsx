import type { Metadata } from 'next'
import Navbar from '@/components/Navbar'
import './globals.css'

export const metadata: Metadata = {
  title: 'Quant Trading Platform',
  description: 'AI-Powered Quantitative Stock Trading Research Platform',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>
        <Navbar />
        <div className="mx-auto min-h-[calc(100vh-65px)] max-w-[1500px] px-4 py-8 lg:px-8 lg:py-10">{children}</div>
        <footer className="border-t border-white/5 px-4 py-5 text-center text-xs text-muted-foreground">Quant Console · Research software only · Historical performance does not guarantee future results</footer>
      </body>
    </html>
  )
}
