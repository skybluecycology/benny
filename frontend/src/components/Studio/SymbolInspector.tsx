import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Info, 
  FileCode, 
  Link, 
  Hash, 
  MapPin, 
  Zap, 
  ArrowRight,
  Database,
  Search,
  ChevronRight,
  Clock,
  ExternalLink
} from 'lucide-react';

interface InspectorProps {
  selection: {
    type: 'node' | 'edge';
    data: any;
  } | null;
  onClose: () => void;
}

export function SymbolInspector({ selection, onClose }: InspectorProps) {
  if (!selection) return null;

  const { type, data } = selection;

  return (
    <motion.div
      initial={{ x: '100%' }}
      animate={{ x: 0 }}
      exit={{ x: '100%' }}
      className="absolute top-24 bottom-24 right-0 w-[320px] bg-[#020408]/60 backdrop-blur-2xl border-l border-white/10 z-40 flex flex-col shadow-[-20px_0_40px_rgba(0,0,0,0.5)]"
    >
      {/* Header */}
      <div className="p-6 border-b border-white/5 flex items-center justify-between bg-white/2">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-sm ${type === 'node' ? 'bg-[#00FFFF]/10 text-[#00FFFF]' : 'bg-[#FF5F1F]/10 text-[#FF5F1F]'}`}>
            {type === 'node' ? <FileCode size={16} /> : <Link size={16} />}
          </div>
          <div className="flex flex-col">
            <span className="text-[10px] font-black tracking-[0.2em] text-white/40 uppercase">
              {type === 'node' ? 'Symbol_Inspector' : 'Relation_Inspector'}
            </span>
            <span className="text-[12px] font-black text-white tracking-widest truncate max-w-[180px]">
              {data.name || data.type || 'UNKNOWN'}
            </span>
          </div>
        </div>
        <button onClick={onClose} className="p-2 text-white/20 hover:text-white transition-all">
          <ChevronRight size={20} />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-6 space-y-8 custom-scrollbar">
        
        {/* Basic Info */}
        <section className="space-y-4">
           <div className="flex items-center gap-2 text-[9px] font-black text-[#00FFFF] tracking-[0.3em] uppercase">
              <Info size={10} /> Core_Metadata
           </div>
           
           <div className="space-y-3">
              <div className="space-y-1">
                <div className="text-[8px] text-white/20 uppercase tracking-widest font-black">Type</div>
                <div className="text-[10px] text-white/80 font-mono tracking-wider">{data.type || 'N/A'}</div>
              </div>

              {type === 'node' && (
                <div className="space-y-1">
                  <div className="text-[8px] text-white/20 uppercase tracking-widest font-black">Location</div>
                  <div className="text-[10px] text-white/80 font-mono tracking-wider break-all flex items-start gap-2">
                    <MapPin size={10} className="mt-0.5 shrink-0 text-[#00FFFF]/40" />
                    {data.path || 'Unknown Path'}
                  </div>
                </div>
              )}

              {type === 'edge' && (
                <>
                  <div className="space-y-1">
                    <div className="text-[8px] text-white/20 uppercase tracking-widest font-black">Origin</div>
                    <div className="text-[10px] text-white/80 font-mono tracking-wider truncate text-[#00FFFF]">{data.sourceName || data.source}</div>
                  </div>
                  <div className="flex justify-center opacity-20"><ArrowRight size={14} /></div>
                  <div className="space-y-1">
                    <div className="text-[8px] text-white/20 uppercase tracking-widest font-black">Target</div>
                    <div className="text-[10px] text-white/80 font-mono tracking-wider truncate text-[#FF5F1F]">{data.targetName || data.target}</div>
                  </div>
                </>
              )}
           </div>
        </section>

        {/* Dynamic Details */}
        <section className="space-y-4">
           <div className="flex items-center gap-2 text-[9px] font-black text-[#00FFFF] tracking-[0.3em] uppercase">
              <Zap size={10} /> Functional_Context
           </div>
           
           <div className="p-4 bg-white/2 border border-white/5 rounded-sm space-y-3">
              <div className="text-[9px] text-white/40 leading-relaxed uppercase tracking-widest font-mono">
                {type === 'node' 
                   ? `Architectural symbol mapped from cross-stack recursive analysis. Contributes to overall system centrality.`
                   : `Directed UML relationship representing ${data.type} logic between entities.`
                }
              </div>
           </div>
        </section>

        {/* Database Identifiers */}
        <section className="space-y-4">
           <div className="flex items-center gap-2 text-[9px] font-black text-white/20 tracking-[0.3em] uppercase">
              <Database size={10} /> DB_INDEX_P0
           </div>
           <div className="space-y-2">
              <div className="px-3 py-2 bg-[#00FFFF]/5 border border-[#00FFFF]/10 text-[8px] font-mono text-[#00FFFF]/60 break-all leading-tight">
                ID: {data.id || data.elementId || 'NO_INDEX'}
              </div>
           </div>
        </section>

      </div>

      {/* Footer */}
      <div className="p-4 border-t border-white/5">
         <button className="w-full h-10 btn-pill border-white/10 text-white/40 hover:text-white hover:border-white/40 text-[9px] font-black tracking-[0.2em] flex items-center justify-center gap-2 transition-all">
            <ExternalLink size={12} /> OPEN_SOURCE_FILE
         </button>
      </div>

    </motion.div>
  );
}
