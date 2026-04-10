import { useState } from 'react';
import { Play, RotateCcw, Save, Loader, Zap } from 'lucide-react';
import { useWorkflowStore } from '../../hooks/useWorkflowStore';
import { useWorkspaceStore } from '../../hooks/useWorkspaceStore';
import WorkflowExportImport from './WorkflowExportImport';
import ActiveLLMBadge from './ActiveLLMBadge';
import { API_BASE_URL, GOVERNANCE_HEADERS } from '../../constants';

interface ExecutionBarProps {
  onNavigateToLLM?: () => void;
}

export default function ExecutionBar({ onNavigateToLLM }: ExecutionBarProps) {
  const { currentWorkspace, activeLLMProvider, activeLLMModels } = useWorkspaceStore();
  const {
    clearExecution,
    nodes,
    edges,
    setNodes,
    setSwarmExecutionId
  } = useWorkflowStore();

  const [saving, setSaving] = useState(false);
  const [executing, setExecuting] = useState(false);
  // Default to the active model from LLM Management
  const activeModel = activeLLMModels[activeLLMProvider] || 'Qwen3-8B-Hybrid';
  const [swarmConfig, setSwarmConfig] = useState({
    model: activeModel,
    max_concurrency: 1,
    workspace: currentWorkspace
  });

  const handleExecute = async () => {
    if (nodes.length === 0) {
      alert('Please add nodes to your workflow first');
      return;
    }

    // Check if workflow has a trigger node — prompt for message
    const hasTrigger = nodes.some(n => n.type === 'trigger');
    let message = '';
    if (hasTrigger) {
      const prompted = prompt(
        'Enter your message for this workflow:',
        'Tell me how I should consider AI when looking at the frolov document'
      );
      if (prompted === null) return; // cancelled
      message = prompted;
    }
    
    setExecuting(true);

    // Mark all nodes as "running"
    const updatedNodes = nodes.map(n => ({
      ...n,
      data: { ...n.data, status: 'running' }
    }));
    setNodes(updatedNodes);

    try {
      const response = await fetch(`${API_BASE_URL}/api/workflows/execute`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          ...GOVERNANCE_HEADERS
        },
        body: JSON.stringify({ 
          nodes, 
          edges,
          workspace: currentWorkspace,
          message
        })
      });
      
      if (response.ok) {
        const result = await response.json();
        console.log('Execution result:', result);

        // Update node statuses based on results
        const resultMap: Record<string, any> = {};
        for (const nr of result.node_results || []) {
          resultMap[nr.node_id] = nr;
        }

        const finalNodes = nodes.map(n => {
          const nr = resultMap[n.id];
          return {
            ...n,
            data: {
              ...n.data,
              status: nr ? nr.status : 'success',
              executionOutput: nr?.output
            }
          };
        });
        setNodes(finalNodes);

        // Show result summary
        const artifactMsg = result.artifact_path 
          ? `\n\n📄 Output: ${result.artifact_path}` 
          : '';
        const errorNodes = (result.node_results || []).filter((r: any) => r.status === 'error');
        if (errorNodes.length > 0) {
          alert(`Workflow completed with ${errorNodes.length} error(s).${artifactMsg}\n\nErrors:\n${errorNodes.map((e: any) => `• ${e.node_id}: ${e.error}`).join('\n')}`);
        } else {
          alert(`✅ Workflow executed successfully!${artifactMsg}`);
        }
      } else {
        const errText = await response.text();
        alert('Execution failed: ' + errText);
        // Mark all as error
        setNodes(nodes.map(n => ({ ...n, data: { ...n.data, status: 'error' } })));
      }
    } catch (error) {
      console.error('Execution error:', error);
      alert('Execution failed: ' + (error as Error).message);
      setNodes(nodes.map(n => ({ ...n, data: { ...n.data, status: 'error' } })));
    } finally {
      setExecuting(false);
    }
  };

  const handleSwarmExecute = async () => {
    const request = prompt('Enter your swarm request:', 'Create a comprehensive guide on...');
    if (!request) return;
    
    setExecuting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/workflow/execute`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          ...GOVERNANCE_HEADERS
        },
        body: JSON.stringify({ 
          workflow: 'swarm',
          workspace: currentWorkspace,
          message: request,
          model: swarmConfig.model,
          params: {
            max_concurrency: swarmConfig.max_concurrency
          }
        })
      });
      
      if (response.ok) {
        const result = await response.json();
        setSwarmExecutionId(result.execution_id);
        
        // Visualize Swarm Graph in Studio
        const swarmNodes = [
          { id: 'planner', type: 'llm', position: { x: 250, y: 50 }, data: { label: 'Planner (Bricoleur)', config: { model: swarmConfig.model } } },
          { id: 'orchestrator', type: 'logic', position: { x: 250, y: 200 }, data: { label: 'Orchestrator', config: { condition: 'Review Plan' } } },
          { id: 'dispatcher', type: 'trigger', position: { x: 250, y: 350 }, data: { label: 'Dispatcher', config: { type: 'fan-out' } } },
          { id: 'executor', type: 'tool', position: { x: 250, y: 500 }, data: { label: `Executor (x${swarmConfig.max_concurrency})`, config: { tool: 'code_execution' } } },
          { id: 'aggregator', type: 'data', position: { x: 250, y: 650 }, data: { label: 'Aggregator (Kludge)', config: { operation: 'combine' } } }
        ];

        const swarmEdges = [
          { id: 'e1', source: 'planner', target: 'orchestrator', animated: true },
          { id: 'e2', source: 'orchestrator', target: 'dispatcher', animated: true },
          { id: 'e3', source: 'dispatcher', target: 'executor', animated: true },
          { id: 'e4', source: 'executor', target: 'aggregator', animated: true }
        ];

        const { setNodes, setEdges } = useWorkflowStore.getState();
        setNodes(swarmNodes);
        setEdges(swarmEdges);

        console.log('Swarm started:', result);
        alert(`Swarm started! Execution ID: ${result.execution_id}\n\nGovernance: ${result.governance_url}`);
      } else {
        alert('Swarm execution failed');
      }
    } catch (error) {
      console.error('Swarm error:', error);
      alert('Swarm failed: ' + (error as Error).message);
    } finally {
      setExecuting(false);
    }
  };

  const handleSave = async () => {
    if (nodes.length === 0) {
      alert('Cannot save empty workflow');
      return;
    }
    
    const name = prompt('Workflow name:', 'Untitled Workflow');
    if (!name) return;
    
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/workflows`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          ...GOVERNANCE_HEADERS
        },
        body: JSON.stringify({
          name,
          description: '',
          nodes,
          edges,
          type: 'user'
        })
      });
      
      if (response.ok) {
        alert('Workflow saved successfully!');
      } else {
        alert('Save failed');
      }
    } catch (error) {
      console.error('Save error:', error);
      alert('Save failed: ' + (error as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="top-bar">
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <h1>🔷 Workflow Studio</h1>
        <ActiveLLMBadge onNavigateToLLM={onNavigateToLLM} />
      </div>
      
      <div className="execution-controls">
        <button 
          className="btn btn-gradient" 
          onClick={handleExecute}
          disabled={executing || nodes.length === 0}
        >
          {executing ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
          {executing ? 'Executing...' : 'Execute'}
        </button>
        <button className="btn btn-outline" onClick={clearExecution}>
          <RotateCcw size={16} />
          Clear
        </button>
        <button 
          className="btn btn-outline" 
          onClick={handleSave}
          disabled={saving || nodes.length === 0}
        >
          {saving ? <Loader className="animate-spin" size={16} /> : <Save size={16} />}
          {saving ? 'Saving...' : 'Save'}
        </button>
        
        <div style={{ marginLeft: '8px', borderLeft: '1px solid var(--border-color)', paddingLeft: '16px' }}>
          <button 
            className="btn btn-gradient" 
            onClick={handleSwarmExecute}
            disabled={executing}
            title="Execute a Swarm workflow"
          >
            <Zap size={16} />
            Swarm
          </button>
        </div>
        
        <WorkflowExportImport 
          workflowName="workflow"
          config={swarmConfig}
          onConfigChange={setSwarmConfig}
        />
      </div>
    </div>
  );
}
