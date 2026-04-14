import { useRef, useMemo } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Stars, Text, Sphere, Line, Trail } from '@react-three/drei';
import * as THREE from 'three';
import { useWorkflowStore } from '../../hooks/useWorkflowStore';

// --- Sub-Agent Node ---
function SubAgent({ position, color, speed, offset, label, status, isSelected, onClick }: { position: [number, number, number], color: string, speed: number, offset: number, label: string, status?: string, isSelected?: boolean, onClick?: () => void }) {
  const ref = useRef<THREE.Mesh>(null);
  const glowRef = useRef<THREE.Mesh>(null);
  const textRef = useRef<any>(null);
  
  useFrame((state) => {
    if (ref.current) {
      const t = state.clock.elapsedTime * (isSelected ? 0.2 : speed) + offset;
      const radius = isSelected ? 4 : 1.2;
      ref.current.position.x = position[0] + Math.cos(t) * radius;
      ref.current.position.y = position[1] + Math.sin(t * 0.8) * radius;
      ref.current.position.z = position[2] + Math.sin(t) * radius;
      
      if (glowRef.current) {
        glowRef.current.position.copy(ref.current.position);
        glowRef.current.scale.setScalar((isSelected ? 2.5 : 1.2) + Math.sin(state.clock.elapsedTime * 4) * 0.2);
      }
      if (textRef.current) {
        textRef.current.position.set(ref.current.position.x, ref.current.position.y - 0.5, ref.current.position.z);
        textRef.current.lookAt(state.camera.position);
      }
    }
  });

  return (
    <>
      <Trail width={isSelected ? 0.8 : 0.4} length={isSelected ? 10 : 5} color={new THREE.Color(color)} attenuation={(t) => t * t}>
        <Sphere ref={ref} args={[isSelected ? 0.3 : 0.18, 16, 16]} position={position} onClick={(e) => { e.stopPropagation(); onClick?.(); }}>
          <meshBasicMaterial color={isSelected ? '#ffffff' : color} toneMapped={false} />
        </Sphere>
      </Trail>
      {(status === 'running' || isSelected) && (
        <Sphere ref={glowRef} args={[0.25, 16, 16]}>
          <meshBasicMaterial color={color} transparent opacity={isSelected ? 0.5 : 0.3} toneMapped={false} />
        </Sphere>
      )}
      <Text 
        ref={textRef}
        fontSize={isSelected ? 0.3 : 0.15} 
        color={isSelected ? '#00FFFF' : '#ffffff'} 
        maxWidth={2}
        textAlign="center"
      >
        {label}
      </Text>
    </>
  );
}

// --- Swarm Cluster ---
function SwarmCluster({ position, name, color, nodes, onNodeClick }: { position: [number, number, number], name: string, color: string, nodes: any[], onNodeClick: (id: string) => void }) {
  const groupRef = useRef<THREE.Group>(null);
  
  const nodeLayouts = useMemo(() => {
    return nodes.map((node, i) => ({
      id: node.id,
      label: node.id.split('.').pop() || node.id,
      status: node.status,
      isSelected: node.isSelected,
      pos: [
        (Math.random() - 0.5) * 6,
        (Math.random() - 0.5) * 6,
        (Math.random() - 0.5) * 6
      ] as [number, number, number],
      speed: 0.3 + Math.random() * 0.4,
      offset: nodes.length > 0 ? (i / nodes.length) * Math.PI * 2 : 0
    }));
  }, [nodes]);


  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y = state.clock.elapsedTime * 0.05;
    }
  });

  return (
    <group position={position} ref={groupRef}>
      {/* Central Hub Core */}
      <Sphere args={[0.5, 32, 32]}>
        <meshBasicMaterial color={color} transparent opacity={0.6} toneMapped={false} />
      </Sphere>
      <Sphere args={[0.8, 16, 16]}>
        <meshBasicMaterial color={color} wireframe transparent opacity={0.1} toneMapped={false} />
      </Sphere>
      
      <Text position={[0, 4, 0]} fontSize={0.6} color={color}>
        {name}
      </Text>


      {/* Actual Agent Nodes */}
      {nodeLayouts.map((node) => (
        <group key={node.id}>
          <SubAgent 
            position={node.pos} 
            color={node.status === 'running' ? '#ffffff' : color} 
            speed={node.speed} 
            offset={node.offset} 
            label={node.label}
            status={node.status}
            isSelected={node.isSelected}
            onClick={() => onNodeClick(node.id)}
          />
          <Line 
            points={[[0,0,0], node.pos]} 
            color={color} 
            transparent 
            opacity={node.isSelected ? 0.5 : 0.1} 
          />
        </group>
      ))}
    </group>
  );
}

export function SwarmCanvas3D() {
  const activeRuns = 4; // Placeholder
  const { nodes, executionStatus, selectedNode, setSelectedNode, playbackIndex, executionEvents } = useWorkflowStore();

  // Temporal State Reconstruction: Replay events up to the scrubber position
  const displayStatus = useMemo(() => {
    if (playbackIndex === null) return executionStatus;
    
    const status: Record<string, any> = {};
    executionEvents.slice(0, playbackIndex + 1).forEach(event => {
      if (event.nodeId && (event.type === 'node_started' || event.type === 'node_completed' || event.type === 'node_error')) {
        status[event.nodeId] = event.type === 'node_started' ? 'running' 
                             : event.type === 'node_completed' ? 'success' : 'error';
      }
    });
    return status;
  }, [executionStatus, playbackIndex, executionEvents]);

  const isTemporalMode = playbackIndex !== null;


  // Categorize nodes into functional clusters for 3D layout
  const clusters = useMemo(() => {
    const intake = nodes.filter(n => n.id.toLowerCase().includes('planner') || n.id.toLowerCase().includes('source') || n.id.toLowerCase().includes('input'));
    const orchestrator = nodes.filter(n => n.id.toLowerCase().includes('scheduler') || n.id.toLowerCase().includes('orchestrator') || n.id.toLowerCase().includes('dispatcher') || n.id.toLowerCase().includes('manager'));
    const synthesis = nodes.filter(n => n.id.toLowerCase().includes('executor') || n.id.toLowerCase().includes('writer') || n.id.toLowerCase().includes('generator') || n.id.toLowerCase().includes('agent'));
    const verifier = nodes.filter(n => n.id.toLowerCase().includes('monitor') || n.id.toLowerCase().includes('reviewer') || n.id.toLowerCase().includes('aggregator') || n.id.toLowerCase().includes('evaluator'));

    // FALLBACK: Put anything else here
    const classifiedIds = new Set([...intake, ...orchestrator, ...synthesis, ...verifier].map(n => n.id));
    const unclassified = nodes.filter(n => !classifiedIds.has(n.id));

    return [
      { id: 'intake', name: 'INTAKE_SWARM', color: '#00FFFF', pos: [-12, 4, -8], nodes: intake },
      { id: 'orchestrator', name: 'ORCHESTRATOR_CORE', color: '#39FF14', pos: [0, 0, 0], nodes: orchestrator },
      { id: 'synthesis', name: 'SYNTHESIS_SWARM', color: '#c084fc', pos: [12, -4, -4], nodes: synthesis },
      { id: 'verifier', name: 'VERIFIER_SWARM', color: '#FF5F1F', pos: [0, 8, -15], nodes: verifier },
      { id: 'unclassified', name: 'X_NEURAL_NODES', color: '#ffffff', pos: [0, -10, -5], nodes: unclassified }
    ];
  }, [nodes]);


  return (
    <div className={`absolute inset-0 bg-[#020408] transition-all duration-700 ${isTemporalMode ? 'sepia-[0.3] brightness-[0.8]' : ''}`}>
      {isTemporalMode && (
        <div className="absolute inset-0 pointer-events-none z-50 border-[20px] border-amber-500/10 animate-pulse shadow-[inset_0_0_150px_rgba(245,158,11,0.15)]" />
      )}
      <Canvas camera={{ position: [0, 10, 30], fov: 60 }}>

        <color attach="background" args={['#020408']} />
        <ambientLight intensity={0.4} />
        <pointLight position={[10, 10, 10]} intensity={1} color="#00FFFF" />
        <Stars radius={100} depth={50} count={10000} factor={4} saturation={1} fade speed={1.5} />
        
        {/* Swarm Clusters */}
        {clusters.map(cluster => (
          <SwarmCluster 
            key={cluster.id}
            position={cluster.pos as [number, number, number]} 
            name={cluster.name} 
            color={cluster.color}
            nodes={cluster.nodes.map(n => ({
                id: n.id,
                status: displayStatus[n.id] || 'idle',
                isSelected: selectedNode === n.id
            }))}

            onNodeClick={(id) => setSelectedNode(id)}
          />
        ))}


        {/* Global Connection Filaments (Inter-Cluster) */}
        <Line points={[[-12, 4, -8], [0, 0, 0]]} color="#00FFFF" transparent opacity={0.2} dashed dashScale={5} />
        <Line points={[[0, 0, 0], [12, -4, -4]]} color="#39FF14" transparent opacity={0.2} dashed dashScale={5} />
        <Line points={[[12, -4, -4], [0, 8, -15]]} color="#c084fc" transparent opacity={0.2} dashed dashScale={5} />

        <OrbitControls 
          enablePan={true} 
          enableZoom={true} 
          enableRotate={true}
          autoRotate={nodes.length === 0}
          autoRotateSpeed={0.1}
          maxDistance={60}
          minDistance={5}
        />
      </Canvas>
    </div>
  );
}
