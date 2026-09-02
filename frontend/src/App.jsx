import React from 'react'
import ChatInterface from './components/ChatInterface'

const appStyle = {
  maxWidth: '800px',
  margin: '0 auto',
  height: '100vh',
  display: 'flex',
  flexDirection: 'column',
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  backgroundColor: '#f5f5f5',
}

const headerStyle = {
  padding: '16px 24px',
  backgroundColor: '#1a1a2e',
  color: '#fff',
  textAlign: 'center',
  borderBottom: '3px solid #e94560',
}

export default function App() {
  return (
    <div style={appStyle}>
      <header style={headerStyle}>
        <h1 style={{ margin: 0, fontSize: '1.5rem' }}>🍽️ CalorAI Chat</h1>
        <p style={{ margin: '4px 0 0', fontSize: '0.85rem', opacity: 0.8 }}>
          Log your meals naturally — just text or send a photo
        </p>
      </header>
      <ChatInterface />
    </div>
  )
}
