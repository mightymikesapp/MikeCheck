import { useCallback } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  Edge,
  Node,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

const initialNodes: Node[] = [
  { 
    id: '1', 
    position: { x: 250, y: 0 }, 
    data: { label: 'Roe v. Wade (1973)' },
    style: { background: '#ef4444', color: 'white', border: 'none', borderRadius: '8px', padding: '10px', fontWeight: 'bold' }
  },
  { 
    id: '2', 
    position: { x: 100, y: 150 }, 
    data: { label: 'Planned Parenthood v. Casey (1992)' },
    style: { background: '#f97316', color: 'white', border: 'none', borderRadius: '8px', padding: '10px' }
  },
  { 
    id: '3', 
    position: { x: 400, y: 150 }, 
    data: { label: 'Dobbs v. Jackson (2022)' },
    style: { background: '#10b981', color: 'white', border: 'none', borderRadius: '8px', padding: '10px', fontWeight: 'bold' }
  },
  { 
    id: '4', 
    position: { x: 250, y: 300 }, 
    data: { label: 'Griswold v. Connecticut (1965)' },
    style: { background: '#3b82f6', color: 'white', border: 'none', borderRadius: '8px', padding: '10px' }
  },
];

const initialEdges: Edge[] = [
  { id: 'e1-2', source: '1', target: '2', animated: true, label: 'Affirmed in part', style: { stroke: '#f97316' } },
  { id: 'e1-3', source: '1', target: '3', animated: true, label: 'Overruled', style: { stroke: '#ef4444', strokeWidth: 2 }, markerEnd: { type: MarkerType.ArrowClosed, color: '#ef4444' } },
  { id: 'e4-1', source: '4', target: '1', label: 'Cited', style: { stroke: '#94a3b8' } },
];

export default function CitationGraph() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges],
  );

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        fitView
        attributionPosition="bottom-right"
      >
        <Controls />
        <MiniMap />
        <Background gap={12} size={1} />
      </ReactFlow>
    </div>
  );
}
