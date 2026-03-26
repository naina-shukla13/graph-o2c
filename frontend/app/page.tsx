

"use client";

import React, { useCallback, useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import axios from 'axios';
import { useNodesState, useEdgesState } from 'reactflow';
import type { Node, Edge } from 'reactflow';
import 'reactflow/dist/style.css';

import ReactFlow, { Background, Controls, MiniMap, ReactFlowProvider } from 'reactflow';

const BACKEND = 'http://127.0.0.1:8000';

const colorByType: Record<string, string> = {
  Customer: '#10b981',
  SalesOrder: '#6366f1',
  Delivery: '#f59e0b',
  BillingDocument: '#ef4444',
  Product: '#8b5cf6',
  Plant: '#14b8a6',
  Payment: '#ec4899',
};

const legendColors: Record<string, string> = {
  Customer: 'bg-emerald-500',
  SalesOrder: 'bg-indigo-500',
  Delivery: 'bg-amber-500',
  BillingDocument: 'bg-red-500',
  Product: 'bg-purple-500',
  Plant: 'bg-teal-500',
  Payment: 'bg-pink-500',
};

type ApiNode = { id: string; type: string; label: string; properties: Record<string, unknown> };
type ApiEdge = { source: string; target: string; label: string };

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sql?: string;
}

// Memoized empty objects for React Flow (IMPORTANT)
const nodeTypes = {};
const edgeTypes = {};

function GraphInner() {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [graphLoading, setGraphLoading] = useState(true);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [question, setQuestion] = useState('');
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [history, setHistory] = useState<{ q: string; a: string }[]>([]);

  const highlightTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Memoize these to prevent React Flow warnings

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load initial graph
  useEffect(() => {
    axios.get(`${BACKEND}/graph`)
      .then(res => {
        setNodes((res.data.nodes || []).map(toRfNode));
        setEdges((res.data.edges || []).map(toRfEdge));
        setGraphLoading(false);
      })
      .catch(e => {
        setGraphError('Cannot reach backend. Make sure Python backend is running on port 8000.');
        setGraphLoading(false);
        console.error(e);
      });
  }, []);

  const applyHighlight = useCallback((ids: string[]) => {
    if (highlightTimeout.current) clearTimeout(highlightTimeout.current);
    setNodes(prev => prev.map(n => ({
      ...n,
      style: { 
        ...n.style, 
        border: ids.includes(n.id) ? '3px solid #facc15' : '1px solid rgba(255,255,255,0.15)' 
      },
    })));
    highlightTimeout.current = setTimeout(() => {
      setNodes(prev => prev.map(n => ({
        ...n,
        style: { ...n.style, border: '1px solid rgba(255,255,255,0.15)' },
      })));
    }, 4000);
  }, [setNodes]);

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNode(node);
    axios.get(`${BACKEND}/expand/${encodeURIComponent(node.id)}`)
      .then(res => {
        const newNodes: ApiNode[] = res.data.nodes || [];
        const newEdges: ApiEdge[] = res.data.edges || [];
        setNodes(prev => {
          const ids = new Set(prev.map(n => n.id));
          return [...prev, ...newNodes.filter(n => !ids.has(n.id)).map((n, i) => toRfNode(n, prev.length + i))];
        });
        setEdges(prev => {
          const ids = new Set(prev.map(e => e.id));
          return [...prev, ...newEdges.map(toRfEdge).filter(e => !ids.has(e.id))];
        });
      }).catch(console.error);
  }, [setNodes, setEdges]);

  const sendQuestion = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) return;
    setMessages(prev => [...prev, { role: 'user', content: trimmed }]);
    setQuestion('');
    setLoading(true);
    try {
      const res = await axios.post(`${BACKEND}/query`, { question: trimmed, history: history.slice(-3) });
      const d = res.data;
      setMessages(prev => [...prev, { role: 'assistant', content: d.answer || 'No answer.', sql: d.sql }]);
      setHistory(prev => [...prev, { q: trimmed, a: d.answer || '' }]);
      if (d.nodes_to_highlight?.length) applyHighlight(d.nodes_to_highlight);
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${String(e)}` }]);
    } finally {
      setLoading(false);
    }
  }, [history, applyHighlight]);

  return (
    <div className="flex h-screen w-full bg-slate-900 text-white overflow-hidden">
      {/* LEFT: Graph */}
      <div className="w-[62%] flex flex-col border-r border-slate-700">
        <div className="bg-slate-800 border-b border-slate-700 px-4 py-3 shrink-0">
          <div className="flex items-center justify-between mb-2">
            <h1 className="text-xl font-bold">Supply Chain Explorer</h1>
            <span className="text-xs text-slate-400">{nodes.length} nodes · {edges.length} edges</span>
          </div>
          <div className="flex gap-3 flex-wrap">
            {Object.entries(legendColors).map(([type, cls]) => (
              <div key={type} className="flex items-center gap-1">
                <div className={`w-2.5 h-2.5 rounded-full ${cls}`} />
                <span className="text-xs text-slate-300">{type}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="flex-1 relative bg-slate-950">
          {graphLoading && (
            <div className="absolute inset-0 flex items-center justify-center z-10">
              <div className="flex gap-1">
                {[0,1,2].map(i => (
                  <div key={i} className="w-3 h-3 bg-indigo-400 rounded-full animate-bounce"
                    style={{ animationDelay: `${i*0.15}s` }} />
                ))}
              </div>
            </div>
          )}
          {graphError && (
            <div className="absolute inset-0 flex items-center justify-center z-10 p-8">
              <p className="text-red-400 text-sm text-center">{graphError}</p>
            </div>
          )}

          {!graphLoading && !graphError && (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={onNodeClick}
              fitView
              fitViewOptions={{ padding: 0.2 }}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              proOptions={{ hideAttribution: true }}
            >
              <Background color="#1e293b" gap={16} />
              <Controls position="top-right" />
              <MiniMap
                position="bottom-right"
                style={{ background: '#0f172a', border: '1px solid #1e293b' }}
                maskColor="rgba(0,0,0,0.4)"
                nodeColor={(n) => colorByType[(n.data as any)?.nodeType] || '#64748b'}
              />
            </ReactFlow>
          )}
        </div>
      </div>

      {/* RIGHT: Chat Panel - Keep as is */}
      <div className="w-[38%] flex flex-col">
        <div className="bg-slate-800 border-b border-slate-700 px-5 py-3 shrink-0">
          <h2 className="text-lg font-bold mb-3">Ask the Data</h2>
          <div className="flex gap-2 flex-wrap">
            {['Top billed products', 'Trace order 740506', 'Incomplete order flows'].map(s => (
              <button key={s} onClick={() => sendQuestion(s)}
                className="px-3 py-1 text-xs bg-slate-700 hover:bg-indigo-600 rounded-full border border-slate-600 transition-colors">
                {s}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="h-full flex items-center justify-center text-slate-500 text-sm text-center">
              <p>Ask a question or click a suggestion ↑</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i}>
              {msg.role === 'user' ? (
                <div className="flex justify-end">
                  <div className="bg-indigo-600 rounded-2xl rounded-tr-sm px-4 py-2 max-w-[80%] text-sm">{msg.content}</div>
                </div>
              ) : (
                <div className="flex justify-start">
                  <div className="bg-slate-800 border border-slate-700 rounded-2xl rounded-tl-sm px-4 py-3 max-w-[90%]">
                    <p className="text-sm text-slate-100 leading-relaxed">{msg.content}</p>
                    {msg.sql && (
                      <div className="mt-2">
                        <button onClick={() => setExpanded(p => ({ ...p, [i]: !p[i] }))}
                          className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1">
                          View SQL <span className={`transition-transform ${expanded[i] ? 'rotate-180' : ''}`}>▾</span>
                        </button>
                        {expanded[i] && (
                          <pre className="mt-2 bg-slate-950 rounded p-2 text-xs text-emerald-300 overflow-x-auto border border-slate-700 whitespace-pre-wrap">
                            {msg.sql}
                          </pre>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-slate-800 border border-slate-700 rounded-2xl px-4 py-3">
                <div className="flex gap-1">
                  {[0,1,2].map(i => (
                    <div key={i} className="w-2 h-2 bg-slate-400 rounded-full animate-bounce"
                      style={{ animationDelay: `${i*0.15}s` }} />
                  ))}
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="bg-slate-800 border-t border-slate-700 px-5 py-4 shrink-0">
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Ask about supply chain..."
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') sendQuestion(question); }}
              className="flex-1 bg-slate-700 border border-slate-600 rounded-xl px-4 py-2 text-sm text-white placeholder-slate-400 focus:outline-none focus:border-indigo-500"
            />
            <button 
              onClick={() => sendQuestion(question)}
              disabled={loading || !question.trim()}
              className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 rounded-xl px-5 py-2 text-sm font-semibold transition-colors"
            >
              Send
            </button>
          </div>
        </div>
      </div>

      {/* Node Detail Drawer */}
      {selectedNode && (
        <div className="fixed right-0 top-0 h-screen w-72 bg-slate-800 border-l border-slate-700 p-5 overflow-y-auto z-50 shadow-2xl">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-bold px-2 py-1 rounded-full text-white"
              style={{ background: colorByType[(selectedNode.data as any)?.nodeType] || '#64748b' }}>
              {(selectedNode.data as any)?.nodeType}
            </span>
            <button onClick={() => setSelectedNode(null)} className="text-slate-400 hover:text-white text-lg">✕</button>
          </div>
          <h3 className="text-sm font-bold mb-4 text-white wrap-break-words">
            {(selectedNode.data as any)?.label || selectedNode.id}
          </h3>
          <div className="space-y-2">
            {Object.entries((selectedNode.data as any)?.properties || {}).map(([k, v]) => (
              <div key={k} className="text-xs bg-slate-900 rounded p-2">
                <div className="text-slate-400">{k}</div>
                <div className="text-slate-100 font-medium wrap-break-words">{String(v)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function toRfNode(n: ApiNode, i: number): Node {
  return {
    id: n.id,
    position: { x: (i % 8) * 220, y: Math.floor(i / 8) * 150 },
    data: { label: n.label, nodeType: n.type, properties: n.properties || {} },
    style: {
      background: colorByType[n.type] || '#64748b',
      color: '#fff',
      borderRadius: 10,
      border: '1px solid rgba(255,255,255,0.15)',
      padding: '8px 12px',
      fontSize: 11,
      minWidth: 100,
    },
  };
}

function toRfEdge(e: ApiEdge, i: number): Edge {
  return {
    id: `e${i}-${e.source}-${e.target}`,
    source: e.source,
    target: e.target,
    label: e.label,
    style: { stroke: '#475569' },
    labelStyle: { fontSize: 9, fill: '#94a3b8' },
  };
}

function Page() {
  return (
    <ReactFlowProvider>
      <GraphInner />
    </ReactFlowProvider>
  );
}

export default dynamic(() => Promise.resolve(Page), { ssr: false });

