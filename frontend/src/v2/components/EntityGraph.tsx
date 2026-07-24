import { useCallback, useMemo } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  type Node,
  type Edge,
  type NodeTypes,
  type NodeProps,
  Handle,
  Position,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';
import type { NodeData, EdgeData } from '../../types';

interface EntityGraphProps {
  nodes: Record<string, NodeData>;
  onNodeClick: (nodeName: string) => void;
}

function extractJoinKey(edgeData: EdgeData): string {
  const steps = edgeData.join_steps;
  if (!steps || steps.length === 0) return '';
  const condition = steps[0]!.condition;
  const match = condition.match(/\{[^}]+\}\.(\w+)\s*=\s*\{[^}]+\}\.(\w+)/);
  if (!match) return '';
  const col1 = match[1]!;
  const col2 = match[2]!;
  if (col1 === 'id') return col2;
  return col1;
}

const NODE_WIDTH = 180;
const NODE_HEIGHT = 60;

function EntityNode({ data }: NodeProps) {
  const d = data as { label: string; fieldCount: number; edgeCount: number; description: string };
  return (
    <>
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <div
        style={{
          padding: '12px 16px',
          borderRadius: 12,
          background: 'var(--v2-accent-subtle)',
          border: '1.5px solid var(--v2-accent)',
          minWidth: NODE_WIDTH,
          textAlign: 'left',
          cursor: 'pointer',
          transition: 'box-shadow 0.2s ease, border-color 0.2s ease',
        }}
        title={d.description}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLElement).style.boxShadow = '0 0 0 3px rgba(139, 92, 246, 0.2)';
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLElement).style.boxShadow = 'none';
        }}
      >
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4,
        }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%',
            background: 'var(--v2-accent)', flexShrink: 0,
          }} />
          <span style={{
            fontSize: 14, fontWeight: 600,
            fontFamily: 'var(--v2-font-sans)',
            color: 'var(--v2-text-primary)',
          }}>
            {d.label}
          </span>
        </div>
        <div style={{
          fontSize: 11, fontFamily: 'var(--v2-font-mono)',
          color: 'var(--v2-text-secondary)', paddingLeft: 16,
        }}>
          {d.fieldCount} fields · {d.edgeCount} edges
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </>
  );
}

const nodeTypes: NodeTypes = { entity: EntityNode };

function buildFlowGraph(
  ontologyNodes: Record<string, NodeData>
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 80, ranksep: 100, marginx: 40, marginy: 40 });

  const nodeNames = Object.keys(ontologyNodes);
  for (const name of nodeNames) {
    g.setNode(name, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }

  const edgeSet = new Set<string>();
  const flowEdges: Edge[] = [];

  for (const name of nodeNames) {
    const node = ontologyNodes[name]!;
    const edges = node.edges ?? {};
    for (const [edgeName, edgeData] of Object.entries(edges)) {
      const target = edgeData.node || edgeName;
      if (!ontologyNodes[target]) continue;
      const key = [name, target].sort().join('::');
      if (edgeSet.has(key)) continue;
      edgeSet.add(key);
      g.setEdge(name, target);
      const joinKey = extractJoinKey(edgeData);
      flowEdges.push({
        id: `${name}-${target}`,
        source: name,
        target,
        label: joinKey || edgeName,
        type: 'default',
        style: { stroke: 'var(--v2-accent)', strokeWidth: 1.5 },
        labelStyle: {
          fontSize: 11,
          fontFamily: 'var(--v2-font-mono)',
          fontWeight: 500,
          fill: 'var(--v2-accent-text)',
        },
        labelBgStyle: {
          fill: 'var(--v2-bg-elevated)',
          stroke: 'var(--v2-border)',
          strokeWidth: 1,
          rx: 6,
          ry: 6,
        },
        labelBgPadding: [6, 4] as [number, number],
        markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--v2-accent)', width: 16, height: 12 },
      });
    }
  }

  dagre.layout(g);

  const flowNodes: Node[] = [];
  for (const name of nodeNames) {
    const pos = g.node(name);
    const node = ontologyNodes[name]!;
    flowNodes.push({
      id: name,
      type: 'entity',
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      data: {
        label: name,
        fieldCount: Object.keys(node.fields ?? {}).length,
        edgeCount: Object.keys(node.edges ?? {}).length,
        description: node.description || '',
      },
    });
  }

  return { nodes: flowNodes, edges: flowEdges };
}

export default function EntityGraph({ nodes: ontologyNodes, onNodeClick }: EntityGraphProps) {
  const { nodes, edges } = useMemo(
    () => buildFlowGraph(ontologyNodes),
    [ontologyNodes]
  );

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => { onNodeClick(node.id); },
    [onNodeClick]
  );

  const nodeCount = Object.keys(ontologyNodes).length;
  const containerHeight = Math.min(700, Math.max(500, nodeCount * 60));

  if (nodeCount === 0) {
    return (
      <div style={{
        padding: 48, textAlign: 'center', borderRadius: 'var(--v2-radius-lg)',
        border: '1px dashed var(--v2-border)', background: 'var(--v2-bg-surface)',
      }}>
        <p className="v2-heading-sm" style={{ marginBottom: 4 }}>No nodes yet</p>
        <p className="v2-caption">Add a schema by connecting a database and generating an ontology.</p>
      </div>
    );
  }

  return (
    <div style={{
      width: '100%', height: containerHeight, borderRadius: 'var(--v2-radius-lg)',
      border: '1px solid var(--v2-border)', overflow: 'hidden',
      background: 'var(--v2-bg-surface)',
    }}>
      <ReactFlowProvider>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={handleNodeClick}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          proOptions={{ hideAttribution: true }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          minZoom={0.2}
          maxZoom={2}
        >
          <Background gap={20} size={1} color="var(--v2-border)" />
          <Controls
            showInteractive={false}
            style={{ background: 'var(--v2-bg-elevated)', border: '1px solid var(--v2-border)', borderRadius: 8 }}
          />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  );
}
