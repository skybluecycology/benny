import { useCallback, useMemo, useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  BackgroundVariant,
  useReactFlow,
} from '@xyflow/react';
import type { NodeTypes, Edge } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useWorkflowStore } from '../../hooks/useWorkflowStore';
import TriggerNode from './nodes/TriggerNode';
import LLMNode from './nodes/LLMNode';
import ToolNode from './nodes/ToolNode';
import LogicNode from './nodes/LogicNode';
import DataNode from './nodes/DataNode';

export default function WorkflowCanvas() {
  const { screenToFlowPosition } = useReactFlow();
  const nodes = useWorkflowStore((state) => state.nodes);
  const edges = useWorkflowStore((state) => state.edges);
  const onNodesChange = useWorkflowStore((state) => state.onNodesChange);
  const onEdgesChange = useWorkflowStore((state) => state.onEdgesChange);
  const onConnect = useWorkflowStore((state) => state.onConnect);
  const addNode = useWorkflowStore((state) => state.addNode);
  const setSelectedNode = useWorkflowStore((state) => state.setSelectedNode);
  const setSelectedEdge = useWorkflowStore((state) => state.setSelectedEdge);
  const deleteSelected = useWorkflowStore((state) => state.deleteSelected);
  const selectedNode = useWorkflowStore((state) => state.selectedNode);
  const selectedEdge = useWorkflowStore((state) => state.selectedEdge);

  const nodeTypes: NodeTypes = useMemo(() => ({
    trigger: TriggerNode,
    llm: LLMNode,
    tool: ToolNode,
    logic: LogicNode,
    data: DataNode,
  }), []);

  // Keyboard delete handler
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Delete' || event.key === 'Backspace') {
        // Don't delete if user is typing in an input
        const target = event.target as HTMLElement;
        if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
          return;
        }
        if (selectedNode || selectedEdge) {
          event.preventDefault();
          deleteSelected();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [selectedNode, selectedEdge, deleteSelected]);

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();

      const type = event.dataTransfer.getData('application/reactflow/type');
      const label = event.dataTransfer.getData('application/reactflow/label');

      if (!type) return;

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const newNode = {
        id: `${type}-${Date.now()}`,
        type,
        position,
        data: { label, config: {} },
      };

      addNode(newNode);
    },
    [screenToFlowPosition, addNode]
  );

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: { id: string }) => {
      setSelectedNode(node.id);
    },
    [setSelectedNode]
  );

  const onEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      setSelectedEdge(edge.id);
    },
    [setSelectedEdge]
  );

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
  }, [setSelectedNode, setSelectedEdge]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges.map(e => ({
        ...e,
        selected: e.id === selectedEdge,
        style: {
          ...e.style,
          stroke: e.id === selectedEdge ? '#ef4444' : 'var(--primary)',
          strokeWidth: e.id === selectedEdge ? 3 : 2,
        }
      }))}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onNodeClick={onNodeClick}
      onEdgeClick={onEdgeClick}
      onPaneClick={onPaneClick}
      nodeTypes={nodeTypes}
      fitView
      snapToGrid
      snapGrid={[20, 20]}
      deleteKeyCode={null} // We handle delete ourselves
      selectionOnDrag
      panOnDrag={[1, 2]} // Pan with middle/right mouse
    >
      <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="rgba(255,255,255,0.05)" />
      <Controls />
      <MiniMap 
        nodeColor={(node) => {
          switch (node.type) {
            case 'trigger': return '#4ade80';
            case 'llm': return '#a78bfa';
            case 'tool': return '#60a5fa';
            case 'logic': return '#fb923c';
            case 'data': return '#2dd4bf';
            default: return '#888';
          }
        }}
        maskColor="rgba(0,0,0,0.8)"
      />
    </ReactFlow>
  );
}
