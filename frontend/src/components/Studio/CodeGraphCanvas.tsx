import React, { useRef, useMemo, useState, useEffect } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Stars, Text, Sphere, Box, Octahedron, Line, Float, MeshDistortMaterial, Html } from '@react-three/drei';
import * as THREE from 'three';
import { motion, AnimatePresence } from 'framer-motion';
import { useWorkflowStore } from '../../hooks/useWorkflowStore';
import { useWorkspaceStore } from '../../hooks/useWorkspaceStore';
import { API_BASE_URL, GOVERNANCE_HEADERS } from '../../constants';
import { Folder, Play, RefreshCw, Layers, Filter } from 'lucide-react';

// --- Visual Components ---

interface CodeNodeProps {
  position: [number, number, number];
  name: string;
  type: string;
  isSelected: boolean;
  onClick: () => void;
}

function CodeSymbolNode({ position, name, type, isSelected, onClick }: CodeNodeProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  
  useFrame((state) => {
    if (meshRef.current) {
      meshRef.current.rotation.y += 0.01;
    }
  });

  const getGeometry = () => {
    switch (type) {
      case 'File': return <octahedronGeometry args={[0.5, 0]} />;
      case 'Class': return <boxGeometry args={[0.6, 0.6, 0.6]} />;
      case 'Interface': return <boxGeometry args={[0.5, 0.5, 0.5]} />;
      case 'Function': return <sphereGeometry args={[0.3, 16, 16]} />;
      default: return <sphereGeometry args={[0.2, 8, 8]} />;
    }
  };

  const getColor = () => {
    if (isSelected) return "#FFFFFF";
    switch (type) {
      case 'File': return "#00FFFF";
      case 'Class': return "#007ACC";
      case 'Interface': return "#39FF14";
      case 'Function': return "#FF5F1F";
      default: return "#888888";
    }
  };

  return (
    <Float speed={2} rotationIntensity={0.5} floatIntensity={0.5}>
      <mesh 
        ref={meshRef} 
        position={position} 
        onClick={(e) => { e.stopPropagation(); onClick(); }}
      >
        {getGeometry()}
        <MeshDistortMaterial 
          color={getColor()} 
          speed={2} 
          distort={isSelected ? 0.3 : 0} 
          transparent 
          opacity={0.8}
          emissive={getColor()}
          emissiveIntensity={isSelected ? 3 : 0.5}
        />
      </mesh>
      <Text
        position={[0, -0.8, 0]}
        fontSize={0.2}
        color="#ffffff"
        opacity={0.6}
        maxWidth={2}
        textAlign="center"
      >
        {name}
      </Text>
    </Float>
  );
}

// --- Main Canvas Component ---

export function CodeGraphCanvas() {
  const { currentWorkspace } = useWorkspaceStore();
  const { codeGraph, setCodeGraph, isCodeGraphScanOpen, setIsCodeGraphScanOpen } = useWorkflowStore();
  const [directories, setDirectories] = useState<string[]>([]);
  const [selectedDir, setSelectedDir] = useState("/");
  const [isGenerating, setIsGenerating] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  useEffect(() => {
    fetchDirs();
    if (!codeGraph) {
      setIsCodeGraphScanOpen(true);
      fetchGraph();
    }
  }, [currentWorkspace]);

  const fetchDirs = async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/api/graph/dirs?workspace=${currentWorkspace}`, {
         headers: { ...GOVERNANCE_HEADERS }
      });
      if (resp.ok) {
        const data = await resp.ok ? await resp.json() : { directories: [] };
        setDirectories(data.directories || ["/"]);
      }
    } catch (e) {
      console.error("Failed to fetch dirs", e);
    }
  };

  const fetchGraph = async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/api/graph/code?workspace=${currentWorkspace}`, {
         headers: { ...GOVERNANCE_HEADERS }
      });
      if (resp.ok) {
        const data = await resp.json();
        if (data.nodes && data.nodes.length > 0) {
          setCodeGraph(data);
          setIsCodeGraphScanOpen(false);
        }
      }
    } catch (e) {
      console.error("Failed to fetch graph", e);
    }
  };

  const handleGenerate = async () => {
    setIsGenerating(true);
    try {
      const resp = await fetch(`${API_BASE_URL}/api/graph/code/generate`, {
        method: "POST",
        headers: { ...GOVERNANCE_HEADERS, "Content-Type": "application/json" },
        body: JSON.stringify({ workspace: currentWorkspace, root_dir: selectedDir === "/" ? "" : selectedDir })
      });
      if (resp.ok) {
        // Wait a bit then fetch
        setTimeout(() => {
          fetchGraph();
          setIsGenerating(false);
          setIsCodeGraphScanOpen(false);
        }, 3000);
      }
    } catch (e) {
      console.error("Failed to generate", e);
      setIsGenerating(false);
    }
  };

  // Layout logic: simple force-ish spread based on path hierarchy
  const processedGraph = useMemo(() => {
    if (!codeGraph) return { nodes: [], edges: [] };
    
    const nodes = codeGraph.nodes.map((node: any, i: number) => {
       // Deterministic position based on path parts
       const parts = node.path.split('/');
       const depth = parts.length;
       const angle = (i / codeGraph.nodes.length) * Math.PI * 2;
       const radius = depth * 4 + 5;
       
       return {
         ...node,
         pos: [
            Math.cos(angle) * radius,
            (Math.random() - 0.5) * 10,
            Math.sin(angle) * radius
         ] as [number, number, number]
       };
    });

    const edges = codeGraph.edges.map((edge: any) => {
       const sourceNode = nodes.find(n => n.id === edge.source);
       const targetNode = nodes.find(n => n.id === edge.target);
       return {
         ...edge,
         sourcePos: sourceNode?.pos || [0,0,0],
         targetPos: targetNode?.pos || [0,0,0]
       };
    });

    return { nodes, edges };
  }, [codeGraph]);

  return (
    <div className="absolute inset-0 bg-[#020408]">
      
      {/* 3D Canvas */}
      <Canvas camera={{ position: [0, 20, 40], fov: 60 }}>
        <color attach="background" args={['#020408']} />
        <ambientLight intensity={0.4} />
        <pointLight position={[10, 10, 10]} intensity={1} color="#00FFFF" />
        <Stars radius={100} depth={50} count={10000} factor={4} saturation={1} fade speed={1.5} />
        
        {processedGraph.nodes.map((node: any) => (
          <CodeSymbolNode 
            key={node.id}
            position={node.pos}
            name={node.name}
            type={node.type}
            isSelected={selectedNodeId === node.id}
            onClick={() => setSelectedNodeId(node.id)}
          />
        ))}

        {processedGraph.edges.map((edge: any, i: number) => {
          const color = edge.type === 'INHERITS' ? '#00FFFF' : 
                        edge.type === 'DEFINES' ? '#ffffff' : 
                        '#FF5F1F';
          const opacity = edge.type === 'DEFINES' ? 0.1 : 0.4;
          
          return (
            <Line 
               key={`${edge.source}-${edge.target}-${i}`}
               points={[edge.sourcePos, edge.targetPos]}
               color={color}
               transparent
               opacity={opacity}
               dashed={edge.type === 'DEPENDS_ON'}
               dashScale={2}
               dashSize={0.5}
            />
          );
        })}

        <OrbitControls enablePan enableZoom enableRotate />
      </Canvas>

      {/* Overlays */}
      <AnimatePresence>
        {isCodeGraphScanOpen && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-50 flex items-center justify-center backdrop-blur-md bg-[#020408]/80"
          >
            <div className="bg-white/5 border border-[#00FFFF]/20 p-8 rounded-lg max-w-md w-full space-y-6">
              <div className="text-center space-y-2">
                <Layers className="w-12 h-12 text-[#00FFFF] mx-auto animate-pulse" />
                <h2 className="text-xl font-black tracking-[0.2em] text-[#00FFFF]">NEURAL_CODE_SCAN</h2>
                <p className="text-[10px] text-[#00FFFF]/60 uppercase tracking-widest leading-relaxed">
                  Initialize recursive analysis to map your cross-stack architecture.
                </p>
              </div>

              <div className="space-y-4">
                 <div className="flex items-center gap-3 p-3 bg-white/5 border border-white/10 rounded-sm">
                    <Folder className="w-4 h-4 text-[#00FFFF]/60" />
                    <select 
                      value={selectedDir}
                      onChange={(e) => setSelectedDir(e.target.value)}
                      className="bg-transparent border-none outline-none text-[11px] font-mono text-white flex-1 cursor-pointer"
                    >
                      {directories.map(d => (
                        <option key={d} value={d} className="bg-[#020408]">{d}</option>
                      ))}
                    </select>
                 </div>

                 <button 
                   onClick={handleGenerate}
                   disabled={isGenerating}
                   className="w-full btn-pill h-12 flex items-center justify-center gap-3 bg-[#00FFFF]/10 border border-[#00FFFF]/60 text-[#00FFFF] group hover:bg-[#00FFFF]/20 disabled:opacity-50"
                 >
                   {isGenerating ? (
                      <RefreshCw className="w-4 h-4 animate-spin" />
                   ) : (
                      <Play className="w-4 h-4 group-hover:scale-125 transition-transform" />
                   )}
                   <span className="text-[10px] font-black tracking-[0.3em]">START_RECURSIVE_SCAN</span>
                 </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Floating Controls */}
      <div className="absolute top-24 right-12 flex flex-col gap-4 pointer-events-auto">
         <button onClick={() => setIsCodeGraphScanOpen(true)} className="btn-pill px-6 h-12 flex items-center gap-3 bg-[#00FFFF]/10 border border-[#00FFFF]/40 hover:border-[#00FFFF] shadow-[0_0_15px_rgba(0,255,255,0.1)] transition-all">
            <RefreshCw size={16} className={isGenerating ? "animate-spin text-[#00FFFF]" : "text-[#00FFFF]"} /> 
            <span className="text-[11px] font-black tracking-[0.2em] text-[#00FFFF]">RE_SCAN</span>
         </button>
           <div className="p-4 bg-[#020408]/60 backdrop-blur-xl border border-white/5 rounded-sm space-y-3">
              <div className="flex items-center gap-2 text-[9px] font-black text-[#00FFFF]/60 tracking-[0.2em]">
                 <Filter size={10} /> LAYER_FILTERS
              </div>
              <div className="space-y-2">
                 <div className="flex items-center justify-between gap-4">
                    <span className="text-[10px] text-white/40">INHERITANCE</span>
                    <div className="w-8 h-4 rounded-full bg-[#00FFFF]/20 border border-[#00FFFF]/40" />
                 </div>
                 <div className="flex items-center justify-between gap-4">
                    <span className="text-[10px] text-white/40">DEPENDENCIES</span>
                    <div className="w-8 h-4 rounded-full bg-[#FF5F1F]/20 border border-[#FF5F1F]/40" />
                 </div>
              </div>
           </div>
        </div>

    </div>
  );
}
