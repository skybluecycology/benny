import { useState, useEffect } from 'react';
import { RefreshCw, CheckCircle2, XCircle, Clock, Loader2, ExternalLink, Copy } from 'lucide-react';
import { API_BASE_URL, GOVERNANCE_HEADERS } from '../../constants';

interface TaskItem {
  task_id: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  skill_hint?: string;
}

interface PartialResult {
  task_id: string;
  content?: string;
  error?: string;
  execution_time_ms: number;
}

interface SwarmExecutionState {
  execution_id: string;
  status: 'pending' | 'planning' | 'executing' | 'aggregating' | 'completed' | 'partial_success' | 'failed';
  plan?: TaskItem[];
  partial_results?: PartialResult[];
  artifact_path?: string;
  governance_url?: string;
  errors?: string[];
}

interface SwarmStatePanelProps {
  executionId: string | null;
}

const API_BASE = API_BASE_URL;

export default function SwarmStatePanel({ executionId }: SwarmStatePanelProps) {
  const [state, setState] = useState<SwarmExecutionState | null>(null);
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchState = async () => {
    if (!executionId) return;
    
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/workflow/${executionId}/status`, {
        headers: { ...GOVERNANCE_HEADERS }
      });
      if (response.ok) {
        const data = await response.json();
        setState(data);
        
        // Stop auto-refresh if completed
        if (['completed', 'partial_success', 'failed'].includes(data.status)) {
          setAutoRefresh(false);
        }
      }
    } catch (error) {
      console.error('Failed to fetch swarm state:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (executionId) {
      fetchState();
    }
  }, [executionId]);

  useEffect(() => {
    if (!autoRefresh || !executionId) return;
    
    const interval = setInterval(fetchState, 2000);
    return () => clearInterval(interval);
  }, [autoRefresh, executionId]);

  if (!executionId) {
    return (
      <div className="swarm-state-panel empty">
        <div className="empty-state">
          <Clock size={32} />
          <p>No active swarm execution</p>
          <span>Execute a swarm workflow to see live state</span>
        </div>
      </div>
    );
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 size={16} className="status-success" />;
      case 'failed':
        return <XCircle size={16} className="status-error" />;
      case 'running':
      case 'planning':
      case 'executing':
      case 'aggregating':
        return <Loader2 size={16} className="status-running spin" />;
      default:
        return <Clock size={16} className="status-pending" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'var(--success)';
      case 'partial_success': return 'var(--warning)';
      case 'failed': return 'var(--error)';
      case 'running':
      case 'planning':
      case 'executing':
      case 'aggregating':
        return 'var(--primary)';
      default: return 'var(--text-secondary)';
    }
  };

  const completedCount = state?.partial_results?.filter(r => r.content && !r.error).length || 0;
  const failedCount = state?.partial_results?.filter(r => r.error).length || 0;
  const totalTasks = state?.plan?.length || 0;

  return (
    <div className="swarm-state-panel">
      <div className="swarm-state-header">
        <h3>Swarm Execution</h3>
        <div className="swarm-state-actions">
          <button 
            className="btn btn-icon btn-ghost"
            onClick={fetchState}
            disabled={loading}
            title="Refresh"
          >
            <RefreshCw size={16} className={loading ? 'spin' : ''} />
          </button>
        </div>
      </div>

      {/* Status Bar */}
      <div className="swarm-status-bar" style={{ borderLeftColor: getStatusColor(state?.status || 'pending') }}>
        <div className="swarm-status-icon">
          {getStatusIcon(state?.status || 'pending')}
        </div>
        <div className="swarm-status-info">
          <span className="swarm-status-label">{state?.status?.toUpperCase() || 'PENDING'}</span>
          <div className="swarm-status-id-row">
            <span className="swarm-status-id">{executionId.slice(0, 8)}...</span>
            <button 
              className="btn btn-icon btn-ghost btn-xs"
              onClick={() => {
                navigator.clipboard.writeText(executionId);
                alert('Execution ID copied!');
              }}
              title="Copy full execution ID"
            >
              <Copy size={12} />
            </button>
          </div>
        </div>
      </div>

      {/* Progress */}
      {totalTasks > 0 && (
        <div className="swarm-progress">
          <div className="swarm-progress-header">
            <span>Tasks</span>
            <span>{completedCount + failedCount} / {totalTasks}</span>
          </div>
          <div className="swarm-progress-bar">
            <div 
              className="swarm-progress-fill success"
              style={{ width: `${(completedCount / totalTasks) * 100}%` }}
            />
            <div 
              className="swarm-progress-fill error"
              style={{ width: `${(failedCount / totalTasks) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Task List */}
      {state?.plan && state.plan.length > 0 && (
        <div className="swarm-tasks">
          <div className="swarm-tasks-header">Plan</div>
          <div className="swarm-tasks-list">
            {state.plan.map((task, index) => {
              const result = state.partial_results?.find(r => r.task_id === task.task_id);
              const taskStatus = result?.error ? 'failed' : result?.content ? 'completed' : task.status;
              
              return (
                <div key={task.task_id} className={`swarm-task-item ${taskStatus}`}>
                  <div className="swarm-task-index">{index + 1}</div>
                  <div className="swarm-task-content">
                    <div className="swarm-task-description">
                      {task.description.slice(0, 60)}...
                    </div>
                    {result?.execution_time_ms && (
                      <div className="swarm-task-time">
                        {(result.execution_time_ms / 1000).toFixed(1)}s
                      </div>
                    )}
                  </div>
                  <div className="swarm-task-status">
                    {getStatusIcon(taskStatus)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Errors */}
      {state?.errors && state.errors.length > 0 && (
        <div className="swarm-errors">
          <div className="swarm-errors-header">Errors</div>
          {state.errors.map((error, i) => (
            <div key={i} className="swarm-error-item">{error}</div>
          ))}
        </div>
      )}

      {/* Governance Link */}
      {state?.governance_url && (
        <div className="swarm-governance-row">
          <a 
            href={state.governance_url} 
            target="_blank" 
            rel="noopener noreferrer"
            className="swarm-governance-link"
          >
            <ExternalLink size={14} />
            View in Marquez
          </a>
          <button 
            className="btn btn-icon btn-ghost btn-sm"
            onClick={() => {
              navigator.clipboard.writeText(state.governance_url!);
              alert('Governance URL copied!');
            }}
            title="Copy governance URL"
          >
            <Copy size={14} />
          </button>
        </div>
      )}

      {/* Artifact Link */}
      {state?.artifact_path && (
        <div className="swarm-artifact">
          <span className="swarm-artifact-label">Output:</span>
          <span className="swarm-artifact-path">{state.artifact_path.split('/').pop()}</span>
        </div>
      )}
    </div>
  );
}
