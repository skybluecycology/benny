import React, { useState, useRef, useEffect } from 'react';
import { Send, Loader, User, Bot, FileText, AlertCircle } from 'lucide-react';
import { useWorkspaceStore } from '../../hooks/useWorkspaceStore';
import { API_BASE_URL, GOVERNANCE_HEADERS } from '../../constants';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: string[];
  isLoading?: boolean;
}

export const NotebookChat: React.FC = () => {
  const { currentWorkspace, selectedDocuments, activeLLMProvider, activeLLMModels } = useWorkspaceStore();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setLoading(true);

    // Placeholder for assistant response to show loading state
    setMessages(prev => [...prev, { role: 'assistant', content: '', isLoading: true }]);

    try {
      const response = await fetch(`${API_BASE_URL}/api/rag/chat`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          ...GOVERNANCE_HEADERS
        },
        body: JSON.stringify({
          query: userMessage,
          workspace: currentWorkspace,
          selected_sources: selectedDocuments,
          provider: activeLLMProvider,
          model: activeLLMModels[activeLLMProvider]
        })
      });

      if (!response.ok) {
        throw new Error(`Chat failed: ${response.statusText}`);
      }

      const data = await response.json();
      
      // Update the loading assistant message with actual data
      setMessages(prev => {
        const updated = [...prev];
        const lastIndex = updated.length - 1;
        updated[lastIndex] = {
          role: 'assistant',
          content: data.answer,
          sources: data.sources || [],
          isLoading: false
        };
        return updated;
      });
    } catch (error) {
      console.error('Chat error:', error);
      setMessages(prev => {
        const updated = [...prev];
        const lastIndex = updated.length - 1;
        updated[lastIndex] = {
          role: 'assistant',
          content: `Sorry, I encountered an error: ${error instanceof Error ? error.message : String(error)}`,
          isLoading: false
        };
        return updated;
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="notebook-chat-container" style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-canvas)' }}>
      {/* Selection Context Header */}
      {selectedDocuments.length > 0 && (
        <div style={{ 
          padding: '8px 16px', 
          background: 'rgba(165, 110, 255, 0.1)', 
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          fontSize: '11px',
          color: 'var(--branch-purple)'
        }}>
          <FileText size={12} />
          <span>Discussing {selectedDocuments.length} selected documents</span>
        </div>
      )}

      {/* Messages Area */}
      <div className="chat-messages" style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
        {messages.length === 0 && (
          <div className="empty-state" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', opacity: 0.5 }}>
            <Bot size={48} style={{ marginBottom: '16px' }} />
            <h3>RAG Discovery Chat</h3>
            <p>Ask anything about your workspace documents.</p>
            {selectedDocuments.length === 0 && (
              <p style={{ fontSize: '11px', marginTop: '12px' }}>
                <AlertCircle size={10} style={{ verticalAlign: 'middle', marginRight: '4px' }} />
                Searching entire workspace. Select files to narrow focus.
              </p>
            )}
          </div>
        )}
        
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role === 'user' ? 'message-user' : 'message-assistant'}`}>
            <div className="message-content">
              {msg.isLoading ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Loader size={14} className="animate-spin" />
                  <span>Synthesizing...</span>
                </div>
              ) : (
                msg.content
              )}
            </div>
            
            {!msg.isLoading && msg.sources && msg.sources.length > 0 && (
              <div className="message-sources">
                <div style={{ fontWeight: 600, marginBottom: '4px', fontSize: '10px' }}>SOURCES:</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                  {msg.sources.map((src, j) => (
                    <span key={j} style={{ background: 'rgba(255,255,255,0.1)', padding: '2px 6px', borderRadius: '4px' }}>
                      {src}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="chat-input-area" style={{ padding: '16px', borderTop: '1px solid var(--border-color)', background: 'var(--bg-panel)' }}>
        <div style={{ display: 'flex', gap: '12px' }}>
          <input
            type="text"
            className="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder={selectedDocuments.length > 0 ? "Ask about selected documents..." : "Ask about the workspace..."}
            disabled={loading}
            style={{ 
              flex: 1, 
              background: 'var(--bg-input)', 
              border: '1px solid var(--border-color)', 
              borderRadius: 'var(--radius-md)', 
              padding: '12px 16px',
              color: 'var(--text-primary)',
              outline: 'none'
            }}
          />
          <button
            className="btn btn-gradient"
            onClick={handleSend}
            disabled={loading || !input.trim()}
            style={{ width: '44px', height: '44px', borderRadius: 'var(--radius-md)', padding: 0 }}
          >
            {loading ? <Loader size={18} className="animate-spin" /> : <Send size={18} />}
          </button>
        </div>
      </div>
    </div>
  );
};

export default NotebookChat;
