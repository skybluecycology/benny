import { useRef, useMemo } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Stars, Text, Sphere, Line } from '@react-three/drei';
import * as THREE from 'three';
import { useWorkspaceStore } from '../../hooks/useWorkspaceStore';

// --- Synoptic Memory Node ---
function SynopticNode({ position, label, color, importance }: { position: [number, number, number], label: string, color: string, importance: number }) {
  const ref = useRef<THREE.Mesh>(null);
  const size = 0.2 + importance * 0.4;

  useFrame((state) => {
    if (ref.current) {
      ref.current.position.y = position[1] + Math.sin(state.clock.elapsedTime * 2 + position[0]) * 0.1;
      ref.current.rotation.y += 0.01;
    }
  });

  return (
    <group position={position}>
      <Sphere ref={ref} args={[size, 16, 16]}>
        <meshBasicMaterial color={color} transparent opacity={0.8} toneMapped={false} />
      </Sphere>
      <Sphere args={[size * 1.5, 8, 8]}>
        <meshBasicMaterial color={color} wireframe transparent opacity={0.1} toneMapped={false} />
      </Sphere>
      <Text 
        position={[0, size + 0.4, 0]} 
        fontSize={0.2} 
        color={color} 
        anchorX="center" 
        anchorY="middle"
      >
        {label}
      </Text>
    </group>
  );
}

export function SynopticWeb() {
  const { currentWorkspace } = useWorkspaceStore();
  
  // Mock data for the "God-Mode" Knowledge Web
  const concepts = useMemo(() => [
    { id: 1, label: 'Cognitive Mesh', pos: [0, 0, 0], color: '#00FFFF', importance: 1.0 },
    { id: 2, label: 'Swarm Intelligence', pos: [-5, 3, -4], color: '#39FF14', importance: 0.8 },
    { id: 3, label: 'Neural Provisioning', pos: [5, -2, -6], color: '#c084fc', importance: 0.7 },
    { id: 4, label: 'Vector Context', pos: [-2, -4, 5], color: '#FF5F1F', importance: 0.6 },
    { id: 5, label: 'Audit Lineage', pos: [6, 4, 2], color: '#00FFFF', importance: 0.5 },
  ], []);

  return (
    <div className="absolute inset-0 bg-[#020408]">
      <Canvas camera={{ position: [0, 5, 20], fov: 60 }}>
        <color attach="background" args={['#020408']} />
        <ambientLight intensity={0.4} />
        <Stars radius={100} depth={50} count={5000} factor={4} saturation={1} fade speed={0.5} />
        
        <group>
          {concepts.map(concept => (
            <SynopticNode 
              key={concept.id}
              position={concept.pos as [number, number, number]}
              label={concept.label}
              color={concept.color}
              importance={concept.importance}
            />
          ))}

          {/* Connection Lines */}
          <Line points={[[0, 0, 0], [-5, 3, -4]]} color="#00FFFF" transparent opacity={0.2} />
          <Line points={[[0, 0, 0], [5, -2, -6]]} color="#00FFFF" transparent opacity={0.2} />
          <Line points={[[-5, 3, -4], [-2, -4, 5]]} color="#39FF14" transparent opacity={0.1} />
          <Line points={[[5, -2, -6], [6, 4, 2]]} color="#c084fc" transparent opacity={0.1} />
        </group>

        <OrbitControls autoRotate autoRotateSpeed={0.5} />
      </Canvas>

      <div className="absolute top-10 left-10 pointer-events-none">
        <h1 className="glow-text-cyan text-[24px] font-bold tracking-widest uppercase">Synoptic_Web</h1>
        <div className="text-[10px] text-white/40 font-mono tracking-widest mt-2">ACTIVE_WORKSPACE: {currentWorkspace?.toUpperCase() || 'DEFAULT'}</div>
      </div>
    </div>
  );
}
