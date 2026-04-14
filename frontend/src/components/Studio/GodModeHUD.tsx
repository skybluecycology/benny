import { AlertTriangle, ShieldAlert, Activity, Cpu, Terminal, Power, ExternalLink, Zap, Settings, Eye, FastForward } from 'lucide-react';
import { useEffect, useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useWorkflowStore } from '../../hooks/useWorkflowStore';
import { useWorkspaceStore } from '../../hooks/useWorkspaceStore';

function SonicWave({ active }: { active: boolean }) {
  return (
    <div className="flex items-center gap-[2px] h-4">
      {Array.from({ length: 12 }).map((_, i) => (
        <motion.div
          key={i}
          animate={{
            height: active ? [4, 16, 8, 14, 6][i % 5] : 4,
            opacity: active ? [0.4, 1, 0.6, 0.8, 0.5][i % 5] : 0.2
          }}
          transition={{
            duration: 0.5,
            repeat: Infinity,
            repeatType: "reverse",
            delay: i * 0.05
          }}
          className="w-[2px] bg-[#00FFFF] rounded-full"
        />
      ))}
    </div>
  );
}

function SynapticStream() {
  const executionEvents = useWorkflowStore((state) => state.executionEvents);
  const currentWorkspace = useWorkspaceStore((state) => state.currentWorkspace);
  
  // High-fidelity integrated stream
  const stream = useMemo(() => {
    // Merge real events with occasional "governance/workspace" injections for the sci-fi feel
    const baseStream = executionEvents.slice(-15).map((event, i) => {
      let timestamp = '00:00:00';
      try {
        timestamp = typeof event.timestamp === 'string' ? event.timestamp : new Date(event.timestamp).toISOString().split('T')[1].slice(0, -5);
      } catch (e) {
        timestamp = 'ERR_TS';
      }
      const hex = Math.floor(Math.random() * 0xFFFF).toString(16).toUpperCase().padStart(4, '0');
      const addr = Math.floor(Math.random() * 0xFFFFFF).toString(16).toUpperCase().padStart(6, '0');
      
      let text = event.type.toUpperCase();
      if (event.nodeId) text += ` [${event.nodeId.split('.').pop()}]`;
      if (event.data?.message) text += ` :: ${event.data.message}`;

      return {
        id: `evt-${i}`,
        text: `[${timestamp}] >> WORKSPACE:${currentWorkspace} >> ADDR:0x${addr} >> ${text}`,
        type: event.type.includes('error') ? 'warn' : event.type.includes('completed') ? 'success' : 'info'
      };
    });

    return baseStream;
  }, [executionEvents, currentWorkspace]);

  return (
    <div className="flex flex-col justify-end h-full font-mono text-[9px] leading-relaxed tracking-wider overflow-hidden">
      <AnimatePresence initial={false}>
        {stream.map((msg) => (
          <motion.div 
            key={msg.id}
            initial={{ x: -20, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            className={`${
              msg.type === 'warn' ? 'glow-text-orange glitch-text' : 
              msg.type === 'success' ? 'glow-text-green' : 
              'glow-text-cyan opacity-80'
            }`}
          >
            {msg.text}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

export function GodModeHUD({ onViewChange, currentView }: { onViewChange: (view: 'swarm' | 'knowledge' | 'marketplace') => void, currentView: string }) {
  const { uiVersion, toggleUIVersion, tokenUsage, executionPhase } = useWorkflowStore();
  const [glitchMode, setGlitchMode] = useState(false);
  const [lowPower, setLowPower] = useState(false);
  
  const activeRuns = 4; // Placeholder

  return (
    <div className="absolute inset-0 pointer-events-none z-50 flex flex-col justify-between p-6 overflow-hidden border-[1px] border-[#00FFFF]/5 rounded-sm">
      
      {/* Top Bar: Global Status & Toggle */}
      <div className="flex justify-between items-start w-full relative">
        <motion.div 
          initial={{ y: -50, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="glass-panel p-4 pointer-events-auto w-80 shadow-[0_0_40px_rgba(0,255,255,0.1)]"
        >
          <div className="flex justify-between items-center mb-4">
            <h1 className="glow-text-cyan text-[12px] font-bold flex items-center gap-2 tracking-[0.2em]">
              <Activity className="w-3 h-3" />
              COGNITIVE_MESH_OS
            </h1>
            <SonicWave active={executionPhase === 'running'} />
          </div>
          
          <div className="space-y-3 text-[9px] text-[#00FFFF]/70 uppercase font-bold tracking-widest">
            <div className="flex justify-between">
              <span>SYSTEM_CORE</span>
              <span className={executionPhase === 'failed' ? 'glow-text-orange glitch-text' : 'glow-text-green'}>
                {executionPhase === 'running' ? 'OPTIMIZING' : 'STABLE_IDLE'}
              </span>
            </div>
            <div className="flex justify-between">
              <span>ACTIVE_MESH_CLUSTERS</span>
              <span>0x0{activeRuns}</span>
            </div>
            <div className="flex justify-between">
              <span>NEURAL_BURN_RATE</span>
              <span className="glow-text-cyan">{(tokenUsage / 60).toFixed(1)} T/S</span>
            </div>
            
            <div className="h-[1px] w-full bg-[#00FFFF]/10 my-2" />
            
            <div className="grid grid-cols-2 gap-2 mt-4">
               <button 
                 onClick={() => setGlitchMode(!glitchMode)}
                 className={`flex items-center gap-2 px-2 py-1 rounded border transition-all ${glitchMode ? 'bg-[#FF5F1F]/20 border-[#FF5F1F] text-[#FF5F1F]' : 'bg-[#00FFFF]/5 border-[#00FFFF]/20 text-[#00FFFF]/50 hover:text-[#00FFFF]'}`}
               >
                 <Zap size={10} />
                 <span>GLITCH_{glitchMode ? 'ON' : 'OFF'}</span>
               </button>
               <button 
                 onClick={() => setLowPower(!lowPower)}
                 className={`flex items-center gap-2 px-2 py-1 rounded border transition-all ${lowPower ? 'bg-[#39FF14]/20 border-[#39FF14] text-[#39FF14]' : 'bg-[#00FFFF]/5 border-[#00FFFF]/20 text-[#00FFFF]/50 hover:text-[#00FFFF]'}`}
               >
                 <Eye size={10} />
                 <span>LOD_{lowPower ? 'ECO' : 'MAX'}</span>
               </button>
            </div>
          </div>
        </motion.div>

        {/* View Mode Toggle (Center) */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 flex gap-2 glass-panel rounded-full p-1 z-50 pointer-events-auto">
          <button 
            onClick={() => onViewChange('swarm')}
            className={`px-6 py-2 rounded-full text-[9px] font-bold tracking-[0.2em] transition-all ${currentView === 'swarm' ? 'bg-[#00FFFF]/20 text-[#00FFFF] shadow-[0_0_15px_rgba(0,255,255,0.4)]' : 'text-white/30 hover:text-white'}`}
          >
            SWARM_DAG
          </button>
          <button 
            onClick={() => onViewChange('knowledge')}
            className={`px-6 py-2 rounded-full text-[9px] font-bold tracking-[0.2em] transition-all ${currentView === 'knowledge' ? 'bg-[#c084fc]/20 text-[#c084fc] shadow-[0_0_15px_rgba(192,132,252,0.4)]' : 'text-white/30 hover:text-white'}`}
          >
            NEURAL_WEB
          </button>
          <button 
            onClick={() => onViewChange('marketplace')}
            className={`px-6 py-2 rounded-full text-[9px] font-bold tracking-[0.2em] transition-all ${currentView === 'marketplace' ? 'bg-[#39FF14]/20 text-[#39FF14] shadow-[0_0_15px_rgba(57,255,20,0.4)]' : 'text-white/30 hover:text-white'}`}
          >
            FORGE_HUB
          </button>
        </div>

        {/* Kill Switch (Right) */}
        <motion.div 
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          className="pointer-events-auto"
        >
          <button className="relative group flex items-center justify-center w-28 h-28 rounded-full bg-[#020408]/60 border-2 border-[#FF5F1F] shadow-[0_0_40px_rgba(255,95,31,0.2)] hover:shadow-[0_0_60px_rgba(255,95,31,0.6)] hover:bg-[#FF5F1F]/10 transition-all duration-500 backdrop-blur-xl">
            {/* Holographic Signal Rings */}
            <div className="absolute inset-[-8px] border-[1px] border-dashed border-[#FF5F1F]/40 rounded-full animate-[spin_8s_linear_infinite]" />
            <div className="absolute inset-[-16px] border-[1px] border-[#FF5F1F]/10 rounded-full animate-[spin_12s_linear_infinite_reverse]" />
            <div className="absolute inset-[-24px] border-[1px] border-dashed border-[#FF5F1F]/5 rounded-full animate-[spin_20s_linear_infinite]" />
            
            <div className="flex flex-col items-center gap-1 z-10">
              <Power className="w-10 h-10 text-[#FF5F1F] drop-shadow-[0_0_12px_rgba(255,95,31,1)]" />
              <span className="text-[10px] font-black text-[#FF5F1F] tracking-[0.3em]">HALT</span>
            </div>
            
            {/* Scanline inside button */}
            <div className="absolute inset-0 rounded-full overflow-hidden opacity-20 pointer-events-none">
              <div className="scanline" />
            </div>
          </button>
        </motion.div>
      </div>

      {/* Middle: HUD Overlays */}
      <div className="flex justify-between items-end w-full flex-1 pb-24">
        {/* Left: Governance & Security (Detailed logs) */}
        <motion.div 
          initial={{ x: -100, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          className="glass-panel p-4 pointer-events-auto w-80 h-[450px] flex flex-col border-l-2 border-l-[#FF5F1F]/40"
        >
          <h2 className="glow-text-orange text-[12px] font-bold mb-4 flex items-center gap-2 tracking-[0.2em]">
            <ShieldAlert className="w-3 h-3" />
            GOVERNANCE_PROTOCOL
          </h2>
          <div className="flex-1 overflow-y-auto space-y-2 text-[9px] font-mono pr-2 custom-scrollbar">
            <div className="p-2 border border-[#FF5F1F]/20 bg-[#FF5F1F]/5 rounded text-[#FF5F1F]/80">
              [WRN] WORKSPACE_ISOLATION:STRICT // ADDR_BOUNDS_CHECK ... FAIL_NON_CRIT
            </div>
            <div className="p-2 border border-[#39FF14]/20 bg-[#39FF14]/5 rounded glow-text-green">
              [OK] AER_VALIDATION :: RUN_ID:0x{Math.floor(Math.random()*1000).toString(16)} ... SYNCED
            </div>
            <div className="p-2 border border-[#00FFFF]/20 bg-[#00FFFF]/5 rounded text-[#00FFFF]/60">
              [INF] LINEAGE_REGISTERED :: OBJECT:ARCHITECTURE.MD ... PROVENANCE_PATH_RECONSTRUCTED
            </div>
            <div className="p-2 border border-[#FF5F1F]/20 bg-[#FF5F1F]/5 rounded text-[#FF5F1F]/80 italic">
              [SYS] NP_KERNEL_SWITCH:LOCAL_ACCEL_ACTIVE
            </div>
          </div>
        </motion.div>

        {/* Right: Synaptic Stream (Live machine thought) */}
        <motion.div 
          initial={{ x: 100, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          className="glass-panel p-4 pointer-events-auto w-[450px] h-[550px] flex flex-col relative overflow-hidden border-r-2 border-r-[#00FFFF]/40"
        >
          <div className="absolute top-0 left-0 right-0 h-16 bg-gradient-to-b from-[#020408] to-transparent z-10" />
          <div className="flex justify-between items-center mb-4 z-20 relative">
            <h2 className="glow-text-cyan text-[12px] font-bold flex items-center gap-2 tracking-[0.2em]">
              <Cpu className="w-3 h-3" />
              SYNAPTIC_STREAM
            </h2>
            <div className="text-[8px] text-[#00FFFF]/40 font-mono">
              BUF_0x42_LOAD: {Math.floor(Math.random()*40+20)}%
            </div>
          </div>
          <div className="flex-1 relative z-0">
            <SynapticStream />
          </div>
        </motion.div>
      </div>

      {/* Bottom: Intent Broadcast */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex flex-col items-center gap-6 pointer-events-auto w-full max-w-4xl">
        <div className="glass-panel w-full rounded-sm p-3 flex items-center gap-4 bg-[#020408]/80 border-[#00FFFF]/30 shadow-[0_0_50px_rgba(0,255,255,0.15)] group transition-all hover:border-[#00FFFF]/60">
          <Terminal className="w-4 h-4 text-[#00FFFF] ml-2 animate-pulse" />
          <input 
            type="text" 
            placeholder="BROADCAST_INTENT >> e.g. 'Optimize graph traversal for large datasets'"
            className="flex-1 bg-transparent border-none outline-none text-[11px] font-mono text-white placeholder:text-[#00FFFF]/30 tracking-wider"
          />
          <button className="px-6 py-2 rounded-sm bg-[#00FFFF]/10 border border-[#00FFFF]/40 text-[#00FFFF] text-[10px] font-black tracking-[0.4em] hover:bg-[#00FFFF]/20 hover:shadow-[0_0_20px_rgba(0,255,255,0.3)] transition-all">
            EXECUTE_CMD [0x42]
          </button>
        </div>
      </div>

    </div>
  );
}
