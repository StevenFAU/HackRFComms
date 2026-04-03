export default function StatusIndicator({ connected, label }) {
  return (
    <span className="flex items-center gap-2">
      <span className={`w-2.5 h-2.5 rounded-full ${connected ? 'bg-green-400' : 'bg-red-500'}`} />
      <span className="text-sm font-mono text-gray-300">{label}</span>
    </span>
  )
}
