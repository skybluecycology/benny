import { useState, useEffect } from 'react';
import { Brain, Upload, Zap, Loader, ChevronDown, ChevronUp, Book, Trash2, Database } from 'lucide-react';
import { useWorkspaceStore } from '../../hooks/useWorkspaceStore';
import { useLLMStatus } from '../../hooks/useLLMStatus';
import { API_BASE_URL } from '../../constants';

interface SynthesisPanelProps {
  onGraphUpdated?: () => void;
}

export const SynthesisPanel: React.FC<SynthesisPanelProps> = ({ onGraphUpdated }) => {
  const { 
    currentWorkspace, 
    activeLLMProvider, 
    setActiveLLMProvider, 
    activeLLMModels, 
    setActiveLLMModel,
    selectedDocuments, 
    toggleSelectedDocument, 
    setSynthesisResults 
  } = useWorkspaceStore();
  const { providers } = useLLMStatus(30000);
  const [ingestText, setIngestText] = useState('');
  const [sourceName, setSourceName] = useState('');
  const [loading, setLoading] = useState(false);
  const [localResults, setLocalResults] = useState<any>(null);
  const [isExpanded, setIsExpanded] = useState(true);
  const [embeddingProvider, setEmbeddingProvider] = useState('local');
  const [indexedDocs, setIndexedDocs] = useState<string[]>([]);
  const [mappedDocs, setMappedDocs] = useState<string[]>([]);
  const [synthesisDirection, setSynthesisDirection] = useState('');
  const [embeddingModel, setEmbeddingModel] = useState('nomic-embed-text-v1-GGUF');
  const [inferenceDelay, setInferenceDelay] = useState(2.0);

  const fetchStatusAndMapped = async () => {
    try {
      const timestamp = Date.now();
      const [statusRes, mappedRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/rag/status?workspace=${currentWorkspace}`),
        fetch(`${API_BASE_URL}/api/graph/sources?workspace=${currentWorkspace}&t=${timestamp}`)
      ]);
      
      if (statusRes.ok) {
        const data = await statusRes.json();
        setIndexedDocs(data.documents || []);
      }
      
      if (mappedRes.ok) {
        const data = await mappedRes.json();
        setMappedDocs(data.sources || []);
      }
    } catch (error) {
      console.error('Failed to fetch status:', error);
    }
  };

  useEffect(() => {
    fetchStatusAndMapped();
  }, [currentWorkspace]);

  const handleRemoveFromGraph = async (doc: string) => {
    if (!window.confirm(`Remove ${doc} from the Knowledge Graph? This deletes all its extracted triples.`)) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/graph/sources/${encodeURIComponent(doc)}?workspace=${currentWorkspace}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        if (onGraphUpdated) onGraphUpdated();
        await fetchStatusAndMapped();
        setLocalResults({ error: null, success_msg: `Removed ${doc} from graph.` });
      } else {
        setLocalResults({ error: "Failed to remove doc." });
      }
    } catch (err) {
      setLocalResults({ error: String(err) });
    } finally {
      setLoading(false);
    }
  };


  const handleIngest = async () => {
    if (!ingestText.trim()) return;
    setLoading(true);
    setLocalResults(null);
    setSynthesisResults(null);

    try {
      const res = await fetch(`${API_BASE_URL}/api/graph/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: ingestText,
          source_name: sourceName || 'manual',
          workspace: currentWorkspace,
          provider: activeLLMProvider,
          model: activeLLMModels[activeLLMProvider],
          embed: true,
          embedding_provider: embeddingProvider,
          embedding_model: embeddingModel
        })
      });

      if (res.ok) {
        const data = await res.json();
        setLocalResults(data);
        setSynthesisResults(data);
        setIngestText('');
        setSourceName('');
        await fetchStatusAndMapped();
        if (onGraphUpdated) onGraphUpdated();
      } else {
        const err = await res.text();
        setLocalResults({ error: err });
      }
    } catch (err) {
      setLocalResults({ error: String(err) });
    } finally {
      setLoading(false);
    }
  };

  const handleIngestFiles = async () => {
    if (selectedDocuments.length === 0) return;
    setLoading(true);
    setLocalResults(null);
    setSynthesisResults(null);

    try {
      const res = await fetch(`${API_BASE_URL}/api/graph/ingest-files`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          files: selectedDocuments,
          workspace: currentWorkspace,
          provider: activeLLMProvider,
          model: activeLLMModels[activeLLMProvider],
          embed: true,
          embedding_provider: embeddingProvider,
          embedding_model: embeddingModel,
          direction: synthesisDirection,
          inference_delay: inferenceDelay
        })
      });

      if (res.ok) {
        const data = await res.json();
        setLocalResults(data);
        setSynthesisResults(data);
        await fetchStatusAndMapped();
        if (onGraphUpdated) onGraphUpdated();
      } else {
        const err = await res.text();
        setLocalResults({ error: err });
      }
    } catch (err) {
      setLocalResults({ error: String(err) });
    } finally {
      setLoading(false);
    }
  };

  const handleSynthesize = async () => {
    setLoading(true);
    setLocalResults(null);
    setSynthesisResults(null);

    try {
      const res = await fetch(`${API_BASE_URL}/api/graph/synthesize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace: currentWorkspace,
          provider: activeLLMProvider,
          model: activeLLMModels[activeLLMProvider]
        })
      });

      if (res.ok) {
        const data = await res.json();
        setLocalResults(data);
        setSynthesisResults(data);
        if (onGraphUpdated) onGraphUpdated();
      } else {
        const err = await res.text();
        setLocalResults({ error: err });
      }
    } catch (err) {
      setLocalResults({ error: String(err) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="synthesis-panel">
      <button 
        className="synthesis-panel-header"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Brain size={16} style={{ color: 'var(--primary)' }} />
          <span>Synthesis Engine</span>
        </div>
        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {isExpanded && (
        <div className="synthesis-panel-body">
          {/* Text Ingestion */}
          <div className="synthesis-section">
            <label className="synthesis-label">
              <Upload size={12} /> Ingest Text → Triples
            </label>
            <input
              type="text"
              value={sourceName}
              onChange={(e) => setSourceName(e.target.value)}
              placeholder="Source name (e.g. research_paper.pdf)"
              className="synthesis-input"
            />
            <textarea
              value={ingestText}
              onChange={(e) => setIngestText(e.target.value)}
              placeholder="Paste text to extract knowledge triples..."
              className="synthesis-textarea"
              rows={4}
            />
            <div className="synthesis-row" style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
              <div style={{ flex: 1 }}>
                <select
                  value={embeddingProvider}
                  onChange={(e) => setEmbeddingProvider(e.target.value)}
                  className="synthesis-select"
                  style={{ width: '100%' }}
                >
                  <option value="local">Local Embedding (Lemonade/Ollama)</option>
                  <option value="openai">OpenAI Embedding</option>
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <input 
                  type="text" 
                  value={embeddingModel} 
                  onChange={(e) => setEmbeddingModel(e.target.value)} 
                  className="synthesis-input" 
                  placeholder="Embedding Model (e.g. nomic-embed-text)"
                  title="Embedding Model Name"
                />
              </div>
            </div>
            <div className="synthesis-row">
              <button
                className="btn btn-gradient"
                onClick={handleIngest}
                disabled={loading || !ingestText.trim()}
              >
                {loading ? <Loader size={14} className="animate-spin" /> : <Upload size={14} />}
                Extract
              </button>
            </div>
          </div>

          {/* Indexed Document Selection */}
          <div className="synthesis-section">
            <label className="synthesis-label">
              <Book size={12} /> Select Indexed Docs
            </label>
            <div className="synthesis-doc-list">
              {indexedDocs.length === 0 ? (
                <div className="synthesis-no-docs">No indexed documents found.</div>
              ) : (
                indexedDocs.map(doc => {
                  const isMapped = mappedDocs.includes(doc);
                  return (
                    <div key={doc} className="synthesis-doc-item" onClick={() => toggleSelectedDocument(doc)}>
                      <input 
                        type="checkbox"
                        checked={selectedDocuments.includes(doc)}
                        onChange={(e) => {
                          e.stopPropagation();
                          toggleSelectedDocument(doc);
                        }}
                        style={{ cursor: 'pointer' }}
                        title={`Select ${doc}`}
                      />
                      <span className="synthesis-doc-name">{doc}</span>
                      {isMapped && (
                        <span className="synthesis-doc-badge">
                          <Database size={10} /> Mapped
                        </span>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Batch File Ingestion */}
          {selectedDocuments.length > 0 && (
            <div className="synthesis-section highlight">
              <label className="synthesis-label" style={{ color: 'var(--primary)' }}>
                <Brain size={12} /> Workspace Mapping
              </label>
              <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '8px' }}>
                Create knowledge map for {selectedDocuments.length} selected document{selectedDocuments.length !== 1 ? 's' : ''}.
                <br/>
                <strong>LLM Model:</strong> {activeLLMModels[activeLLMProvider] || 'Default'}
              </p>
              
              <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '10px', color: 'var(--text-muted)' }}>LLM Provider</label>
                  <select
                    value={activeLLMProvider}
                    onChange={(e) => setActiveLLMProvider(e.target.value)}
                    className="synthesis-select"
                    style={{ width: '100%' }}
                    title="Select LLM Provider"
                    aria-label="Select LLM Provider"
                  >
                    {Object.entries(providers).map(([id, p]) => (
                      <option key={id} value={id}>{p.name} {p.running ? '●' : '○'}</option>
                    ))}
                    <optgroup label="Cloud">
                      <option value="openai">OpenAI</option>
                      <option value="anthropic">Anthropic</option>
                    </optgroup>
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Model</label>
                  <select
                    value={activeLLMModels[activeLLMProvider] || ''}
                    onChange={(e) => setActiveLLMModel(activeLLMProvider, e.target.value)}
                    className="synthesis-select"
                    style={{ width: '100%' }}
                    title="Select Model"
                    aria-label="Select Model"
                  >
                    {!providers[activeLLMProvider] ? (
                       <option value="">Loading models...</option>
                    ) : providers[activeLLMProvider]?.models?.data?.length > 0 ? (
                      providers[activeLLMProvider].models.data.map((m: any) => (
                        <option key={m.id} value={m.id}>
                          {m.id} {m.status === 'fallback' ? '(NPU Fallback)' : ''}
                        </option>
                      ))
                    ) : (
                      <optgroup label="Default Fallbacks">
                        <option value="gpt-4-turbo">GPT-4 Turbo</option>
                        <option value="claude-3-sonnet">Claude 3 Sonnet</option>
                      </optgroup>
                    )}
                  </select>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                <div style={{ flex: '0 0 100px' }}>
                  <label style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Delay (s)</label>
                  <input 
                    type="number" 
                    value={inferenceDelay} 
                    onChange={(e) => setInferenceDelay(parseFloat(e.target.value) || 0)} 
                    className="synthesis-input"
                    step="0.5"
                    min="0"
                    title="Inference Delay to prevent hardware throttling"
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Synthesis Direction</label>
                  <input
                    type="text"
                    value={synthesisDirection}
                    onChange={(e) => setSynthesisDirection(e.target.value)}
                    placeholder="e.g. 'Extract points on how to train an AI agent'"
                    className="synthesis-input"
                  />
                </div>
              </div>
              <button
                className="btn btn-gradient synthesis-btn-full mt-2"
                onClick={handleIngestFiles}
                disabled={loading}
                style={{ background: 'linear-gradient(135deg, #a88bfa, #8b5cf6)' }}
              >
                {loading ? <Loader size={14} className="animate-spin" /> : <Brain size={14} />}
                Map Selected Documents ({selectedDocuments.length})
              </button>
            </div>
          )}

          {/* Synthesis Trigger */}
          <div className="synthesis-section">
            <label className="synthesis-label">
              <Zap size={12} /> Run Synthesis (Find Analogies)
            </label>
            <button
              className="btn btn-gradient synthesis-btn-full"
              onClick={handleSynthesize}
              disabled={loading}
            >
              {loading ? <Loader size={14} className="animate-spin" /> : <Zap size={14} />}
              Discover Structural Isomorphisms
            </button>
          </div>

          {/* Manage Mapped Documents */}
          {mappedDocs.length > 0 && (
            <div className="synthesis-section">
              <label className="synthesis-label text-muted">
                <Database size={12} /> Graph Assets
              </label>
              <div className="synthesis-doc-list mt-0">
                {mappedDocs.map(doc => (
                  <div key={doc} className="synthesis-doc-item read-only">
                    <span className="synthesis-doc-name">{doc}</span>
                    <button 
                      className="btn-icon btn-ghost danger" 
                      onClick={() => handleRemoveFromGraph(doc)}
                      title="Remove from graph"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Results */}
          {localResults && (
            <div className="synthesis-results">
              {localResults.error ? (
                <div className="synthesis-error">❌ {localResults.error}</div>
              ) : (
                <>
                  {localResults.success_msg && (
                    <div className="synthesis-stat success">
                      ✅ {localResults.success_msg}
                    </div>
                  )}
                  {localResults.triples_extracted !== undefined && (
                    <div className="synthesis-stat">
                      ✅ {localResults.triples_extracted} triples extracted, {localResults.triples_stored} stored
                    </div>
                  )}
                  {localResults.conflicts_detected > 0 && (
                    <div className="synthesis-stat conflict">
                      ⚠️ {localResults.conflicts_detected} conflicts detected
                    </div>
                  )}
                  {localResults.concepts_embedded > 0 && (
                    <div className="synthesis-stat">
                      🧮 {localResults.concepts_embedded} concepts embedded
                    </div>
                  )}
                  {localResults.analogies_found !== undefined && (
                    <div className="synthesis-stat">
                      🔗 {localResults.analogies_found} analogies discovered
                    </div>
                  )}
                  {localResults.triples && localResults.triples.length > 0 && (
                    <div className="synthesis-triples">
                      {localResults.triples.map((t: string[], i: number) => (
                        <div key={i} className="triple-item">
                          <span className="triple-subject">{t[0]}</span>
                          <span className="triple-predicate">{t[1]}</span>
                          <span className="triple-object">{t[2]}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {localResults.analogies && localResults.analogies.length > 0 && (
                    <div className="synthesis-analogies">
                      {localResults.analogies.map((a: any, i: number) => (
                        <div key={i} className="analogy-item">
                          <strong>{a.concept_a} ↔ {a.concept_b}</strong>
                          <p>{a.description}</p>
                          <span className="pattern-tag">Pattern: {a.pattern}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SynthesisPanel;
