import { useEffect, useState, useRef } from 'react';
import { useWorkflowStore } from '../../hooks/useWorkflowStore';
import { API_BASE_URL } from '../../constants';

export default function LiveExecutionOverlay() {
  const {
    executionPhase,
    executionRunId,
    setExecutionPhase,
    setCurrentExecutingNodeId,
    setHitlPendingData,
    addExecutionEvent,
    setReasoningTrace,
    startNodeTimer,
    stopNodeTimer,
    nodes,
    setNodes,
  } = useWorkflowStore();
  
  const eventSourceRef = useRef<EventSource | null>(null);

  // Connect to SSE when execution starts
  useEffect(() => {
    if (executionPhase !== 'running' || !executionRunId) {
      console.log('[AUDIT] SSE useEffect early return | phase:', executionPhase, '| runId:', executionRunId);
      return;
    }

    const url = `${API_BASE_URL}/api/workflows/execute/${executionRunId}/events`;
    console.log('[AUDIT] Connecting to SSE | url:', url);
    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;
    console.log('[AUDIT] EventSource created for:', executionRunId);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('[AUDIT] SSE message received | type:', data.type, '| nodeId:', data.nodeId);
        
        if (data.type === 'heartbeat') {
          console.log('[AUDIT] Heartbeat received');
          return;
        }

        addExecutionEvent({
          type: data.type,
          nodeId: data.nodeId,
          timestamp: Date.now(),
          data,
        });

        switch (data.type) {
          case 'node_started':
            console.log('[AUDIT] Node started:', data.nodeId);
            setCurrentExecutingNodeId(data.nodeId);
            startNodeTimer(data.nodeId);
            // Update node visual status
            setNodes(nodes.map(n => 
              n.id === data.nodeId 
                ? { ...n, data: { ...n.data, status: 'running' } }
                : n
            ));
            break;

          case 'node_completed':
            console.log('[AUDIT] Node completed:', data.nodeId);
            stopNodeTimer(data.nodeId);
            setNodes(nodes.map(n =>
              n.id === data.nodeId
                ? { ...n, data: { ...n.data, status: 'success', executionOutput: data.output } }
                : n
            ));
            if (data.reasoning) {
              setReasoningTrace(data.nodeId, data.reasoning);
            }
            break;

          case 'node_error':
            console.log('[AUDIT] Node error:', data.nodeId, '| error:', data.error);
            stopNodeTimer(data.nodeId);
            setNodes(nodes.map(n =>
              n.id === data.nodeId
                ? { ...n, data: { ...n.data, status: 'error', executionOutput: data.error } }
                : n
            ));
            break;

          case 'hitl_required':
            console.log('[AUDIT] HITL required');
            setHitlPendingData({
              nodeId: data.nodeId,
              nodeName: data.nodeName || 'Intervention',
              action_description: data.action_description || '',
              reasoning: data.reasoning || '',
              current_state_summary: data.current_state_summary || '',
              options: data.options || [
                { label: 'Approve', value: 'approve' },
                { label: 'Reject', value: 'reject' },
              ],
            });
            break;

          case 'workflow_completed':
            console.log('[AUDIT] Workflow completed');
            setExecutionPhase('completed');
            setCurrentExecutingNodeId(null);
            // Auto hide after 3 seconds
            setTimeout(() => setExecutionPhase('idle'), 3000);
            break;

          case 'workflow_failed':
            console.log('[AUDIT] Workflow failed');
            setExecutionPhase('failed');
            setCurrentExecutingNodeId(null);
            break;
        }
      } catch (e) {
        console.error('[AUDIT] SSE parse error:', e);
      }
    };

    eventSource.onerror = () => {
      console.warn('[AUDIT] SSE connection lost for:', executionRunId);
      eventSource.close();
    };

    return () => {
      console.log('[AUDIT] Closing SSE connection for:', executionRunId);
      eventSource.close();
      eventSourceRef.current = null;
    };
  }, [executionPhase, executionRunId]);

  if (executionPhase === 'idle') return null;

  return (
    <div style={{
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      zIndex: 100,
      pointerEvents: 'none',
    }}>
      {/* Execution phase indicator */}
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        padding: '8px',
        pointerEvents: 'auto',
      }}>
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '8px',
          padding: '6px 16px',
          borderRadius: '20px',
          fontSize: '12px',
          fontWeight: 600,
          background: executionPhase === 'running'
            ? 'rgba(139, 92, 246, 0.2)'
            : executionPhase === 'paused_hitl'
            ? 'rgba(245, 158, 11, 0.2)'
            : executionPhase === 'completed'
            ? 'rgba(34, 197, 94, 0.2)'
            : 'rgba(239, 68, 68, 0.2)',
          border: `1px solid ${
            executionPhase === 'running' ? '#8b5cf6'
            : executionPhase === 'paused_hitl' ? '#f59e0b'
            : executionPhase === 'completed' ? '#22c55e'
            : '#ef4444'
          }`,
          color: '#fff',
          backdropFilter: 'blur(8px)',
        }}>
          {executionPhase === 'running' && (
            <span className="animate-pulse" style={{ width: 8, height: 8, borderRadius: '50%', background: '#8b5cf6', display: 'inline-block' }} />
          )}
          {executionPhase === 'running' ? '⚡ Executing Workflow...'
            : executionPhase === 'paused_hitl' ? '⏸ Waiting for Approval'
            : executionPhase === 'completed' ? '✅ Completed'
            : '❌ Failed'}
        </div>
      </div>
    </div>
  );
}
