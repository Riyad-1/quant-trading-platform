import type { Metadata } from 'next'

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
      <body>{children}</body>
    </html>
  )
}
