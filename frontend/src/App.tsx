console.log("BOOT: App.tsx (Emergency Rollback Phase 2)");
import { useState, useEffect } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import WorkflowCanvas from './components/Studio/WorkflowCanvas';
import NodePalette from './components/Studio/NodePalette';
import SidebarTabs from './components/Studio/SidebarTabs';
import WorkflowList from './components/Studio/WorkflowList';
import ResultPanel from './components/Studio/ResultPanel';
import { useWorkflowStore } from './hooks/useWorkflowStore';
import { useWorkspaceStore } from './hooks/useWorkspaceStore';
import ErrorBoundary, { withErrorBoundary } from './components/Shared/ErrorBoundary';
import AppV2 from './AppV2Beta';

import { 
  Settings, 
  ChevronRight, ChevronLeft, Layout, Sparkles
} from 'lucide-react';

type View = 'studio' | 'agents' | 'topology' | 'settings' | 'marketplace' | 'documents';

function App() {
  const [view, setView] = useState<View>('studio');
  const [sidebarTab, setSidebarTab] = useState<'flows' | 'agents' | 'nodes' | 'sources'>('flows');
  const [isLeftPaneOpen, setIsLeftPaneOpen] = useState(true);
  const [isRightPaneOpen, setIsRightPaneOpen] = useState(false);
  const [rightPanelWidth, setRightPanelWidth] = useState(380);
  const [isDraggingRight, setIsDraggingRight] = useState(false);
  const [leftPanelWidth, setLeftPanelWidth] = useState(280);
  const [isDraggingLeft, setIsDraggingLeft] = useState(false);
  
  const uiVersion = useWorkflowStore((state) => state.uiVersion);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isDraggingRight) {
        const newWidth = window.innerWidth - e.clientX;
        if (newWidth >= 250 && newWidth <= window.innerWidth * 0.6) {
          setRightPanelWidth(newWidth);
        }
      } else if (isDraggingLeft) {
        const newWidth = e.clientX - 64;
        if (newWidth >= 200 && newWidth <= window.innerWidth * 0.5) {
          setLeftPanelWidth(newWidth);
        }
      }
    };

    const handleMouseUp = () => {
      setIsDraggingRight(false);
      setIsDraggingLeft(false);
    };

    if (isDraggingRight || isDraggingLeft) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDraggingRight, isDraggingLeft]);

  // V2 Beta Toggle Logic
  if (uiVersion === 'v2') {
    return (
      <ErrorBoundary name="AppV2Beta">
        <AppV2 />
      </ErrorBoundary>
    );
  }

  return (
    <div className="flex h-screen bg-[#020408] overflow-hidden obsidian-theme">
      <div className="scanline z-50 pointer-events-none" />
      
      {/* Navigation Rail */}
      <nav className="w-16 border-r border-white/5 flex flex-col items-center py-6 gap-6 z-40 bg-[#020408]">
        <div className="w-10 h-10 rounded bg-[#39FF14]/10 border border-[#39FF14]/30 flex items-center justify-center mb-4">
          <Sparkles className="text-[#39FF14]" size={20} />
        </div>
        
        <button 
          onClick={() => setView('studio')}
          className={`p-3 rounded transition-all ${view === 'studio' ? 'text-[#39FF14] bg-[#39FF14]/10' : 'text-white/40 hover:text-white/60'}`}
        >
          <Layout size={20} />
        </button>
        
        <div className="mt-auto flex flex-col gap-4">
          <button className="p-3 text-white/20 hover:text-white/60 transition-all">
            <Settings size={20} />
          </button>
        </div>
      </nav>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        <main className="flex-1 flex overflow-hidden">
          
          {/* Left Sidebar */}
          <div 
            style={{ width: isLeftPaneOpen ? `${leftPanelWidth}px` : '0' }}
            className={`border-r border-white/5 transition-all duration-300 relative flex flex-col bg-[#020408]/40 ${!isLeftPaneOpen ? 'overflow-hidden border-none' : ''}`}
          >
            <div className="h-full flex flex-col w-full min-w-[280px]">
              <SidebarTabs activeTab={sidebarTab} onTabChange={setSidebarTab} />
              <div className="flex-1 overflow-y-auto custom-scrollbar">
                {sidebarTab === 'flows' && <WorkflowList />}
                {sidebarTab === 'nodes' && <NodePalette />}
                {(sidebarTab === 'agents' || sidebarTab === 'sources') && (
                  <div className="p-8 text-center text-white/20 text-[10px] uppercase tracking-widest font-mono">
                    Module_Integrity_Pending...
                  </div>
                )}
              </div>
            </div>
            
            <div 
              onMouseDown={() => setIsDraggingLeft(true)}
              className="absolute top-0 right-0 w-1 h-full cursor-ew-resize hover:bg-[#39FF14]/40 z-30 transition-colors"
              title="Drag to resize"
            />
          </div>

          {/* Canvas Area */}
          <div className="flex-1 relative bg-[#020408] overflow-hidden">
            <ReactFlowProvider>
              <div className="w-full h-full relative">
                <WorkflowCanvas />
                
                {/* Floating Status / Control Overlay */}
                <div className="absolute top-6 left-1/2 -translate-x-1/2 z-40">
                   <div 
                     onClick={() => setIsRightPaneOpen(!isRightPaneOpen)}
                     className="px-6 py-2 bg-[#020408]/80 border border-[#39FF14]/30 text-[#39FF14] text-[10px] font-black tracking-widest hover:bg-[#39FF14]/10 transition-all shadow-[0_0_20px_rgba(57,255,20,0.1)] rounded-full cursor-pointer flex items-center gap-3 grayscale hover:grayscale-0"
                   >
                     <div className="w-2 h-2 rounded-full bg-[#39FF14] animate-pulse" />
                     {isRightPaneOpen ? 'CLOSE_AUDIT_PANE' : 'ACCESS_AUDIT_PANE'}
                   </div>
                </div>
              </div>
            </ReactFlowProvider>
          </div>

          {/* Right Side Panel */}
          <div 
            style={{ width: isRightPaneOpen ? `${rightPanelWidth}px` : '0' }}
            className={`border-l border-white/5 bg-[#020408]/80 backdrop-blur-xl transition-all duration-300 relative ${!isRightPaneOpen ? 'overflow-hidden border-none' : ''}`}
          >
            <div className="h-full min-w-[380px] flex flex-col">
              <ResultPanel isOpen={isRightPaneOpen} onClose={() => setIsRightPaneOpen(false)} />
            </div>
            
            <div 
              onMouseDown={() => setIsDraggingRight(true)}
              className="absolute top-0 left-0 w-1 h-full cursor-ew-resize hover:bg-[#39FF14]/40 z-30 transition-colors"
              title="Drag to resize"
            />
          </div>
          
        </main>
      </div>
    </div>
  );
}

export default withErrorBoundary(App, "GlobalApp");
