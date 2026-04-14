import { motion } from 'framer-motion';
import { ShoppingBag, Star, Zap, Shield, Search, Activity } from 'lucide-react';


import { useState } from 'react';

const MOCK_AGENTS = [
  { id: 1, name: 'Architect-Prime', type: 'Planner', rating: 4.9, cost: '0.04/task', color: '#00FFFF', desc: 'Strategic planner for high-level swarm orchestration.' },
  { id: 2, name: 'Synthesizer-X', type: 'Executor', rating: 4.8, cost: '0.02/task', color: '#c084fc', desc: 'Code and content synthesis agent with multi-modal support.' },
  { id: 3, name: 'Guardian-Auth', type: 'Security', rating: 5.0, cost: '0.05/task', color: '#FF5F1F', desc: 'Zero-trust security auditor for sensitive workspace access.' },
  { id: 4, name: 'Refiner-Beta', type: 'Aggregator', rating: 4.7, cost: '0.01/task', color: '#39FF14', desc: 'Efficient data refiner and knowledge graph optimizer.' },
];

export function MarketplaceV2() {
  const [selectedAgent, setSelectedAgent] = useState<any>(null);

  return (
    <div className="absolute inset-0 p-12 overflow-y-auto custom-scrollbar">
      {/* Detail Overlay */}
      {selectedAgent && (
        <motion.div 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="fixed inset-0 bg-[#020408]/80 backdrop-blur-md z-[100] flex items-center justify-center p-12"
          onClick={() => setSelectedAgent(null)}
        >
          <motion.div 
            initial={{ scale: 0.9, y: 20 }}
            animate={{ scale: 1, y: 0 }}
            className="glass-panel w-full max-w-2xl p-8 rounded-3xl"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex justify-between items-start mb-8">
              <div className="flex gap-6 items-center">
                 <div className="w-20 h-20 rounded-2xl bg-white/5 flex items-center justify-center">
                    <ShoppingBag size={40} color={selectedAgent.color} />
                 </div>
                 <div>
                    <h2 className="text-2xl font-bold tracking-widest uppercase">{selectedAgent.name}</h2>
                    <div className="text-[#00FFFF] text-xs font-bold tracking-widest">{selectedAgent.type}</div>
                 </div>
              </div>
              <button 
                onClick={() => setSelectedAgent(null)}
                className="text-white/40 hover:text-white"
              >
                CLOSE [X]
              </button>
            </div>
            <p className="text-white/60 mb-8 leading-relaxed italic">{selectedAgent.desc}</p>
            <div className="grid grid-cols-2 gap-4 mb-8">
               <div className="bg-white/5 p-4 rounded-xl">
                  <div className="text-[10px] text-white/30 uppercase mb-1">Reliability_Score</div>
                  <div className="text-xl font-mono text-[#39FF14]">{selectedAgent.rating * 20}%</div>
               </div>
               <div className="bg-white/5 p-4 rounded-xl">
                  <div className="text-[10px] text-white/30 uppercase mb-1">Inference_Cost</div>
                  <div className="text-xl font-mono text-[#00FFFF]">{selectedAgent.cost}</div>
               </div>
            </div>
            <button className="w-full py-4 rounded-xl bg-[#00FFFF] text-[#020408] font-bold tracking-[0.2em] shadow-[0_0_30px_rgba(0,255,255,0.3)] hover:scale-[1.02] transition-all">
                PROVISION_BLUEPRINT
            </button>
          </motion.div>
        </motion.div>
      )}

      <div className="max-w-6xl mx-auto space-y-12">

        
        {/* Header */}
        <div className="flex justify-between items-end border-b border-[#00FFFF]/20 pb-8">
          <div>
            <h1 className="glow-text-cyan text-[32px] font-bold tracking-[0.2em] uppercase">Swarm_Marketplace</h1>
            <p className="text-white/40 text-[12px] mt-2 font-mono">NEURAL_PROVISIONING_GATEWAY ACTIVE</p>
          </div>
          <div className="flex items-center gap-4 bg-white/5 border border-white/10 rounded-full px-6 py-3">
             <Search size={16} className="text-[#00FFFF]/60" />
             <input 
               type="text" 
               placeholder="Search neural blueprints..." 
               className="bg-transparent border-none outline-none text-[12px] text-white w-64"
             />
          </div>
        </div>

        {/* Featured Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {MOCK_AGENTS.map((agent, i) => (
            <motion.div
              key={agent.id}
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ delay: i * 0.1 }}
              className="glass-panel p-6 rounded-2xl hover:border-[#00FFFF]/50 transition-all cursor-pointer group relative overflow-hidden"
            >
              {/* Decorative Glow */}
              <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-br from-white/10 to-transparent rotate-45 translate-x-12 -translate-y-12" />
              
              <div className="w-12 h-12 rounded-xl bg-white/5 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                <ShoppingBag size={24} color={agent.color} />
              </div>
              
              <h3 className="text-white font-bold text-[16px] mb-1">{agent.name}</h3>
              <div className="text-[10px] text-[#00FFFF] font-bold tracking-widest uppercase mb-4">{agent.type}</div>
              
              <div className="flex items-center gap-2 mb-6">
                 <Star size={12} className="fill-[#FFD700] text-[#FFD700]" />
                 <span className="text-[12px] text-white/80">{agent.rating}</span>
                 <span className="text-white/20 px-2">|</span>
                 <span className="text-[12px] text-white/40">{agent.cost}</span>
              </div>

              <div className="flex gap-2">
                 <button 
                   onClick={() => setSelectedAgent(agent)}
                   className="flex-1 py-2 rounded-lg bg-[#00FFFF]/10 border border-[#00FFFF]/20 text-white text-[10px] font-bold hover:bg-[#00FFFF]/20 transition-all"
                 >
                    DETAILS
                 </button>

                 <button className="p-2 rounded-lg bg-[#00FFFF] text-[#020408] hover:shadow-[0_0_15px_rgba(0,255,255,0.5)] transition-all">
                    <Zap size={14} fill="currentColor" />
                 </button>
              </div>
            </motion.div>
          ))}
        </div>

        {/* System Status / Stats Section */}
        <div className="grid grid-cols-3 gap-6">
           <div className="glass-panel p-6 rounded-2xl border-l-4 border-l-[#39FF14]">
              <div className="flex items-center gap-3 mb-2">
                 <Zap className="text-[#39FF14]" size={18} />
                 <span className="text-[10px] text-white/40 font-bold tracking-widest uppercase">System Latency</span>
              </div>
              <div className="text-[20px] text-white font-mono">14ms</div>
           </div>
           <div className="glass-panel p-6 rounded-2xl border-l-4 border-l-[#00FFFF]">
              <div className="flex items-center gap-3 mb-2">
                 <Shield className="text-[#00FFFF]" size={18} />
                 <span className="text-[10px] text-white/40 font-bold tracking-widest uppercase">Encryption</span>
                 <span className="text-[#39FF14] text-[8px] border border-[#39FF14]/50 rounded px-1 ml-auto">ACTIVE</span>
              </div>
              <div className="text-[20px] text-white font-mono">SHA-9512</div>
           </div>
           <div className="glass-panel p-6 rounded-2xl border-l-4 border-l-[#FF5F1F]">
              <div className="flex items-center gap-3 mb-2">
                 <Activity className="text-[#FF5F1F]" size={18} />
                 <span className="text-[10px] text-white/40 font-bold tracking-widest uppercase">Network Congestion</span>
              </div>
              <div className="text-[20px] text-white font-mono">0.04%</div>
           </div>
        </div>

      </div>
    </div>
  );
}
