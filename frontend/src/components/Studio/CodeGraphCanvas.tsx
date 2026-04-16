import React, { useRef, useMemo, useState, useEffect } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { 
  OrbitControls, 
  Stars, 
  Text, 
  Sphere, 
  Box, 
  Octahedron, 
  Line, 
  Float, 
  MeshDistortMaterial, 
  Html, 
  CameraControls,
  KeyboardControls,
  useKeyboardControls,
  Points,
  PointMaterial
} from '@react-three/drei';
import * as THREE from 'three';
import { motion, AnimatePresence } from 'framer-motion';
import { useWorkflowStore } from '../../hooks/useWorkflowStore';
import { useWorkspaceStore } from '../../hooks/useWorkspaceStore';
import { API_BASE_URL, GOVERNANCE_HEADERS } from '../../constants';
import { 
  Folder as FolderIcon, 
  Play, 
  RefreshCw, 
  Layers, 
  Filter, 
  Terminal, 
  ChevronRight, 
  Home, 
  ExternalLink,
  Target,
  Zap,
  Info,
  Share2
} from 'lucide-react';
import { SymbolInspector } from './SymbolInspector';

// --- Visual Components ---

interface CodeNodeProps {
  id: string;
  position: [number, number, number];
  name: string;
  type: string;
  isSelected: boolean;
  isClusterMode: boolean;
  metadata?: any;
  onClick: () => void;
}

function FloatingMetadataHUD({ metadata, hovered }: { metadata: any, hovered: boolean }) {
  if (!hovered || !metadata) return null;

  const entries = Object.entries(metadata).filter(([_, v]) => v && typeof v !== 'object').slice(0, 4);

  return (
    <group>
      {entries.map(([key, value], i) => {
        const angle = (i / entries.length) * Math.PI * 2;
        const radius = 1.2;
        return (
          <Html key={key} position={[Math.cos(angle) * radius, Math.sin(angle) * radius, 0]} center>
            <motion.div 
              initial={{ scale: 0, opacity: 0, y: 0 }}
              animate={{ scale: 1, opacity: 1, y: -20 }}
              className="px-2 py-1 rounded-sm bg-[#00FFFF]/10 border border-[#00FFFF]/30 backdrop-blur-md"
            >
              <div className="text-[6px] text-[#00FFFF]/60 uppercase font-black tracking-tighter">{key}</div>
              <div className="text-[8px] text-white font-mono whitespace-nowrap">{String(value)}</div>
            </motion.div>
          </Html>
        );
      })}
    </group>
  );
}

function NeuralSpark({ node, active }: { node: any, active: boolean }) {
  const groupRef = useRef<THREE.Group>(null);
  
  useFrame((state) => {
    if (groupRef.current && active) {
      groupRef.current.rotation.y += 0.02;
      groupRef.current.rotation.x += 0.01;
    }
  });

  if (!active || !node.metadata) return null;

  // Projection of labels or related concepts as orbiting satellites
  const satellites = [
    { label: node.type, color: "#00FFFF" },
    { label: node.metadata.community_name || 'Neural Nexus', color: "#FF00FF" },
    { label: node.metadata.strategy || 'safe', color: "#39FF14" }
  ].filter(s => s.label);

  return (
    <group ref={groupRef}>
      {satellites.map((sat, i) => {
        const phi = Math.acos(-1 + (2 * i) / satellites.length);
        const theta = Math.sqrt(satellites.length * Math.PI) * phi;
        const radius = 1.5;
        
        return (
          <group 
            key={i} 
            position={[
              radius * Math.cos(theta) * Math.sin(phi),
              radius * Math.sin(theta) * Math.sin(phi),
              radius * Math.cos(phi)
            ]}
          >
            <Html center>
              <motion.div 
                initial={{ opacity: 0, scale: 0 }}
                animate={{ opacity: 1, scale: 1 }}
                className="pointer-events-none select-none"
              >
                <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-black/60 border border-white/20 backdrop-blur-md">
                   <div className="w-1 h-1 rounded-full animate-pulse" style={{ backgroundColor: sat.color }} />
                   <span className="text-[7px] text-white/80 font-mono uppercase tracking-widest">{sat.label}</span>
                </div>
              </motion.div>
            </Html>
          </group>
        );
      })}
      
      {/* Orbital Ring */}
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <ringGeometry args={[1.4, 1.42, 64]} />
        <meshBasicMaterial color="#00FFFF" transparent opacity={0.1} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

function CodeSymbolNode({ id, position, name, type, isSelected, isClusterMode, metadata, onClick }: CodeNodeProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);
  const [, getKeys] = useKeyboardControls();
  
  useEffect(() => {
    document.body.style.cursor = hovered ? 'pointer' : 'auto';
    return () => { document.body.style.cursor = 'auto'; };
  }, [hovered]);

  useFrame((state) => {
    if (meshRef.current) {
      meshRef.current.rotation.y += 0.01;
      if (isSelected || hovered) {
         meshRef.current.scale.lerp(new THREE.Vector3(1.8, 1.8, 1.8), 0.1);
      } else {
         meshRef.current.scale.lerp(new THREE.Vector3(1, 1, 1), 0.1);
      }
    }
  });

  const getGeometry = () => {
    switch (type) {
      case 'Folder': return <boxGeometry args={[0.7, 0.7, 0.7]} />; // Folder is slightly larger box
      case 'File': return <octahedronGeometry args={[0.5, 0]} />;
      case 'Documentation': return <octahedronGeometry args={[0.6, 0]} />; // Docs are larger octahedrons
      case 'Class': return <boxGeometry args={[0.6, 0.6, 0.6]} />;
      case 'Interface': return <boxGeometry args={[0.5, 0.5, 0.5]} />;
      case 'Function': return <sphereGeometry args={[0.3, 16, 16]} />;
      case 'Concept': return <sphereGeometry args={[0.4, 24, 24]} />; // Concepts are glowing orbs
      default: return <sphereGeometry args={[0.2, 8, 8]} />;
    }
  };

  const getColor = () => {
    if (isSelected) return "#FFFFFF";
    if (hovered) return "#00FFFF";
    switch (type) {
      case 'Folder': return "#FFD700"; // Gold for Folders
      case 'File': return "#00FFFF";
      case 'Class': return "#007ACC";
      case 'Interface': return "#39FF14";
      case 'Function': return "#FF5F1F";
      case 'Documentation': return "#00FFFF";
      case 'Concept': return "#FF00FF";
      default: return "#888888";
    }
  };

  const getNodeColor = () => {
    // If community_id is present and we are in cluster mode (conceptual), use HSL
    if (isClusterMode && metadata?.community_id !== undefined) {
      return `hsl(${(metadata.community_id * 137.5) % 360}, 70%, 60%)`;
    }
    return getColor();
  };

  return (
    <group 
      position={position}
      onPointerOver={(e) => { e.stopPropagation(); setHovered(true); }}
      onPointerOut={() => setHovered(false)}
    >
      <Float speed={2} rotationIntensity={0.5} floatIntensity={0.5}>
        <mesh 
          ref={meshRef} 
          onClick={(e) => { e.stopPropagation(); onClick(); }}
        >
          {getGeometry()}
          <MeshDistortMaterial 
            color={getNodeColor()} 
            speed={hovered ? 5 : 2} 
            distort={isSelected || hovered ? 0.4 : 0} 
            transparent 
            opacity={0.8}
            emissive={getNodeColor()}
            emissiveIntensity={isSelected || hovered ? 5 : 0.5}
          />
        </mesh>
      </Float>

      <NeuralSpark node={{ id, name, type, metadata }} active={isSelected || hovered} />
      <FloatingMetadataHUD metadata={metadata} hovered={hovered} />
      
      <Html distanceFactor={10} position={[0, -0.8, 0]}>
        <div className={`whitespace-nowrap px-2 py-1 rounded bg-black/80 border border-white/10 text-[8px] font-mono text-white pointer-events-none transition-all duration-300 ${isSelected || hovered ? 'opacity-100 scale-110 border-[#00FFFF]/40 shadow-[0_0_10px_rgba(0,255,255,0.2)]' : 'opacity-40'}`}>
          {name}
        </div>
      </Html>
    </group>
  );
}

// --- Visual Components ---

function UMLArrowhead({ start, end, type, color, opacity, isSelected }: { start: THREE.Vector3, end: THREE.Vector3, type: string, color: string, opacity: number, isSelected: boolean }) {
  const dir = new THREE.Vector3().subVectors(end, start).normalize();
  
  // Offset to place arrowhead at the surface of the node (approximate)
  const offsetEnd = end.clone().sub(dir.clone().multiplyScalar(0.4));
  
  const isInherits = type === 'INHERITS';
  const isCalls = type === 'CALLS' || type === 'DEPENDS_ON';
  
  if (!isInherits && !isCalls) return null;

  return (
    <mesh 
      position={offsetEnd} 
      onUpdate={(self) => {
        self.lookAt(end);
        self.rotateX(Math.PI / 2);
      }}
    >
      {isInherits ? (
        <coneGeometry args={[0.25, 0.5, 3]} />
      ) : (
        <coneGeometry args={[0.15, 0.4, 8]} />
      )}
      <meshBasicMaterial 
        color={isInherits ? "#ffffff" : color} 
        transparent 
        opacity={opacity * 1.5}
        wireframe={isInherits}
      />
    </mesh>
  );
}

// --- Interactive Edge Component ---

function CodeGraphEdge({ edge, isSelected, isNodeSelected, onClick }: { edge: any, isSelected: boolean, isNodeSelected: boolean, onClick: () => void }) {
  const [hovered, setHovered] = useState(false);
  
  useEffect(() => {
    if (hovered) document.body.style.cursor = 'pointer';
    return () => { document.body.style.cursor = 'auto'; };
  }, [hovered]);

  const getColor = () => {
    if (isSelected || hovered) return '#FFFFFF';
    switch(edge.type) {
      case 'INHERITS': return '#39FF14'; 
      case 'DEFINES': return '#ffffff';  
      case 'CALLS': return '#FF5F1F';    
      case 'DEPENDS_ON': return '#00FFFF'; 
      default: return '#888888';
    }
  };

  const start = new THREE.Vector3(...edge.sourcePos);
  const end = new THREE.Vector3(...edge.targetPos);
  const distance = start.distanceTo(end);
  const midpoint = start.clone().add(end).multiplyScalar(0.5);

  const edgeOpacity = isSelected || hovered ? 1 : isNodeSelected ? 0.9 : edge.type === 'DEFINES' ? 0.3 : 0.6;
  const lineWidth = (isSelected || hovered) ? 4 : (isNodeSelected ? 3 : (edge.type === 'INHERITS' ? 2.5 : 1.5));

  return (
    <group>
      {/* Visible Line */}
      <Line 
         points={[edge.sourcePos, edge.targetPos]}
         color={getColor()}
         transparent
         opacity={edgeOpacity}
         lineWidth={lineWidth}
         dashed={edge.type === 'DEPENDS_ON' || edge.type === 'CALLS'}
         dashScale={2}
         dashSize={0.5}
      />

      {/* UML Grounding Marker */}
      <UMLArrowhead 
        start={start} 
        end={end} 
        type={edge.type} 
        color={getColor()} 
        opacity={edgeOpacity}
        isSelected={isSelected || hovered}
      />

      {/* Invisible Hit-Tube */}
      <mesh 
        position={midpoint} 
        onPointerOver={(e) => { e.stopPropagation(); setHovered(true); }}
        onPointerOut={() => setHovered(false)}
        onClick={(e) => { e.stopPropagation(); onClick(); }}
        onUpdate={(self) => {
           self.lookAt(end);
           self.rotateX(Math.PI / 2);
        }}
      >
        <cylinderGeometry args={[0.5, 0.5, distance, 6]} />
        <meshBasicMaterial visible={false} />
      </mesh>
    </group>
  );
}

// --- Immersive Navigation ---

function SpaceNavigator({ controlsRef }: { controlsRef: any }) {
  const [, getKeys] = useKeyboardControls();
  const { camera } = useThree();
  const speed = 15; // Movement speed in units per second

  useFrame((state, delta) => {
    if (!controlsRef.current) return;

    const keys = getKeys();
    if (!keys) return;
    const { 
      forward = false, 
      backward = false, 
      left = false, 
      right = false, 
      ascend = false, 
      descend = false 
    } = keys;
    
    if (!forward && !backward && !left && !right && !ascend && !descend) return;

    const distance = speed * delta;

    // Movement deltas relative to camera orientation
    const moveZ = (forward ? 1 : 0) - (backward ? 1 : 0); // Positive = Forward
    const moveX = (right ? 1 : 0) - (left ? 1 : 0);    // Positive = Right
    const moveY = (ascend ? 1 : 0) - (descend ? 1 : 0); // Positive = Up

    // Lateral and Vertical movement (Trucking)
    if (moveX !== 0 || moveY !== 0) {
      controlsRef.current.truck(moveX * distance, moveY * distance, true);
    }

    // Forward/Backward movement
    if (moveZ !== 0) {
      const direction = new THREE.Vector3();
      camera.getWorldDirection(direction);
      direction.multiplyScalar(moveZ * distance);
      
      const newPos = camera.position.clone().add(direction);
      const target = new THREE.Vector3();
      controlsRef.current.getTarget(target);
      const newTarget = target.clone().add(direction);
      
      controlsRef.current.setLookAt(
        newPos.x, newPos.y, newPos.z,
        newTarget.x, newTarget.y, newTarget.z,
        true
      );
    }
  });

  return null;
}


const KEY_MAP = [
  { name: 'forward', keys: ['w', 'W', 'ArrowUp'] },
  { name: 'backward', keys: ['s', 'S', 'ArrowDown'] },
  { name: 'left', keys: ['a', 'A', 'ArrowLeft'] },
  { name: 'right', keys: ['d', 'D', 'ArrowRight'] },
  { name: 'ascend', keys: ['Space'] },
  { name: 'descend', keys: ['Shift'] },
];

function CodeGraphScene({ processedGraph, selectedNodeId, selectedEdgeId, onNodeClick, onEdgeClick, cameraControlsRef, showClusters }: any) {
  return (
    <>
      <color attach="background" args={['#020408']} />
      <ambientLight intensity={0.4} />
      <pointLight position={[10, 10, 10]} intensity={1} color="#00FFFF" />
      <Stars radius={100} depth={50} count={10000} factor={4} saturation={1} fade speed={1.5} />
      
      {/* Central Hub for Navigation Reference */}
      <mesh position={[0, 0, 0]}>
        <boxGeometry args={[2, 2, 2]} />
        <meshBasicMaterial color="#00FFFF" wireframe />
      </mesh>

      {processedGraph.nodes.map((node: any) => (
        <CodeSymbolNode 
          key={node.id} 
          {...node} 
          isSelected={selectedNodeId === node.id}
          isClusterMode={showClusters}
          onClick={() => onNodeClick(node)} 
        />
      ))}

      {processedGraph.edges.map((edge: any, i: number) => (
        <CodeGraphEdge 
          key={`${edge.source}-${edge.target}-${i}`}
          edge={edge}
          isSelected={selectedEdgeId === `${edge.source}-${edge.target}`}
          isNodeSelected={selectedNodeId === edge.source || selectedNodeId === edge.target}
          onClick={() => onEdgeClick(edge)}
        />
      ))}

      <SpaceNavigator controlsRef={cameraControlsRef} />
      <CameraControls 
        ref={cameraControlsRef} 
        makeDefault 
        dollySpeed={0.2}
        minDistance={5}
        maxDistance={400}
        draggingSmoothTime={0.3}
        smoothTime={0.5}
      />
    </>
  );
}

// --- Main Canvas Component ---

export function CodeGraphCanvas() {
  const { currentWorkspace, activeGraphId, focusPath, setFocusPath, setActiveDocument } = useWorkspaceStore();
  const { codeGraph, setCodeGraph, isCodeGraphScanOpen, setIsCodeGraphScanOpen, setViewMode } = useWorkflowStore();
  const [directories, setDirectories] = useState<string[]>([]);
  const [visibleTypes, setVisibleTypes] = useState<string[]>(['Folder', 'File', 'Class', 'Interface', 'Function', 'Documentation', 'Concept']);
  const [showClusters, setShowClusters] = useState(false);
  const [selectedDir, setSelectedDir] = useState("/");
  const [scanName, setScanName] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const cameraControlsRef = useRef<any>(null);

  const flyToNode = (pos: [number, number, number]) => {
    if (cameraControlsRef.current) {
      cameraControlsRef.current.setLookAt(
        pos[0], pos[1] + 10, pos[2] + 20, // Camera pos
        pos[0], pos[1], pos[2],           // Target pos
        true                              // Transition
      );
    }
  };
  
  const handleRecenter = () => {
    if (cameraControlsRef.current) {
        cameraControlsRef.current.setLookAt(0, 40, 80, 0, 0, 0, true);
        setFocusPath(null);
        setSelectedNodeId(null);
    }
  };

  const fetchDirs = async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/api/graph/dirs?workspace=${currentWorkspace}`, {
         headers: { ...GOVERNANCE_HEADERS }
      });
      if (resp.ok) {
        const data = await resp.json();
        setDirectories(data.directories || ["/"]);
      }
    } catch (e) {
      console.error("Failed to fetch dirs", e);
    }
  };

  const fetchGraph = async () => {
    try {
      // Only fetch if a code snapshot is selected OR we are in default mode
      const snapshotParam = activeGraphId && activeGraphId !== 'neural_nexus' ? `&snapshot_id=${activeGraphId}` : '';
      const pathParam = focusPath ? `&path=${focusPath}` : '';
      
      const resp = await fetch(`${API_BASE_URL}/api/graph/code?workspace=${currentWorkspace}${snapshotParam}${pathParam}`, {
         headers: { ...GOVERNANCE_HEADERS }
      });
      if (resp.ok) {
        const data = await resp.json();
        if (data.nodes) {
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
        body: JSON.stringify({ 
          workspace: currentWorkspace, 
          root_dir: selectedDir === "/" ? "" : selectedDir,
          name: scanName || undefined
        })
      });
      if (resp.ok) {
        setTimeout(() => {
          fetchGraph();
          setIsGenerating(false);
          setIsCodeGraphScanOpen(false);
          setScanName("");
        }, 3000);
      }
    } catch (e) {
      console.error("Failed to generate", e);
      setIsGenerating(false);
    }
  };

  // Layout logic
  const processedGraph = useMemo(() => {
    if (!codeGraph) return { nodes: [], edges: [] };
    
    const filteredSourceNodes = codeGraph.nodes.filter((n: any) => visibleTypes.includes(n.type));

    const nodes = filteredSourceNodes.map((node: any, i: number) => {
       const isSymbol = !['Folder', 'File'].includes(node.type);
       const parts = (node.path || "").split('/');
       const depth = parts.length;
       const nodeCount = filteredSourceNodes.length || 1;
       const baseAngle = (i / nodeCount) * Math.PI * 2;
       const baseRadius = depth * 6 + 10;
       
       let position: [number, number, number];
       
       if (isSymbol) {
         const hash = node.name.split('').reduce((a: number, b: string) => a + b.charCodeAt(0), 0);
         const offsetAngle = (hash % 100) / 100 * Math.PI * 2;
         const offsetRadius = 2 + (hash % 8) * 0.3;
         position = [
            Math.cos(baseAngle) * baseRadius + Math.cos(offsetAngle) * offsetRadius,
            (Math.random() - 0.5) * 6,
            Math.sin(baseAngle) * baseRadius + Math.sin(offsetAngle) * offsetRadius
         ];
       } else {
         position = [
            Math.cos(baseAngle) * baseRadius,
            (Math.random() - 0.5) * 4,
            Math.sin(baseAngle) * baseRadius
         ];
       }
       
       return {
         ...node,
         position
       };
    });

    const edges = codeGraph.edges.filter((e: any) => {
       return nodes.find(n => n.id === e.source) && nodes.find(n => n.id === e.target);
    }).map((edge: any) => {
       const sourceNode = nodes.find(n => n.id === edge.source);
       const targetNode = nodes.find(n => n.id === edge.target);
       return {
         ...edge,
         sourcePos: sourceNode?.position || [0,0,0],
         targetPos: targetNode?.position || [0,0,0]
       };
    });

    return { nodes, edges };
  }, [codeGraph, visibleTypes]);

  const selectedNode = useMemo(() => 
    processedGraph.nodes.find((n: any) => n.id === selectedNodeId), 
    [processedGraph.nodes, selectedNodeId]
  );

  const selectedEdge = useMemo(() => 
    processedGraph.edges.find((e: any) => `${e.source}-${e.target}` === selectedEdgeId),
    [processedGraph.edges, selectedEdgeId]
  );

  useEffect(() => {
    fetchDirs();
    fetchGraph();
    // Reset camera on root
    if (!focusPath && cameraControlsRef.current) {
        cameraControlsRef.current.setLookAt(0, 20, 40, 0, 0, 0, true);
    }
  }, [currentWorkspace, activeGraphId, focusPath]);


  return (
    <div className="absolute inset-0 bg-[#020408]" onClick={() => { setSelectedNodeId(null); setSelectedEdgeId(null); }}>
      
      {/* Breadcrumbs */}
      <div className="absolute top-24 left-12 z-10 flex items-center gap-2 bg-black/40 backdrop-blur-md border border-white/10 px-4 py-2 rounded-full">
        <button 
          onClick={() => setFocusPath(null)}
          className={`p-1.5 rounded-full hover:bg-white/10 transition-all ${!focusPath ? 'text-[#00FFFF]' : 'text-white/40'}`}
        >
          <Home size={14} />
        </button>
        {focusPath && focusPath.split('/').filter(Boolean).map((part, i, arr) => (
          <React.Fragment key={i}>
            <ChevronRight size={12} className="text-white/20" />
            <button 
              onClick={() => setFocusPath(arr.slice(0, i + 1).join('/'))}
              className={`text-[10px] font-mono uppercase tracking-widest px-2 py-1 rounded hover:bg-white/5 transition-all ${i === arr.length - 1 ? 'text-[#00FFFF] font-black' : 'text-white/60'}`}
            >
              {part}
            </button>
          </React.Fragment>
        ))}
      </div>
      
      {/* 3D Canvas */}
      <div className="flex-1 w-full h-[calc(100vh-100px)] relative overflow-hidden">
        <KeyboardControls map={KEY_MAP}>
          <Canvas 
            camera={{ position: [0, 40, 80], fov: 60 }}
            onCreated={({ raycaster }) => { raycaster.params.Line.threshold = 0.5; }}
          >
            <CodeGraphScene 
              processedGraph={processedGraph}
              selectedNodeId={selectedNodeId}
              selectedEdgeId={selectedEdgeId}
              onNodeClick={(node: any) => {
                setSelectedNodeId(node.id);
                if (node.type === 'Folder') {
                   setFocusPath(node.id);
                   flyToNode(node.position);
                } else {
                   flyToNode(node.position);
                }
              }}
              onEdgeClick={(edge: any) => {
                setSelectedEdgeId(`${edge.source}-${edge.target}`);
                setSelectedNodeId(null);
              }}
              cameraControlsRef={cameraControlsRef}
              showClusters={showClusters}
            />
          </Canvas>
        </KeyboardControls>
      </div>


      {/* Smart Overlays */}
      <>
        {/* Smart Filter Bar */}
        <div className="absolute top-24 right-12 z-20 flex flex-col gap-4">
          <div className="bg-black/60 backdrop-blur-xl border border-white/10 p-3 rounded-2xl flex flex-col gap-2 shadow-2xl">
            <div className="text-[10px] text-white/40 uppercase font-black tracking-tighter mb-1 px-1 flex items-center gap-2">
              <Filter size={10} /> Structural Layers
            </div>
            <div className="flex flex-wrap gap-2 w-48">
              {[
                { id: 'Folder', icon: <FolderIcon size={12}/>, color: '#FFD700' },
                { id: 'File', icon: <Play size={12}/>, color: '#00FFFF' },
                { id: 'Class', icon: <Layers size={12}/>, color: '#007ACC' },
                { id: 'Documentation', icon: <Info size={12}/>, color: '#00FFFF' },
                { id: 'Concept', icon: <Zap size={12}/>, color: '#FF00FF' }
              ].map(type => (
                <button
                  key={type.id}
                  onClick={() => setVisibleTypes(prev => prev.includes(type.id) ? prev.filter(t => t !== type.id) : [...prev, type.id])}
                  className={`flex items-center gap-2 px-2 py-1.5 rounded-lg border transition-all ${visibleTypes.includes(type.id) ? 'bg-white/10 border-white/20' : 'bg-black/20 border-white/5 opacity-40 grayscale'}`}
                >
                  <div style={{ color: type.color }}>{type.icon}</div>
                  <span className="text-[10px] text-white font-mono">{type.id}</span>
                </button>
              ))}
            </div>
            
            <div className="h-[1px] bg-white/5 my-2" />
            
            <button
              onClick={() => setShowClusters(!showClusters)}
              className={`flex items-center gap-3 px-3 py-2 rounded-xl border transition-all ${showClusters ? 'bg-[#00FFFF]/10 border-[#00FFFF]/30 shadow-[0_0_15px_rgba(0,255,255,0.1)]' : 'bg-black/20 border-white/5 opacity-60'}`}
            >
              <div className={`${showClusters ? 'text-[#00FFFF]' : 'text-white/40'}`}>
                 <Share2 size={14} />
              </div>
              <div className="flex flex-col items-start leading-tight">
                 <span className="text-[10px] text-white font-bold">Leiden Clustering</span>
                 <span className="text-[8px] text-white/40">Toggle Semantic Neighborhoods</span>
              </div>
            </button>
          </div>
        </div>

        {/* Community Legend HUD - Only visible in cluster mode */}
        {showClusters && (
          <motion.div 
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="absolute bottom-12 right-12 z-10 bg-black/60 backdrop-blur-xl border border-white/10 p-6 rounded-3xl w-72 shadow-2xl"
          >
            <div className="flex items-center gap-3 mb-4">
               <div className="w-2 h-2 rounded-full bg-[#00FFFF] animate-pulse" />
               <h3 className="text-sm text-white font-black uppercase tracking-widest">Semantic Landscape</h3>
            </div>
            <p className="text-[10px] text-white/40 leading-relaxed mb-4">
               Neighborhoods identified via Neural Synthesis. Common functional patterns are grouped by color.
            </p>
            <div className="space-y-2 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
               {Array.from(new Set(processedGraph.nodes
                 .filter((n: any) => n.metadata?.community_id !== undefined)
                 .map((n: any) => JSON.stringify({id: n.metadata.community_id, name: n.metadata.community_name}))))
                 .slice(0, 10)
                 .map((json: any) => {
                   const {id, name} = JSON.parse(json);
                   return (
                     <div key={id} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5 border border-white/10">
                        <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: `hsl(${(id * 137.5) % 360}, 70%, 60%)` }} />
                        <span className="text-[10px] text-white/80 font-mono truncate">{name || `Community ${id}`}</span>
                     </div>
                   );
                 })
               }
               {processedGraph.nodes.length > 0 && (
                 <div className="flex items-center gap-2 px-3 py-1 opacity-50">
                    <span className="text-[9px] text-white/30 font-mono italic">Integrated {processedGraph.nodes.length} neural anchors</span>
                 </div>
               )}
            </div>
          </motion.div>
        )}

        {/* Modal Overlays */}
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
                 <div className="space-y-1">
                    <div className="text-[8px] text-[#00FFFF]/40 uppercase tracking-widest pl-1">Target_Directory</div>
                    <div className="flex items-center gap-3 p-3 bg-white/5 border border-white/10 rounded-sm">
                        <FolderIcon className="w-4 h-4 text-[#00FFFF]/60" />
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
                 </div>

                 <div className="space-y-1">
                    <div className="text-[8px] text-[#00FFFF]/40 uppercase tracking-widest pl-1">Snapshot_Identity</div>
                    <div className="flex items-center gap-3 p-3 bg-white/5 border border-white/10 rounded-sm">
                        <Terminal className="w-4 h-4 text-[#00FFFF]/60" />
                        <input 
                          type="text"
                          placeholder="SCAN_NAME (SNAPSHOT_0x1F)"
                          value={scanName}
                          onChange={(e) => setScanName(e.target.value)}
                          className="bg-transparent border-none outline-none text-[11px] font-mono text-white flex-1"
                        />
                    </div>
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
      </>

      {/* Floating Controls */}
      <div className="absolute top-72 right-12 flex flex-col gap-4 pointer-events-auto">
         <button 
           onClick={(e) => { e.stopPropagation(); handleRecenter(); }} 
           className="btn-pill px-6 h-12 flex items-center gap-3 bg-white/5 border border-white/20 hover:bg-white/10 shadow-[0_0_15px_rgba(255,255,255,0.05)] transition-all"
         >
            <Home size={16} className="text-white/60" /> 
            <span className="text-[11px] font-black tracking-[0.2em] text-white/60">RE_CENTER</span>
         </button>
         
         <button onClick={(e) => { e.stopPropagation(); setIsCodeGraphScanOpen(true); }} className="btn-pill px-6 h-12 flex items-center gap-3 bg-[#00FFFF]/10 border border-[#00FFFF]/40 hover:border-[#00FFFF] shadow-[0_0_15px_rgba(0,255,255,0.1)] transition-all">
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
                    <div className="w-8 h-4 rounded-full bg-[#39FF14]/20 border border-[#39FF14]/40" />
                 </div>
                 <div className="flex items-center justify-between gap-4">
                    <span className="text-[10px] text-white/40">EXECUTION</span>
                    <div className="w-8 h-4 rounded-full bg-[#FF5F1F]/20 border border-[#FF5F1F]/40" />
                 </div>
                 <div className="flex items-center justify-between gap-4">
                    <span className="text-[10px] text-white/40">DEPENDENCIES</span>
                    <div className="w-8 h-4 rounded-full bg-[#00FFFF]/20 border border-[#00FFFF]/40" />
                 </div>
              </div>
           </div>
      </div>

       {/* Selection Inspector */}
       <AnimatePresence>
          {(selectedNode || selectedEdge) && (
            <SymbolInspector 
              selection={selectedNode ? { type: 'node', data: selectedNode } : { type: 'edge', data: {
                ...selectedEdge,
                sourceName: processedGraph.nodes.find((n: any) => n.id === selectedEdge.source)?.name,
                targetName: processedGraph.nodes.find((n: any) => n.id === selectedEdge.target)?.name
              } }} 
              onClose={() => { setSelectedNodeId(null); setSelectedEdgeId(null); }}
            />
          )}
       </AnimatePresence>

    </div>
  );
}
