import { AlertTriangle, ShieldAlert, Activity, Cpu, Terminal, Power, ExternalLink } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useWorkflowStore } from '../../hooks/useWorkflowStore';

function SynapticStream() {
  const executionEvents = useWorkflowStore((state) => state.executionEvents);
  
  // Display last 15 events
  const stream = executionEvents.slice(-15).map((event, i) => {
    let timestamp = '00:00:00';
    try {
      timestamp = typeof event.timestamp === 'string' ? event.timestamp : new Date(event.timestamp).toISOString().split('T')[1].slice(0, -5);
    } catch (e) {
      timestamp = 'ERR_TS';
    }
    const hex = Math.floor(Math.random() * 0xFFFF).toString(16).toUpperCase().padStart(4, '0');

    
    let text = event.type;
    if (event.nodeId) text += ` [${event.nodeId}]`;
    if (event.data?.message) text += `: ${event.data.message}`;

    return {
      id: i,
      text: `[${timestamp}] <0x${hex}> ${text}`,
      type: event.type.includes('error') ? 'warn' : event.type.includes('completed') ? 'success' : 'info'
    };
  });

  return (
    <div className="flex flex-col justify-end h-full font-mono text-[10px] leading-relaxed tracking-wider overflow-hidden">
      {stream.map((msg, i) => (
        <div 
          key={i} 
          className={`animate-[pulse_2s_ease-in-out_infinite] ${
            msg.type === 'warn' ? 'glow-text-orange' : 
            msg.type === 'success' ? 'glow-text-green' : 
            'glow-text-cyan opacity-70'
          }`}
        >
          {msg.text}
        </div>
      ))}
    </div>
  );
}

export function GodModeHUD({ onViewChange, currentView }: { onViewChange: (view: 'swarm' | 'knowledge' | 'marketplace') => void, currentView: string }) {
  const { uiVersion, toggleUIVersion, tokenUsage, executionPhase } = useWorkflowStore();
  const activeRuns = 4; // Placeholder


  return (
    <div className="absolute inset-0 pointer-events-none z-10 flex flex-col justify-between p-6 overflow-hidden">
      
      {/* Top Bar: Global Status & Toggle */}
      <div className="flex justify-between items-start w-full relative">
        <div 
          className="glass-panel rounded-lg p-4 pointer-events-auto w-80"
        >
          <h1 className="glow-text-cyan text-[14px] font-bold mb-4 flex items-center gap-2 tracking-widest">
            <Activity className="w-4 h-4" />
            COGNITIVE MESH
          </h1>
          <div className="space-y-3 text-[10px] text-[#00FFFF]/70">
            <div className="flex justify-between">
              <span>SYSTEM_STATUS</span>
              <span className={executionPhase === 'failed' ? 'glow-text-orange' : 'glow-text-green'}>
                {executionPhase === 'running' ? 'OPTIMIZING' : 'OPTIMAL'}
              </span>
            </div>
            <div className="flex justify-between">
              <span>ACTIVE_SWARMS</span>
              <span>{activeRuns} CLUSTERS</span>
            </div>
            <div className="flex justify-between">
              <span>TOKEN_BURN_RATE</span>
              <span>{(tokenUsage / 60).toFixed(1)} t/s</span>
            </div>
            <div className="h-[1px] w-full bg-[#00FFFF]/20 my-2" />
            <div className="flex justify-between items-center">
              <span>ENVIRONMENT</span>
              <div className="flex items-center gap-2">
                 <span className="glow-text-cyan">{uiVersion.toUpperCase()}</span>
                 <button 
                   onClick={toggleUIVersion}
                   className="p-1 rounded hover:bg-white/10 transition-colors pointer-events-auto"
                   title="Switch to V1 Dashboard"
                 >
                   <ExternalLink size={12} />
                 </button>
              </div>
            </div>
          </div>
        </div>

        {/* View Mode Toggle (Center) */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 flex gap-2 glass-panel rounded-full p-1 z-50 pointer-events-auto">
          <button 
            onClick={() => onViewChange('swarm')}
            className={`px-6 py-2 rounded-full text-[10px] font-bold tracking-widest transition-all ${currentView === 'swarm' ? 'bg-[#00FFFF]/20 text-[#00FFFF] shadow-[0_0_15px_rgba(0,255,255,0.4)]' : 'text-white/50 hover:text-white'}`}
          >
            SWARM DAG
          </button>
          <button 
            onClick={() => onViewChange('knowledge')}
            className={`px-6 py-2 rounded-full text-[10px] font-bold tracking-widest transition-all ${currentView === 'knowledge' ? 'bg-[#c084fc]/20 text-[#c084fc] shadow-[0_0_15px_rgba(192,132,252,0.4)]' : 'text-white/50 hover:text-white'}`}
          >
            KNOWLEDGE GRAPH
          </button>
          <button 
            onClick={() => onViewChange('marketplace')}
            className={`px-6 py-2 rounded-full text-[10px] font-bold tracking-widest transition-all ${currentView === 'marketplace' ? 'bg-[#39FF14]/20 text-[#39FF14] shadow-[0_0_15px_rgba(57,255,20,0.4)]' : 'text-white/50 hover:text-white'}`}
          >
            MARKETPLACE
          </button>
        </div>

        {/* Kill Switch (Right) */}
        <div 
          className="pointer-events-auto"
        >
          <button className="relative group flex items-center justify-center w-24 h-24 rounded-full bg-[#020408]/80 border-2 border-[#FF5F1F] shadow-[0_0_30px_rgba(255,95,31,0.4)] hover:shadow-[0_0_50px_rgba(255,95,31,0.8)] hover:bg-[#FF5F1F]/20 transition-all duration-300 backdrop-blur-md">
            <div className="absolute inset-[-10px] border border-dashed border-[#FF5F1F]/50 rounded-full animate-[spin_10s_linear_infinite]" />
            <div className="absolute inset-[-20px] border border-[#FF5F1F]/20 rounded-full animate-[spin_15s_linear_infinite_reverse]" />
            
            <div className="flex flex-col items-center gap-1">
              <Power className="w-8 h-8 text-[#FF5F1F] drop-shadow-[0_0_8px_rgba(255,95,31,1)]" />
              <span className="text-[10px] font-bold text-[#FF5F1F] tracking-widest">HALT</span>
            </div>
          </button>
        </div>
      </div>

      {/* Middle: Panels */}
      <div className="flex justify-between items-end w-full flex-1 pb-24">
        {/* Left: Governance */}
        <div 
          className="glass-panel rounded-lg p-4 pointer-events-auto w-80 h-96 flex flex-col"
        >
          <h2 className="glow-text-orange text-[14px] font-bold mb-4 flex items-center gap-2 tracking-widest">
            <ShieldAlert className="w-4 h-4" />
            GOVERNANCE LOGS
          </h2>
          <div className="flex-1 overflow-hidden space-y-2 text-[10px] text-[#FF5F1F]/80">
             {/* Mock logs for now, will map to execution_audit metadata */}
            <div className="p-2 border border-[#FF5F1F]/30 bg-[#FF5F1F]/10 rounded">
              [WARN] Workspace isolation strict. No root access for Swarm_Agent_1.
            </div>
            <div className="p-2 border border-[#39FF14]/30 bg-[#39FF14]/10 rounded glow-text-green">
              [SAFE] AER validation check passed for Planner node.
            </div>
            <div className="p-2 border border-[#00FFFF]/30 bg-[#00FFFF]/10 rounded text-[#00FFFF]/80">
              [INFO] Lineage registered for run_{Date.now().toString().slice(-4)}.
            </div>
          </div>
        </div>

        {/* Right: Observability Stream */}
        <div 
          className="glass-panel rounded-lg p-4 pointer-events-auto w-96 h-[500px] flex flex-col relative overflow-hidden"
        >
          <div className="absolute top-0 left-0 right-0 h-20 bg-gradient-to-b from-[#020408] to-transparent z-10" />
          <h2 className="glow-text-cyan text-[14px] font-bold mb-4 flex items-center gap-2 tracking-widest z-20 relative">
            <Cpu className="w-4 h-4" />
            OBSERVABILITY STREAM
          </h2>
          <div className="flex-1 relative z-0">
            <SynapticStream />
          </div>
        </div>
      </div>

      {/* Bottom: Command & Timeline */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex flex-col items-center gap-6 pointer-events-auto w-full max-w-3xl">
        <div className="relative w-full h-12 flex items-center justify-center">
          <div className="absolute w-full h-[1px] bg-gradient-to-r from-transparent via-[#00FFFF]/50 to-transparent" />
          <div className="flex items-center gap-1 absolute">
            {Array.from({ length: 40 }).map((_, i) => (
              <div key={i} className={`w-[2px] ${i === 20 ? 'h-6 bg-[#39FF14] shadow-[0_0_10px_rgba(57,255,20,1)]' : 'h-3 bg-[#00FFFF]/30'} rounded-full`} />
            ))}
          </div>
          <div className="absolute -top-6 text-[10px] glow-text-green tracking-widest">
            PRESENT_STATE_SYNCED
          </div>
        </div>

        <div className="glass-panel w-full rounded-full p-2 flex items-center gap-3 shadow-[0_0_30px_rgba(0,255,255,0.2)]">
          <Terminal className="w-5 h-5 text-[#00FFFF] ml-4" />
          <input 
            type="text" 
            placeholder="Broadcast intent to swarm..."
            className="flex-1 bg-transparent border-none outline-none text-[12px] font-mono text-white placeholder:text-[#00FFFF]/40"
          />
          <div className="px-4 py-2 rounded-full border border-[#00FFFF]/30 text-[#00FFFF] text-[10px] font-bold tracking-widest hover:bg-[#00FFFF]/20 transition-colors cursor-pointer">
            EXECUTE
          </div>
        </div>
      </div>

    </div>
  );
}
