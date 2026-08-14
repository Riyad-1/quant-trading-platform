'use client'

import { useEffect, useState } from 'react'
import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function Home() {
  const [healthStatus, setHealthStatus] = useState<string>('Checking...')
  const [apiInfo, setApiInfo] = useState<any>(null)

  useEffect(() => {
    // Check API health
    axios.get(`${API_URL}/api/v1/health`)
      .then((res) => setHealthStatus(`Connected: ${res.data.database}`))
      .catch((err) => setHealthStatus(`Error: ${err.message}`))

    // Get API info
    axios.get(`${API_URL}/`)
      .then((res) => setApiInfo(res.data))
      .catch((err) => console.error('API error:', err))
  }, [])

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-4xl mx-auto">
        <header className="mb-8">
          <h1 className="text-4xl font-bold text-primary mb-2">
            Quant Trading Platform
          </h1>
          <p className="text-muted-foreground">
            AI-Powered Quantitative Stock Trading Research
          </p>
        </header>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 mb-8">
          {/* Status Card */}
          <div className="border rounded-lg p-6 bg-card">
            <h3 className="font-semibold mb-2">API Status</h3>
            <p className={`text-sm ${healthStatus.includes('Connected') ? 'text-green-600' : 'text-red-600'}`}>
              {healthStatus}
            </p>
          </div>

          {/* Version Card */}
          <div className="border rounded-lg p-6 bg-card">
            <h3 className="font-semibold mb-2">Version</h3>
            <p className="text-sm text-muted-foreground">
              {apiInfo?.version || 'Loading...'}
            </p>
          </div>

          {/* Phase Card */}
          <div className="border rounded-lg p-6 bg-card">
            <h3 className="font-semibold mb-2">Current Phase</h3>
            <p className="text-sm text-muted-foreground">
              Phase 1 - Foundation
            </p>
          </div>
        </div>

        <div className="border rounded-lg p-6 bg-card">
          <h2 className="text-2xl font-semibold mb-4">Platform Overview</h2>

          <div className="space-y-4">
            <section>
              <h3 className="font-medium mb-2">What&apos;s Implemented</h3>
              <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                <li>Project architecture and folder structure</li>
                <li>PostgreSQL + TimescaleDB database schema</li>
                <li>FastAPI backend with CRUD endpoints</li>
                <li>Celery worker setup for background tasks</li>
                <li>Docker Compose configuration</li>
                <li>Next.js frontend scaffolding</li>
              </ul>
            </section>

            <section>
              <h3 className="font-medium mb-2">Coming in Phase 2</h3>
              <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                <li>Market data ingestion pipeline</li>
                <li>Technical indicator calculations</li>
                <li>Stock scanner and ranking system</li>
                <li>Opportunity dashboard</li>
              </ul>
            </section>

            <section>
              <h3 className="font-medium mb-2">Key Features (Planned)</h3>
              <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                <li>Momentum, breakout, and relative strength strategies</li>
                <li>Market regime detection</li>
                <li>News sentiment analysis with LLM</li>
                <li>ML-based stock ranking</li>
                <li>Backtesting with SPY benchmark</li>
                <li>Paper trading simulation</li>
                <li>Portfolio intelligence and risk management</li>
              </ul>
            </section>
          </div>
        </div>

        <div className="mt-8 border rounded-lg p-6 bg-card">
          <h2 className="text-2xl font-semibold mb-4">Quick Links</h2>
          <div className="grid gap-4 md:grid-cols-2">
            <a
              href={`${API_URL}/docs`}
              target="_blank"
              className="flex items-center p-4 border rounded-lg hover:bg-accent transition-colors"
            >
              <div>
                <h3 className="font-medium">API Documentation</h3>
                <p className="text-sm text-muted-foreground">Swagger UI for REST API</p>
              </div>
            </a>

            <a
              href={`${API_URL}/health`}
              target="_blank"
              className="flex items-center p-4 border rounded-lg hover:bg-accent transition-colors"
            >
              <div>
                <h3 className="font-medium">Health Check</h3>
                <p className="text-sm text-muted-foreground">API status endpoint</p>
              </div>
            </a>
          </div>
        </div>
      </div>
    </main>
  )
}
