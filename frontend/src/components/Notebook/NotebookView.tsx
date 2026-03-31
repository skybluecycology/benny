import { useState } from 'react';
import { Send, Loader, BookOpen } from 'lucide-react';
import { useWorkspaceStore } from '../../hooks/useWorkspaceStore';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: string[];
}

export default function NotebookView() {
  const { currentWorkspace, activeLLMProvider, activeLLMModels, selectedDocuments } = useWorkspaceStore();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    if (!input.trim()) return;
    
    const userMessage: Message = { role: 'user', content: input };
    setMessages([...messages, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await fetch('http://localhost:8005/api/rag/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: input,
          workspace: currentWorkspace,
          provider: activeLLMProvider,
          model: activeLLMModels[activeLLMProvider],
          top_k: 20,
          selected_sources: selectedDocuments
        })
      });

      if (response.ok) {
        const data = await response.json();
        const assistantMessage: Message = {
          role: 'assistant',
          content: data.response || data.answer || 'No response',
          sources: data.sources || []
        };
        setMessages(prev => [...prev, assistantMessage]);
      } else {
        const errorMessage: Message = {
          role: 'assistant',
          content: 'Sorry, I encountered an error processing your question.'
        };
        setMessages(prev => [...prev, errorMessage]);
      }
    } catch (error) {
      console.error('Query failed:', error);
      const errorMessage: Message = {
        role: 'assistant',
        content: 'Failed to connect to the server. Please make sure files are indexed.'
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="notebook-view">
      {/* Empty state or welcome message */}
      {messages.length === 0 && (
        <div className="empty-state notebook-empty">
          <BookOpen size={48} />
          <h3>Chat with your documents</h3>
          <p>
            Current Workspace: <strong>{currentWorkspace}</strong><br/>
            Upload files in the sidebar, index them, and ask questions.
          </p>
        </div>
      )}

      {/* Chat messages */}
      {messages.length > 0 && (
        <div className="chat-messages">
          {messages.map((msg, idx) => {
            // Parse inline citations like [Source: filename.pdf]
            let contentElements: React.ReactNode[] = [msg.content];
            if (msg.role === 'assistant') {
              const parts = msg.content.split(/(\[Source:\s*[^\]]+\])/);
              contentElements = parts.map((part, i) => {
                const match = part.match(/\[Source:\s*([^\]]+)\]/);
                if (match && match[1]) {
                  return (
                    <span key={i} className="source-citation" style={{ 
                      display: 'inline-flex',
                      alignItems: 'center',
                      background: 'rgba(139, 92, 246, 0.15)',
                      color: 'var(--primary)',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      fontSize: '11px',
                      fontWeight: 600,
                      margin: '0 4px',
                      border: '1px solid rgba(139, 92, 246, 0.3)',
                      cursor: 'help'
                    }} title={`Source: ${match[1]}`}>
                      {match[1]}
                    </span>
                  );
                }
                return <span key={i} style={{ whiteSpace: 'pre-wrap' }}>{part}</span>;
              });
            }

            return (
            <div key={idx} className={`message message-${msg.role}`}>
              <div className="message-content">{contentElements}</div>
              {msg.sources && msg.sources.length > 0 && (
                <div className="message-sources">
                  Sources: {msg.sources.join(', ')}
                </div>
              )}
            </div>
            );
          })}
          {loading && (
            <div className="message message-loading" style={{ opacity: 0.8, fontStyle: 'italic', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Loader className="animate-spin" size={16} />
              <span>{activeLLMProvider} is thinking...</span>
            </div>
          )}
        </div>
      )}

      {/* Input area */}
      <div className="chat-input-area">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Ask a question about your documents..."
          className="chat-input"
          disabled={loading}
        />
        <button 
          onClick={handleSend} 
          className="btn btn-gradient"
          disabled={loading || !input.trim()}
        >
          {loading ? <Loader className="animate-spin" size={16} /> : <Send size={16} />}
        </button>
      </div>
    </div>
  );
}

