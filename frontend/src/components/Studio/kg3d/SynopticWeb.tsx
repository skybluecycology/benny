import React, { useEffect, useRef, useState, useMemo } from 'react';
import ForceGraph3D, { ForceGraphMethods } from 'react-force-graph-3d';
import { CATEGORY_COLORS, EDGE_COLORS } from './palette';
import InstancedNodes from './InstancedNodes';
import { useKg3dStore, type KgNode, type KgEdge, type DeltaEvent } from '../../../hooks/useKg3dStore';
import { API_BASE_URL, GOVERNANCE_HEADERS } from '../../../constants';
import * as THREE from 'three';

interface SynopticWebProps {
  enabled: boolean;
  focusedLayer?: number;
}

const SynopticWeb: React.FC<SynopticWebProps> = ({ enabled, focusedLayer = null }) => {
  const fgRef = useRef<ForceGraphMethods>();
  const { selectConcept, setGraph } = useKg3dStore();
  const [data, setData] = useState<{ nodes: any[]; links: any[] }>({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(true);

  // Fetch initial ontology
  useEffect(() => {
    if (!enabled) return;

    const fetchOntology = async () => {
      const startTime = performance.now();
      try {
        const res = await fetch(`${API_BASE_URL}/api/kg3d/ontology`, {
          headers: { ...GOVERNANCE_HEADERS }
        });
        if (res.ok) {
          const raw = await res.json();
          setData({
            nodes: raw.nodes.map((n: KgNode) => ({ ...n })),
            links: raw.edges.map((e: KgEdge) => ({ ...e, source: e.source_id, target: e.target_id }))
          });
          setGraph(raw.nodes, raw.edges);
          const duration = performance.now() - startTime;
          console.log(`[KG3D_TELEMETRY] Ontology loaded in ${duration.toFixed(2)}ms. Nodes: ${raw.nodes.length}`);
        }
      } catch (e) {
        console.error("Failed to load ontology:", e);
      } finally {
        setLoading(false);
      }
    };

    fetchOntology();
  }, [enabled]);

  // SSE Stream for updates
  useEffect(() => {
    if (!enabled) return;

    const eventSource = new EventSource(`${API_BASE_URL}/api/kg3d/stream`);
    
    eventSource.onmessage = (event) => {
      const delta: DeltaEvent = JSON.parse(event.data);
      if (delta.kind === 'upsert_node' && delta.payload) {
        setData(prev => ({
          ...prev,
          nodes: [...prev.nodes.filter(n => n.id !== delta.payload.id), delta.payload]
        }));
      } else if (delta.kind === 'upsert_edge' && delta.payload) {
          setData(prev => ({
            ...prev,
            links: [...prev.links.filter(l => l.id !== delta.payload.id), {
                ...delta.payload,
                source: delta.payload.source_id,
                target: delta.payload.target_id
            }]
          }));
      }
    };

    return () => eventSource.close();
  }, [enabled]);

  // AoT Layer Filtering (Fading)
  const processedData = useMemo(() => {
    if (focusedLayer === null) return data;
    
    return {
      nodes: data.nodes.map(n => ({
        ...n,
        __opacity: n.aot_layer === focusedLayer ? 1.0 : 0.1
      })),
      links: data.links.map(l => ({
        ...l,
        __opacity: 0.2 // Simplified fading for links
      }))
    };
  }, [data, focusedLayer]);

  if (!enabled) return null;

  return (
    <div className="synoptic-web-container" style={{ width: '100%', height: '100%', background: '#020408' }}>
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center text-[#39FF14] font-mono text-sm">
          SYNOPTIC_WEB_LOADING...
        </div>
      )}
      <ForceGraph3D
        ref={fgRef}
        graphData={processedData}
        backgroundColor="#020408"
        nodeLabel="display_name"
        nodeColor={(n: any) => CATEGORY_COLORS[n.category] || CATEGORY_COLORS.default}
        nodeRelSize={6}
        nodeVal={(n: any) => n.metrics.pagerank * 100 + 1}
        nodeOpacity={1}
        nodeThreeObject={(n: any) => {
            // Optimization: If using customLayer, we return null here
            return data.nodes.length > 500 ? new THREE.Object3D() : undefined;
        }}
        customLayerOrder={['node', 'link', 'custom']}
        customLayerData={[data.nodes]}
        customLayerElement={(nodes: any[]) => {
            if (nodes[0].length <= 500) return null;
            return <InstancedNodes nodes={nodes[0]} quality="low" />;
        }}
        linkColor={(l: any) => EDGE_COLORS[l.kind] || EDGE_COLORS.references}
        linkWidth={1.5}
        linkDirectionalParticles={2}
        linkDirectionalParticleSpeed={0.01}
        showNavInfo={false}
        onNodeClick={(node: any) => {
          selectConcept(node.id);
          console.log("Focused concept:", node.canonical_name);
        }}
      />
    </div>
  );
};

export { SynopticWeb };
export default SynopticWeb;
