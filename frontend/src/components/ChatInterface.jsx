import React, { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'

const API_BASE = 'http://localhost:8000'

export default function ChatInterface() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [image, setImage] = useState(null)
  const [imagePreview, setImagePreview] = useState(null)
  const [loading, setLoading] = useState(false)
  const [sessionId] = useState(() => Math.random().toString(36).substring(2, 10))
  const messagesEndRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleImageSelect = (e) => {
    const file = e.target.files[0]
    if (file) {
      setImage(file)
      const reader = new FileReader()
      reader.onload = (ev) => setImagePreview(ev.target.result)
      reader.readAsDataURL(file)
    }
  }

  const removeImage = () => {
    setImage(null)
    setImagePreview(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const sendMessage = async () => {
    const text = input.trim()
    if (!text && !image) return

    // Add user message to chat
    const userMsg = {
      role: 'user',
      content: text || '📷 [Photo]',
      image: imagePreview,
      timestamp: new Date().toLocaleTimeString(),
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const formData = new FormData()
      formData.append('message', text || 'Here is a photo of my meal')
      formData.append('session_id', sessionId)
      if (image) formData.append('image', image)

      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        body: formData,
      })

      if (!res.ok) {
        throw new Error(`Server error: ${res.status}`)
      }

      const data = await res.json()

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.response,
          latency: data.latency_ms,
          timestamp: new Date().toLocaleTimeString(),
        },
      ])
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `❌ Error: ${err.message}. Make sure the backend is running on port 8000.`,
          timestamp: new Date().toLocaleTimeString(),
        },
      ])
    } finally {
      setLoading(false)
      removeImage()
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div style={containerStyle}>
      {/* Messages */}
      <div style={messagesContainerStyle}>
        {messages.length === 0 && (
          <div style={emptyStateStyle}>
            <p style={{ fontSize: '2rem', margin: 0 }}>👋</p>
            <p style={{ color: '#666' }}>
              Tell me what you ate! Try:
            </p>
            <div style={suggestionsStyle}>
              {['had 2 parathas and chai', 'how am I doing on calories?', "i'm vegetarian btw"].map((s) => (
                <button
                  key={s}
                  style={suggestionBtnStyle}
                  onClick={() => { setInput(s); }}
                >
                  "{s}"
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              ...messageBubbleStyle,
              alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
              backgroundColor: msg.role === 'user' ? '#e94560' : '#fff',
              color: msg.role === 'user' ? '#fff' : '#333',
            }}
          >
            {msg.image && (
              <img
                src={msg.image}
                alt="Uploaded food"
                style={{ maxWidth: '200px', borderRadius: '8px', marginBottom: '8px' }}
              />
            )}
            <div style={{ whiteSpace: 'pre-wrap' }}>
              <ReactMarkdown
                components={{
                  p: ({node, ...props}) => <p style={{ margin: '0 0 8px 0' }} {...props} />,
                  ul: ({node, ...props}) => <ul style={{ margin: '0 0 8px 0', paddingLeft: '20px' }} {...props} />,
                  li: ({node, ...props}) => <li style={{ margin: '4px 0' }} {...props} />
                }}
              >
                {msg.content}
              </ReactMarkdown>
            </div>
            <div
              style={{
                fontSize: '0.7rem',
                opacity: 0.6,
                marginTop: '4px',
                textAlign: 'right',
              }}
            >
              {msg.timestamp}
              {msg.latency != null && ` · ${Math.round(msg.latency)}ms`}
            </div>
          </div>
        ))}

        {loading && (
          <div style={{ ...messageBubbleStyle, alignSelf: 'flex-start', backgroundColor: '#fff' }}>
            <span style={typingStyle}>CalorAI is thinking...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Image preview */}
      {imagePreview && (
        <div style={imagePreviewContainerStyle}>
          <img src={imagePreview} alt="Preview" style={{ height: '60px', borderRadius: '6px' }} />
          <button onClick={removeImage} style={removeImgBtnStyle}>✕</button>
        </div>
      )}

      {/* Input area */}
      <div style={inputContainerStyle}>
        <input
          type="file"
          ref={fileInputRef}
          accept="image/*"
          style={{ display: 'none' }}
          onChange={handleImageSelect}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          style={iconBtnStyle}
          title="Attach photo"
        >
          📷
        </button>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Tell me what you ate..."
          disabled={loading}
          style={textInputStyle}
        />
        <button
          onClick={sendMessage}
          disabled={loading || (!input.trim() && !image)}
          style={{
            ...sendBtnStyle,
            opacity: loading || (!input.trim() && !image) ? 0.5 : 1,
          }}
        >
          ↑
        </button>
      </div>
    </div>
  )
}

// ── Styles ──────────────────────────────────────────────────────────────────

const containerStyle = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const messagesContainerStyle = {
  flex: 1,
  overflowY: 'auto',
  padding: '16px',
  display: 'flex',
  flexDirection: 'column',
  gap: '12px',
}

const emptyStateStyle = {
  textAlign: 'center',
  padding: '40px 20px',
  alignSelf: 'center',
}

const suggestionsStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: '8px',
  marginTop: '12px',
}

const suggestionBtnStyle = {
  padding: '8px 16px',
  border: '1px solid #ddd',
  borderRadius: '20px',
  backgroundColor: '#fff',
  cursor: 'pointer',
  fontSize: '0.9rem',
  color: '#555',
  transition: 'all 0.2s',
}

const messageBubbleStyle = {
  maxWidth: '75%',
  padding: '10px 14px',
  borderRadius: '16px',
  boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
  fontSize: '0.95rem',
  lineHeight: 1.4,
}

const typingStyle = {
  color: '#999',
  fontStyle: 'italic',
}

const imagePreviewContainerStyle = {
  padding: '8px 16px',
  backgroundColor: '#fff',
  borderTop: '1px solid #eee',
  display: 'flex',
  alignItems: 'center',
  gap: '8px',
}

const removeImgBtnStyle = {
  background: '#e94560',
  color: '#fff',
  border: 'none',
  borderRadius: '50%',
  width: '24px',
  height: '24px',
  cursor: 'pointer',
  fontSize: '0.8rem',
}

const inputContainerStyle = {
  padding: '12px 16px',
  backgroundColor: '#fff',
  borderTop: '1px solid #eee',
  display: 'flex',
  gap: '8px',
  alignItems: 'center',
}

const iconBtnStyle = {
  background: 'none',
  border: 'none',
  fontSize: '1.4rem',
  cursor: 'pointer',
  padding: '4px',
}

const textInputStyle = {
  flex: 1,
  padding: '10px 14px',
  border: '1px solid #ddd',
  borderRadius: '24px',
  fontSize: '1rem',
  outline: 'none',
}

const sendBtnStyle = {
  width: '36px',
  height: '36px',
  borderRadius: '50%',
  border: 'none',
  backgroundColor: '#e94560',
  color: '#fff',
  fontSize: '1.2rem',
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
}
