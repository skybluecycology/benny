import { create } from 'zustand';
import { addEdge, applyNodeChanges, applyEdgeChanges } from '@xyflow/react';
import type { Node, Edge, Connection, NodeChange, EdgeChange } from '@xyflow/react';

export interface HITLRequest {
  nodeId: string;
  nodeName: string;
  action_description: string;
  reasoning: string;
  current_state_summary: string;
  options: Array<{
    label: string;
    value: string;
    description?: string;
  }>;
}

export interface ExecutionEvent {
  type: 'node_started' | 'node_completed' | 'node_error' | 'hitl_required' | 'workflow_completed' | 'workflow_failed' | 'node_progress' | 'tool_used' | 'resource_usage';
  nodeId?: string;
  timestamp: string | number;
  data?: any;
}

export interface AERTrace {
  intent: string;
  observation: string;
  inference: string;
  plan: string;
}

interface WorkflowState {
  nodes: Node[];
  edges: Edge[];
  selectedNode: string | null;
  selectedEdge: string | null;
  executionStatus: Record<string, 'idle' | 'running' | 'success' | 'error'>;
  nodeOutputs: Record<string, any>;
  swarmExecutionId: string | null;
  
  // === NEW FIELDS ===
  executionPhase: 'idle' | 'running' | 'paused_hitl' | 'completed' | 'failed';
  currentExecutingNodeId: string | null;
  hitlPendingData: HITLRequest | null;
  executionRunId: string | null;
  nodeExecutionTimers: Record<string, number>;
  executionEvents: ExecutionEvent[];
  reasoningTraces: Record<string, AERTrace>;
  currentWorkflow: any | null;
  
  // High-level run tracking
  activeRuns: Record<string, { status: string, progress: number }>;
  runHistory: any[];
  isAuditHubOpen: boolean;
  totalTasks: number;
  completedTasks: number;
  tokenUsage: number;
  npuActive: boolean;
  nodeHasTools: Record<string, boolean>;

  // Actions
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  setSwarmExecutionId: (id: string | null) => void;
  onNodesChange: (changes: NodeChange[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: (connection: Connection) => void;
  addNode: (node: Node) => void;
  deleteNode: (nodeId: string) => void;
  deleteEdge: (edgeId: string) => void;
  deleteSelected: () => void;
  setSelectedNode: (nodeId: string | null) => void;
  setSelectedEdge: (edgeId: string | null) => void;
  updateNodeData: (nodeId: string, data: any) => void;
  setNodeStatus: (nodeId: string, status: 'idle' | 'running' | 'success' | 'error') => void;
  setNodeOutput: (nodeId: string, output: any) => void;
  clearExecution: () => void;
  getConnectedNodes: (nodeId: string) => { inputs: Node[]; outputs: Node[] };

  // === NEW ACTIONS ===
  setExecutionPhase: (phase: WorkflowState['executionPhase']) => void;
  setCurrentExecutingNodeId: (nodeId: string | null) => void;
  setHitlPendingData: (data: HITLRequest | null) => void;
  setExecutionRunId: (runId: string | null) => void;
  addExecutionEvent: (event: ExecutionEvent) => void;
  setReasoningTrace: (nodeId: string, trace: AERTrace) => void;
  startNodeTimer: (nodeId: string) => void;
  stopNodeTimer: (nodeId: string) => void;
  resetExecution: () => void;
  setCurrentWorkflow: (workflow: any | null) => void;
  setRunHistory: (history: any[]) => void;
  updateActiveRun: (runId: string, data: { status: string, progress: number }) => void;
  setAuditHubOpen: (isOpen: boolean) => void;
  toggleAuditHub: () => void;
}

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  nodes: [],
  edges: [],
  selectedNode: null,
  selectedEdge: null,
  executionStatus: {},
  nodeOutputs: {},
  swarmExecutionId: null,

  // === INITIAL VALUES ===
  executionPhase: 'idle',
  currentExecutingNodeId: null,
  hitlPendingData: null,
  executionRunId: null,
  nodeExecutionTimers: {},
  executionEvents: [],
  reasoningTraces: {},
  currentWorkflow: null,
  activeRuns: {},
  runHistory: [],
  isAuditHubOpen: false,
  totalTasks: 0,
  completedTasks: 0,
  tokenUsage: 0,
  npuActive: false,
  nodeHasTools: {},

  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  setSwarmExecutionId: (id) => set({ swarmExecutionId: id }),

  onNodesChange: (changes) => {
    set({ nodes: applyNodeChanges(changes, get().nodes) });
  },

  onEdgesChange: (changes) => {
    set({ edges: applyEdgeChanges(changes, get().edges) });
  },

  onConnect: (connection) => {
    set({ 
      edges: addEdge({ 
        ...connection, 
        animated: true,
        style: { stroke: 'var(--primary)' }
      }, get().edges) 
    });
  },

  addNode: (node) => {
    set({ nodes: [...get().nodes, node] });
  },

  deleteNode: (nodeId) => {
    const { nodes, edges, selectedNode } = get();
    // Remove node and all connected edges
    set({
      nodes: nodes.filter((n) => n.id !== nodeId),
      edges: edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
      selectedNode: selectedNode === nodeId ? null : selectedNode,
    });
  },

  deleteEdge: (edgeId) => {
    const { edges, selectedEdge } = get();
    set({
      edges: edges.filter((e) => e.id !== edgeId),
      selectedEdge: selectedEdge === edgeId ? null : selectedEdge,
    });
  },

  deleteSelected: () => {
    const { selectedNode, selectedEdge, deleteNode, deleteEdge } = get();
    if (selectedNode) {
      deleteNode(selectedNode);
    } else if (selectedEdge) {
      deleteEdge(selectedEdge);
    }
  },

  setSelectedNode: (nodeId) => {
    set({ selectedNode: nodeId, selectedEdge: null });
  },

  setSelectedEdge: (edgeId) => {
    set({ selectedEdge: edgeId, selectedNode: null });
  },

  updateNodeData: (nodeId, data) => {
    set({
      nodes: get().nodes.map((node) =>
        node.id === nodeId ? { ...node, data: { ...node.data, ...data } } : node
      ),
    });
  },

  setNodeStatus: (nodeId, status) => {
    set({
      executionStatus: { ...get().executionStatus, [nodeId]: status },
    });
  },

  setNodeOutput: (nodeId, output) => {
    set({
      nodeOutputs: { ...get().nodeOutputs, [nodeId]: output },
    });
  },

  clearExecution: () => {
    set({
      executionStatus: {},
      nodeOutputs: {},
    });
  },

  getConnectedNodes: (nodeId) => {
    const { nodes, edges } = get();
    const inputEdges = edges.filter((e) => e.target === nodeId);
    const outputEdges = edges.filter((e) => e.source === nodeId);
    
    return {
      inputs: nodes.filter((n) => inputEdges.some((e) => e.source === n.id)),
      outputs: nodes.filter((n) => outputEdges.some((e) => e.target === n.id)),
    };
  },

  // === NEW ACTION IMPLEMENTATIONS ===
  setExecutionPhase: (phase) => set({ executionPhase: phase }),

  setCurrentExecutingNodeId: (nodeId) => set({ currentExecutingNodeId: nodeId }),

  setHitlPendingData: (data) => set({ 
    hitlPendingData: data,
    executionPhase: data ? 'paused_hitl' : get().executionPhase 
  }),

  setExecutionRunId: (runId) => set({ executionRunId: runId }),

  addExecutionEvent: (event) => {
    const { nodes, executionEvents, nodeHasTools } = get();
    
    // Auto-update node status if possible
    let nodesUpdated = false;
    let nextNodes = nodes;
    let nextStatus = get().executionStatus;

    if (event.nodeId && (event.type === 'node_started' || event.type === 'node_completed' || event.type === 'node_error')) {
      const status = event.type === 'node_started' ? 'running' 
                   : event.type === 'node_completed' ? 'success' 
                   : 'error';
                   
      nextNodes = nodes.map(n => n.id === event.nodeId ? { ...n, data: { ...n.data, status } } : n);
      nextStatus = { ...get().executionStatus, [event.nodeId]: status };
      nodesUpdated = true;

      if (event.type === 'node_completed') {
        set({ completedTasks: get().completedTasks + 1 });
      }
    }

    if (event.type === 'tool_used' && event.nodeId && !nodeHasTools[event.nodeId]) {
      set({ nodeHasTools: { ...nodeHasTools, [event.nodeId]: true } });
    }

    if (event.type === 'resource_usage') {
      const tokens = event.data?.usage?.total_tokens || 0;
      set({ 
        tokenUsage: get().tokenUsage + tokens,
        npuActive: true 
      });
      // Deactivate NPU glow after 2 seconds
      setTimeout(() => set({ npuActive: false }), 2000);
    }

    if (event.type === 'node_progress' && event.data?.total_steps) {
      set({ totalTasks: event.data.total_steps });
    }

    // Optimization: Cap events to last 1000 to prevent memory bloat
    const updatedEvents = [...executionEvents, event];
    const finalEvents = updatedEvents.length > 1000 ? updatedEvents.slice(-1000) : updatedEvents;

    set({ 
      executionEvents: finalEvents,
      ...(nodesUpdated ? { nodes: nextNodes, executionStatus: nextStatus } : {})
    });
  },

  setReasoningTrace: (nodeId, trace) => set({
    reasoningTraces: { ...get().reasoningTraces, [nodeId]: trace }
  }),

  startNodeTimer: (nodeId) => set({
    nodeExecutionTimers: { ...get().nodeExecutionTimers, [nodeId]: Date.now() }
  }),

  stopNodeTimer: (nodeId) => {
    const timers = { ...get().nodeExecutionTimers };
    delete timers[nodeId];
    set({ nodeExecutionTimers: timers });
  },

  resetExecution: () => set({
    executionPhase: 'idle',
    currentExecutingNodeId: null,
    hitlPendingData: null,
    executionRunId: null,
    nodeExecutionTimers: {},
    executionEvents: [],
    reasoningTraces: {},
    executionStatus: {},
    nodeOutputs: {},
    totalTasks: 0,
    completedTasks: 0,
    tokenUsage: 0,
    npuActive: false,
    nodeHasTools: {},
  }),
  setCurrentWorkflow: (workflow) => set({ currentWorkflow: workflow }),
  setRunHistory: (history) => set({ runHistory: history }),
  updateActiveRun: (runId, data) => set({
    activeRuns: { ...get().activeRuns, [runId]: data }
  }),
  setAuditHubOpen: (isOpen) => set({ isAuditHubOpen: isOpen }),
  toggleAuditHub: () => set({ isAuditHubOpen: !get().isAuditHubOpen }),
}));

