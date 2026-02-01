import { Handle, Position } from '@xyflow/react';
import { Brain, X } from 'lucide-react';
import { useWorkflowStore } from '../../../hooks/useWorkflowStore';

interface LLMNodeData {
  label?: string;
  config?: {
    model?: string;
    systemPrompt?: string;
  };
}

interface LLMNodeProps {
  id: string;
  data: LLMNodeData;
  selected?: boolean;
}

export default function LLMNode({ id, data, selected }: LLMNodeProps) {
  const status = useWorkflowStore((state) => state.executionStatus[id] || 'idle');
  const output = useWorkflowStore((state) => state.nodeOutputs[id]);
  const deleteNode = useWorkflowStore((state) => state.deleteNode);

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    deleteNode(id);
  };

  return (
    <div className={`workflow-node workflow-node--llm ${selected ? 'selected' : ''} ${status}`}>
      {/* Input Section */}
      <div className="node-section node-section--input">
        <Handle 
          type="target" 
          position={Position.Left} 
          id="input"
          className="node-handle node-handle--input"
        />
        <span className="node-handle-label">Input</span>
      </div>

      {/* Header */}
      <div className="node-header">
        <div className="node-icon node-icon--llm">
          <Brain size={14} />
        </div>
        <span className="node-title">{data.label || 'LLM'}</span>
        <div className={`node-status node-status--${status}`} />
        <button 
          className="node-delete-btn" 
          onClick={handleDelete}
          title="Delete node"
        >
          <X size={12} />
        </button>
      </div>

      {/* Body / Process */}
      <div className="node-body">
        <div className="node-field">
          <span className="node-field-label">Model</span>
          <div className="node-field-value">{data.config?.model || 'gpt-4-turbo'}</div>
        </div>
        {data.config?.systemPrompt && (
          <div className="node-field">
            <span className="node-field-label">Prompt</span>
            <div className="node-field-value node-field-value--truncate">
              {data.config.systemPrompt.slice(0, 40)}...
            </div>
          </div>
        )}
        {output && (
          <div className="node-output-preview">
            <span className="node-field-label">Output</span>
            <div className="node-field-value node-field-value--truncate">
              {typeof output === 'string' ? output.slice(0, 60) : JSON.stringify(output).slice(0, 60)}...
            </div>
          </div>
        )}
      </div>

      {/* Output Section */}
      <div className="node-section node-section--output">
        <span className="node-handle-label">Output</span>
        <Handle 
          type="source" 
          position={Position.Right} 
          id="output"
          className="node-handle node-handle--output"
        />
      </div>
    </div>
  );
}
