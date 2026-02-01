import { useState } from 'react';
import { X, Trash2, ArrowRight, ArrowLeft } from 'lucide-react';
import { useWorkflowStore } from '../../hooks/useWorkflowStore';

interface ConfigPanelProps {
  isOpen: boolean;
  nodeId: string | null;
}

export default function ConfigPanel({ isOpen, nodeId }: ConfigPanelProps) {
  const [activeTab, setActiveTab] = useState<'settings' | 'input' | 'output'>('settings');
  const nodes = useWorkflowStore((state) => state.nodes);
  const updateNodeData = useWorkflowStore((state) => state.updateNodeData);
  const setSelectedNode = useWorkflowStore((state) => state.setSelectedNode);
  const deleteNode = useWorkflowStore((state) => state.deleteNode);
  const getConnectedNodes = useWorkflowStore((state) => state.getConnectedNodes);
  const nodeOutputs = useWorkflowStore((state) => state.nodeOutputs);

  const node = nodes.find((n) => n.id === nodeId);
  const output = nodeId ? nodeOutputs[nodeId] : null;
  const connections = nodeId ? getConnectedNodes(nodeId) : { inputs: [], outputs: [] };

  if (!node) return null;

  const handleClose = () => {
    setSelectedNode(null);
  };

  const handleDelete = () => {
    if (confirm(`Delete node "${node.data.label || node.type}"?`)) {
      deleteNode(node.id);
    }
  };

  const handleLabelChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    updateNodeData(node.id, { label: e.target.value });
  };

  const handleConfigChange = (key: string, value: string) => {
    updateNodeData(node.id, { 
      config: { 
        ...(node.data.config as object || {}), 
        [key]: value 
      } 
    });
  };

  return (
    <div className={`config-panel ${isOpen ? 'open' : ''}`}>
      <div className="config-header">
        <h2>{String(node.data.label || node.type)}</h2>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button 
            className="btn btn-icon btn-ghost" 
            onClick={handleDelete}
            title="Delete node"
            aria-label="Delete node"
          >
            <Trash2 size={16} />
          </button>
          <button 
            className="btn btn-icon btn-ghost" 
            onClick={handleClose}
            title="Close panel"
            aria-label="Close panel"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      <div className="config-tabs">
        <button 
          className={`config-tab ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
        >
          Settings
        </button>
        <button 
          className={`config-tab ${activeTab === 'input' ? 'active' : ''}`}
          onClick={() => setActiveTab('input')}
        >
          Input ({connections.inputs.length})
        </button>
        <button 
          className={`config-tab ${activeTab === 'output' ? 'active' : ''}`}
          onClick={() => setActiveTab('output')}
        >
          Output ({connections.outputs.length})
        </button>
      </div>

      <div className="config-content">
        {activeTab === 'settings' && (
          <>
            <div className="form-group">
              <label className="form-label" htmlFor="node-name">Node Name</label>
              <input 
                id="node-name"
                type="text" 
                className="form-input" 
                value={String(node.data.label || '')} 
                onChange={handleLabelChange}
                placeholder="Enter node name..."
              />
            </div>

            {node.type === 'llm' && (
              <>
                <div className="form-group">
                  <label className="form-label" htmlFor="llm-model">Model</label>
                  <select 
                    id="llm-model"
                    className="form-select" 
                    value={(node.data.config as {model?: string})?.model || 'gpt-4-turbo'}
                    onChange={(e) => handleConfigChange('model', e.target.value)}
                    title="Select LLM model"
                    aria-label="Select LLM model"
                  >
                    <optgroup label="Cloud Models">
                      <option value="gpt-4-turbo">GPT-4 Turbo (OpenAI)</option>
                      <option value="claude-3-sonnet">Claude 3 Sonnet (Anthropic)</option>
                      <option value="gpt-3.5-turbo">GPT-3.5 Turbo (OpenAI)</option>
                    </optgroup>
                    <optgroup label="Local Models">
                      <option value="ollama/llama3.2">Llama 3.2 (Ollama)</option>
                      <option value="ollama/deepseek-r1:8b">DeepSeek R1 (Ollama)</option>
                      <option value="openai/deepseek-r1:8b">DeepSeek R1 (FastFlowLM)</option>
                    </optgroup>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="system-prompt">System Prompt</label>
                  <textarea 
                    id="system-prompt"
                    className="form-textarea" 
                    placeholder="You are a helpful assistant..."
                    value={(node.data.config as {systemPrompt?: string})?.systemPrompt || ''}
                    onChange={(e) => handleConfigChange('systemPrompt', e.target.value)}
                  />
                </div>
              </>
            )}

            {node.type === 'trigger' && (
              <div className="form-group">
                <label className="form-label" htmlFor="trigger-type">Trigger Type</label>
                <select 
                  id="trigger-type"
                  className="form-select" 
                  value={(node.data.config as {triggerType?: string})?.triggerType || 'manual'}
                  onChange={(e) => handleConfigChange('triggerType', e.target.value)}
                  title="Select trigger type"
                  aria-label="Select trigger type"
                >
                  <option value="manual">Manual</option>
                  <option value="chat">Chat Input</option>
                  <option value="schedule">Schedule (Cron)</option>
                  <option value="webhook">Webhook</option>
                </select>
              </div>
            )}

            {node.type === 'tool' && (
              <div className="form-group">
                <label className="form-label" htmlFor="tool-select">Tool</label>
                <select 
                  id="tool-select"
                  className="form-select" 
                  value={(node.data.config as {tool?: string})?.tool || ''}
                  onChange={(e) => handleConfigChange('tool', e.target.value)}
                  title="Select tool"
                  aria-label="Select tool"
                >
                  <option value="">Select a tool...</option>
                  <option value="search_knowledge">Search Knowledge Base</option>
                  <option value="read_file">Read File</option>
                  <option value="write_file">Write File</option>
                  <option value="extract_pdf">Extract PDF Text</option>
                  <option value="query_csv">Query CSV</option>
                  <option value="web_search">Web Search</option>
                </select>
              </div>
            )}

            {node.type === 'data' && (
              <>
                <div className="form-group">
                  <label className="form-label" htmlFor="data-operation">Operation</label>
                  <select 
                    id="data-operation"
                    className="form-select" 
                    value={(node.data.config as {operation?: string})?.operation || 'read'}
                    onChange={(e) => handleConfigChange('operation', e.target.value)}
                    title="Select operation"
                    aria-label="Select data operation"
                  >
                    <option value="read">Read File</option>
                    <option value="write">Write File</option>
                    <option value="search">Search Knowledge Base</option>
                    <option value="csv">Query CSV</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="file-path">File Path</label>
                  <input 
                    id="file-path"
                    type="text" 
                    className="form-input" 
                    placeholder="/path/to/file.txt"
                    value={(node.data.config as {path?: string})?.path || ''}
                    onChange={(e) => handleConfigChange('path', e.target.value)}
                  />
                </div>
              </>
            )}

            {node.type === 'logic' && (
              <div className="form-group">
                <label className="form-label" htmlFor="condition">Condition</label>
                <textarea 
                  id="condition"
                  className="form-textarea" 
                  placeholder="output.contains('success')"
                  value={(node.data.config as {condition?: string})?.condition || ''}
                  onChange={(e) => handleConfigChange('condition', e.target.value)}
                />
              </div>
            )}
          </>
        )}

        {activeTab === 'input' && (
          <div className="connections-list">
            {connections.inputs.length === 0 ? (
              <div className="empty-state">
                <ArrowLeft size={24} />
                <p>No incoming connections</p>
              </div>
            ) : (
              connections.inputs.map((inputNode) => (
                <div key={inputNode.id} className="connection-item">
                  <ArrowLeft size={16} />
                  <span>{String(inputNode.data.label || inputNode.type)}</span>
                </div>
              ))
            )}
            <div className="data-preview" style={{ marginTop: '16px' }}>
              <div className="data-preview-header">Input Schema</div>
              <div className="data-preview-content">
                {`{
  "messages": [...],
  "context": {...}
}`}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'output' && (
          <div className="connections-list">
            {connections.outputs.length === 0 ? (
              <div className="empty-state">
                <ArrowRight size={24} />
                <p>No outgoing connections</p>
              </div>
            ) : (
              connections.outputs.map((outputNode) => (
                <div key={outputNode.id} className="connection-item">
                  <span>{String(outputNode.data.label || outputNode.type)}</span>
                  <ArrowRight size={16} />
                </div>
              ))
            )}
            <div className="data-preview" style={{ marginTop: '16px' }}>
              <div className="data-preview-header">Output Data</div>
              <div className="data-preview-content">
                {output ? JSON.stringify(output, null, 2) : 'No output yet. Execute the workflow to see results.'}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
