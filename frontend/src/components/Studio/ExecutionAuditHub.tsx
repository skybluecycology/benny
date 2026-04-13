import { useEffect, useRef, useState, useMemo } from 'react';
import { useWorkflowStore } from '../../hooks/useWorkflowStore';
import type { ExecutionEvent } from '../../hooks/useWorkflowStore';

export default function ExecutionAuditHub() {
  const { isAuditHubOpen, toggleAuditHub } = useWorkflowStore();
  const executionEvents = useWorkflowStore((state) => state.executionEvents);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [filter, setFilter] = useState<string | null>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [executionEvents]);

  if (!isAuditHubOpen) return null;
  
  // Memoize filtering and stats to prevent redundant calculations
  const filteredEvents = useMemo(() => 
    filter ? executionEvents.filter(e => e.type === filter) : executionEvents,
    [executionEvents, filter]
  );

  const totalTokens = useMemo(() => 
    executionEvents
      .filter(e => e.type === 'resource_usage')
      .reduce((acc, e) => acc + (e.data?.usage?.total_tokens || 0), 0),
    [executionEvents]
  );
  
  const toolCount = useMemo(() => 
    executionEvents.filter(e => e.type === 'tool_used').length,
    [executionEvents]
  );

  return (
    <div className="execution-audit-hub" style={{
      position: 'fixed',
      bottom: 0,
      left: 0,
      right: 0,
      height: '30vh',
      background: 'rgba(10, 10, 18, 0.95)',
      backdropFilter: 'blur(16px)',
      borderTop: '1px solid var(--border-active)',
      zIndex: 1000,
      display: 'flex',
      flexDirection: 'column',
      fontFamily: '"Fira Code", monospace',
      boxShadow: '0 -10px 40px rgba(0,0,0,0.5)',
      animation: 'slideUp 0.3s ease-out',
    }}>
      {/* Header / Toolbar */}
      <div style={{
        padding: '8px 16px',
        background: 'rgba(255,255,255,0.03)',
        borderBottom: '1px solid rgba(255,255,255,0.05)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        fontSize: '11px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span style={{ color: 'var(--primary)', fontWeight: 600 }}>TERMINAL :: EXECUTION_AUDIT</span>
          
          <div style={{ display: 'flex', gap: '8px', opacity: 0.8 }}>
             <span title="Total Tokens Used">💎 {totalTokens.toLocaleString()} tokens</span>
             <span title="Tools Invocations">🛠 {toolCount} tools</span>
          </div>

          <div style={{ display: 'flex', gap: '4px', marginLeft: '12px' }}>
            {['node_progress', 'tool_used', 'resource_usage'].map(f => (
              <button 
                key={f}
                onClick={() => setFilter(filter === f ? null : f)}
                style={{
                  padding: '2px 8px',
                  borderRadius: '4px',
                  background: filter === f ? 'var(--primary)' : 'rgba(255,255,255,0.05)',
                  border: 'none',
                  color: '#fff',
                  fontSize: '9px',
                  cursor: 'pointer'
                }}
              >
                {f.replace('_', ' ').toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <button onClick={toggleAuditHub} style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', opacity: 0.5 }}>
          ✕
        </button>
      </div>

      {/* Log Stream */}
      <div 
        ref={scrollRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '12px',
          fontSize: '11px',
          lineHeight: '1.5',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
        }}
      >
        {filteredEvents.length === 0 && (
          <div style={{ color: 'rgba(255,255,255,0.2)', textAlign: 'center', marginTop: '20px' }}>
            Listening for execution events...
          </div>
        )}
        
        {filteredEvents.map((event, i) => (
          <div key={i} style={{ display: 'flex', gap: '12px', animation: 'fadeIn 0.2s ease-out' }}>
            <span style={{ color: 'rgba(255,255,255,0.3)', minWidth: '70px' }}>
              [{new Date(event.timestamp).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}]
            </span>
            
            <EventItem event={event} />
          </div>
        ))}
      </div>

      <style>{`
        @keyframes slideUp {
          from { transform: translateY(100%); }
          to { transform: translateY(0); }
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
      `}</style>
    </div>
  );
}

function EventItem({ event }: { event: ExecutionEvent }) {
  switch (event.type) {
    case 'node_progress':
      return (
        <span style={{ color: '#e2e8f0' }}>
          <span style={{ color: '#8b5cf6' }}>PROG</span> [{event.nodeId}] {event.data?.message}
        </span>
      );
    case 'tool_used':
      return (
        <span style={{ color: '#fab005' }}>
          <span style={{ color: '#fab005', fontWeight: 600 }}>TOOL</span> [{event.nodeId}] call <span style={{ color: '#fff' }}>{event.data?.tool_name}</span>({JSON.stringify(event.data?.args)})
        </span>
      );
    case 'resource_usage':
      return (
        <span style={{ color: '#63e6be' }}>
          <span style={{ color: '#63e6be' }}>UTIL</span> {event.data?.model} :: {event.data?.usage?.total_tokens} tokens / {event.data?.duration_ms}ms
        </span>
      );
    case 'node_error':
      return (
        <span style={{ color: '#ff6b6b' }}>
          <span style={{ color: '#ff6b6b', fontWeight: 600 }}>ERR!</span> [{event.nodeId}] {event.data?.error}
        </span>
      );
    default:
      return (
        <span style={{ color: 'rgba(255,255,255,0.5)' }}>
          <span style={{ color: 'rgba(255,255,255,0.5)' }}>INFO</span> [{event.nodeId}] {event.type}
        </span>
      );
  }
}
