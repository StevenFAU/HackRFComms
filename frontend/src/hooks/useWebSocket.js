import { useEffect, useRef, useState, useCallback } from 'react'

export function useWebSocket(url) {
  const [messages, setMessages] = useState([])
  const [connected, setConnected] = useState(false)
  const ws = useRef(null)
  const shouldConnect = useRef(false)

  const connect = useCallback(() => {
    shouldConnect.current = true
    const socket = new WebSocket(url)
    ws.current = socket

    socket.onopen = () => setConnected(true)
    socket.onclose = () => {
      setConnected(false)
      if (shouldConnect.current) setTimeout(connect, 2000)
    }
    socket.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        setMessages(prev => [...prev.slice(-99), { ...data, id: Date.now() }])
      } catch {}
    }
  }, [url])

  const disconnect = useCallback(() => {
    shouldConnect.current = false
    ws.current?.close()
  }, [])

  useEffect(() => () => { shouldConnect.current = false; ws.current?.close() }, [])

  return { messages, connected, connect, disconnect }
}
