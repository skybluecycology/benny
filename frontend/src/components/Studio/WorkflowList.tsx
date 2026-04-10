import { useState, useEffect } from 'react';
import { FileText, Plus, Trash2, Loader } from 'lucide-react';
import { useWorkflowStore } from '../../hooks/useWorkflowStore';
import { API_BASE_URL, GOVERNANCE_HEADERS } from '../../constants';

interface Workflow {
  id: string;
  name: string;
  description?: string;
  type: 'user' | 'example';
  readonly?: boolean;
  nodes: any[];
  edges: any[];
}

interface WorkflowListProps {
  mode?: 'flows' | 'agents';
}

export default function WorkflowList({ mode = 'flows' }: WorkflowListProps) {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const setNodes = useWorkflowStore((state) => state.setNodes);
  const setEdges = useWorkflowStore((state) => state.setEdges);

  useEffect(() => {
    fetchWorkflows();
  }, []);

  const fetchWorkflows = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/workflows`, {
        headers: { ...GOVERNANCE_HEADERS }
      });
      const data = await response.json();
      const workflowList = Array.isArray(data) ? data : (data.value || []);
      setWorkflows(workflowList);
    } catch (error) {
      console.error('Failed to fetch workflows:', error);
    } finally {
      setLoading(false);
    }
  };

  const filteredWorkflows = workflows.filter(w => {
    const isAgent = w.name.toLowerCase().includes('agent') || w.name.toLowerCase().includes('persona');
    return mode === 'agents' ? isAgent : !isAgent;
  });

  const loadWorkflow = async (workflow: Workflow) => {
    setSelectedId(workflow.id);
    setNodes(workflow.nodes || []);
    setEdges(workflow.edges || []);
  };

  const deleteWorkflow = async (id: string) => {
    if (!confirm('Delete this workflow?')) return;
    try {
      await fetch(`${API_BASE_URL}/api/workflows/${id}`, {
        method: 'DELETE',
        headers: { ...GOVERNANCE_HEADERS }
      });
      fetchWorkflows();
    } catch (error) {
      console.error('Failed to delete workflow:', error);
    }
  };

  const createNew = () => {
    setSelectedId(null);
    setNodes([]);
    setEdges([]);
  };

  if (loading) {
    return (
      <div style={{ padding: '20px', textAlign: 'center' }}>
        <Loader className="animate-spin" size={24} />
      </div>
    );
  }

  return (
    <div className="workflow-list-container" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <button
        className="btn btn-gradient"
        onClick={createNew}
        style={{ width: '100%', gap: '8px' }}
      >
        <Plus size={16} />
        {mode === 'agents' ? 'Create New Agent' : 'New Workflow'}
      </button>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {filteredWorkflows.length === 0 && (
          <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
            No {mode === 'agents' ? 'Agents' : 'Flows'} found.
          </div>
        )}
        {filteredWorkflows.map((workflow) => (
          <div
            key={workflow.id}
            className={`workflow-card ${selectedId === workflow.id ? 'selected' : ''}`}
            onClick={() => loadWorkflow(workflow)}
            style={{
              padding: '12px',
              background: 'var(--bg-card)',
              borderRadius: '8px',
              cursor: 'pointer',
              border: selectedId === workflow.id ? '2px solid var(--accent-llm)' : '1px solid var(--border-color)',
              transition: 'all 0.2s ease'
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flex: 1 }}>
                {mode === 'agents' ? <Plus size={16} style={{ color: 'var(--accent-llm)' }} /> : <FileText size={16} style={{ color: 'var(--accent-llm)' }} />}
                <div>
                  <div style={{ fontSize: '14px', fontWeight: '500' }}>{workflow.name}</div>
                  {workflow.description && (
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                      {workflow.description}
                    </div>
                  )}
                </div>
              </div>
              
              {workflow.type === 'example' && (
                <span className="badge" style={{ fontSize: '10px', marginLeft: '8px', background: 'rgba(139, 92, 250, 0.1)', color: 'var(--accent-llm)', padding: '2px 6px', borderRadius: '4px' }}>
                  Example
                </span>
              )}
              
              {workflow.type === 'user' && (
                <button
                  className="btn btn-ghost"
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteWorkflow(workflow.id);
                  }}
                  style={{ padding: '4px' }}
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
