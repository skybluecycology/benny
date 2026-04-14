import { motion } from 'framer-motion';
import { useWorkflowStore } from '../../hooks/useWorkflowStore';
import { Clock, ChevronLeft, ChevronRight, Play, Pause } from 'lucide-react';
import { useMemo } from 'react';

export function TemporalAudit() {
  const { executionEvents, playbackIndex, setPlaybackIndex } = useWorkflowStore();

  const events = useMemo(() => {
    // Group events or filter for relevant 'checkpoints'
    return executionEvents.filter(e => 
      e.type === 'node_started' || 
      e.type === 'node_completed' || 
      e.type === 'node_error' ||
      e.type === 'workflow_completed'
    );
  }, [executionEvents]);

  const currentIndex = playbackIndex !== null ? playbackIndex : events.length - 1;

  return (
    <div className="flex flex-col h-full glass-panel rounded-lg p-4 pointer-events-auto border-l-4 border-l-amber-500/30 overflow-hidden">
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <h3 className="glow-text-orange text-[12px] font-bold tracking-widest flex items-center gap-2">
          <Clock className="w-4 h-4" />
          TEMPORAL_SCRUBBER
        </h3>
        <div className="flex gap-2">
           <button 
             onClick={() => setPlaybackIndex(null)}
             className={`text-[8px] px-2 py-1 rounded border transition-colors ${playbackIndex === null ? 'bg-amber-500 text-black border-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.5)]' : 'text-amber-500 border-amber-500/30 hover:bg-amber-500/10'} font-bold`}
           >
             LIVE
           </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar relative pr-2">
        {/* The Timeline Line */}
        <div className="absolute left-3 top-0 bottom-0 w-[1px] bg-amber-500/20" />
        
        <div className="space-y-4 pl-8 relative pb-2">
          {events.map((event, i) => {
            const isSelected = i === currentIndex && playbackIndex !== null;
            
            return (
              <motion.div 
                key={i}
                initial={{ x: -10, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                transition={{ delay: i * 0.05 }}
                className={`relative cursor-pointer group transition-all ${isSelected ? 'scale-[1.02]' : 'opacity-60 hover:opacity-100'}`}
                onClick={() => setPlaybackIndex(i)}
              >
                {/* Node on the line */}
                <div className={`absolute -left-[21px] w-3 h-3 rounded-full border-2 border-[#020408] z-10 transition-all
                  ${isSelected ? 'bg-amber-500 scale-125 shadow-[0_0_10px_rgba(245,158,11,0.8)]' : 
                    event.type === 'node_error' ? 'bg-red-500' : 
                    event.type === 'node_completed' ? 'bg-green-500' : 'bg-amber-500/40'}`} 
                />
                
                <div className={`p-2 rounded border transition-colors ${isSelected ? 'bg-amber-500/20 border-amber-500/50 shadow-[0_0_15px_rgba(245,158,11,0.1)]' : 'bg-white/5 border-white/10'}`}>
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-[9px] font-bold uppercase tracking-tighter truncate w-32">
                      {event.nodeId?.split('.').pop() || 'SYSTEM'}
                    </span>
                    <span className="text-[8px] opacity-40 font-mono">
                      {typeof event.timestamp === 'string' ? event.timestamp.split('T')[1]?.slice(0, 5) || '00:00' : '00:00'}
                    </span>
                  </div>
                  <div className="text-[8px] opacity-70 leading-tight">
                    {event.type.split('_').join(' ').toUpperCase()}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      {/* Playback Controls */}
      <div className="mt-4 pt-4 border-t border-white/10 flex justify-center gap-4 flex-shrink-0">
        <button 
           className="text-white/40 hover:text-amber-500 transition-colors"
           onClick={() => currentIndex > 0 && setPlaybackIndex(currentIndex - 1)}
        >
          <ChevronLeft size={16} />
        </button>
        <button className="text-amber-500 hover:scale-110 transition-transform">
           {playbackIndex === null ? <Pause size={16} fill="currentColor" /> : <Play size={16} fill="currentColor" />}
        </button>
        <button 
           className="text-white/40 hover:text-amber-500 transition-colors"
           onClick={() => (events.length > 0 && currentIndex < events.length - 1) && setPlaybackIndex(currentIndex + 1)}
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}
