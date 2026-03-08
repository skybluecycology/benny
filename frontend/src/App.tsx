import { useState } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import WorkflowCanvas from './components/Studio/WorkflowCanvas';
import NodePalette from './components/Studio/NodePalette';
import ConfigPanel from './components/Studio/ConfigPanel';
import ExecutionBar from './components/Studio/ExecutionBar';
import LLMManager from './components/LLMManager/LLMManager';
import WorkflowList from './components/Studio/WorkflowList';
import SourcePanel from './components/Studio/SourcePanel';
import ResultPanel from './components/Studio/ResultPanel';
import NotebookView from './components/Notebook/NotebookView';
import SwarmStatePanel from './components/Studio/SwarmStatePanel';
import SwarmConfigPanel from './components/Studio/SwarmConfigPanel';
import { useWorkflowStore } from './hooks/useWorkflowStore';
import { Layers, Cpu, BookOpen } from 'lucide-react';

type View = 'studio' | 'notebook' | 'llm';

import WorkspaceSelector from './components/Shared/WorkspaceSelector';

function App() {
  const [view, setView] = useState<View>('studio');
  const [showResults, setShowResults] = useState(false);
  const swarmExecutionId = useWorkflowStore((state) => state.swarmExecutionId);
  const [swarmConfig, setSwarmConfig] = useState({
    model: 'ollama/llama3.2',
    max_concurrency: 1,
    workspace: 'default'
  });
  const selectedNode = useWorkflowStore((state) => state.selectedNode);

  return (
    <ReactFlowProvider>
      <div className="app-layout">
        {/* Left Sidebar - Navigation + Content */}
        <div className="sidebar">
          {/* Navigation */}
          <div style={{ padding: '16px', borderBottom: '1px solid var(--border-color)' }}>
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '10px',
              marginBottom: '16px' 
            }}>
              <div style={{
                width: '32px',
                height: '32px',
                background: 'var(--gradient-primary)',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 'bold'
              }}>B</div>
              <span style={{ fontSize: '18px', fontWeight: '600' }}>Benny</span>
            </div>
            
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <button 
                className={`btn btn-${view === 'studio' ? 'gradient' : 'ghost'}`}
                onClick={() => setView('studio')}
                style={{ flex: '1 1 calc(50% - 4px)' }}
              >
                <Layers size={16} />
                Studio
              </button>
              <button 
                className={`btn btn-${view === 'notebook' ? 'gradient' : 'ghost'}`}
                onClick={() => setView('notebook')}
                style={{ flex: '1 1 calc(50% - 4px)' }}
              >
                <BookOpen size={16} />
                Notebook
              </button>
              <button 
                className={`btn btn-${view === 'llm' ? 'gradient' : 'ghost'}`}
                onClick={() => setView('llm')}
                style={{ flex: '1 1 100%' }}
              >
                <Cpu size={16} />
                LLMs
              </button>
            </div>
          </div>

          {/* Studio Sidebar - Workflows + Node Palette + Swarm */}
          {view === 'studio' && (
            <div className="studio-sidebar">
              <WorkspaceSelector />
              <WorkflowList />
              <SwarmConfigPanel 
                config={swarmConfig}
                onChange={setSwarmConfig}
              />
              <SwarmStatePanel executionId={swarmExecutionId} />
              <NodePalette />
            </div>
          )}

          {/* Notebook Sidebar - Sources */}
          {view === 'notebook' && (
            <div className="notebook-sidebar">
              <WorkspaceSelector />
              <SourcePanel />
            </div>
          )}

          {/* LLM view - show node palette as fallback */}
          {view === 'llm' && <NodePalette />}
        </div>

        {/* Main Content */}
        <div className="main-content">
          {view === 'studio' && (
            <>
              <ExecutionBar onNavigateToLLM={() => setView('llm')} />
              <div className="canvas-container">
                <WorkflowCanvas />
              </div>
            </>
          )}
          
          {view === 'notebook' && <NotebookView />}
          
          {view === 'llm' && <LLMManager />}
        </div>

        {/* Right Panel - Config or Results */}
        {view === 'studio' && selectedNode && (
          <ConfigPanel 
            isOpen={!!selectedNode} 
            nodeId={selectedNode} 
          />
        )}
        
        {view === 'studio' && showResults && (
          <ResultPanel 
            isOpen={showResults}
            onClose={() => setShowResults(false)}
          />
        )}
      </div>
    </ReactFlowProvider>
  );
}

export default App;
