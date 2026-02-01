import { useState } from 'react';
import { Play, RotateCcw, Save, Loader } from 'lucide-react';
import { useWorkflowStore } from '../../hooks/useWorkflowStore';
import { useWorkspaceStore } from '../../hooks/useWorkspaceStore';

export default function ExecutionBar() {
  const nodes = useWorkflowStore((state) => state.nodes);
  const edges = useWorkflowStore((state) => state.edges);
  const clearExecution = useWorkflowStore((state) => state.clearExecution);
  const { currentWorkspace } = useWorkspaceStore();
  const [saving, setSaving] = useState(false);
  const [executing, setExecuting] = useState(false);

  const handleExecute = async () => {
    if (nodes.length === 0) {
      alert('Please add nodes to your workflow first');
      return;
    }
    
    setExecuting(true);
    try {
      const response = await fetch('http://localhost:8000/api/workflows/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          nodes, 
          edges,
          workspace: currentWorkspace
        })
      });
      
      if (response.ok) {
        const result = await response.json();
        console.log('Execution result:', result);
        alert('Workflow executed successfully!');
      } else {
        alert('Execution failed');
      }
    } catch (error) {
      console.error('Execution error:', error);
      alert('Execution failed: ' + (error as Error).message);
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
      const response = await fetch('http://localhost:8000/api/workflows', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
      <h1>🔷 Workflow Studio</h1>
      
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
      </div>
    </div>
  );
}
