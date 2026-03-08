import { Settings2 } from 'lucide-react';

interface SwarmConfig {
  model: string;
  max_concurrency: number;
  workspace: string;
}

interface SwarmConfigPanelProps {
  config: SwarmConfig;
  onChange: (config: SwarmConfig) => void;
}

export default function SwarmConfigPanel({ config, onChange }: SwarmConfigPanelProps) {
  const handleChange = (key: keyof SwarmConfig, value: string | number) => {
    onChange({ ...config, [key]: value });
  };

  return (
    <div className="swarm-config-panel">
      <div className="swarm-config-header">
        <Settings2 size={16} />
        <span>Swarm Configuration</span>
      </div>
      
      <div className="swarm-config-content">
        {/* Model Selector */}
        <div className="form-group">
          <label className="form-label" htmlFor="swarm-model">LLM Model</label>
          <select
            id="swarm-model"
            className="form-select"
            value={config.model}
            onChange={(e) => handleChange('model', e.target.value)}
          >
            <optgroup label="Local Models">
              <option value="ollama/llama3.2">Llama 3.2 (Ollama)</option>
              <option value="ollama/gemma:2b">Gemma 2B (Ollama)</option>
              <option value="openai/gemma3:4b">Gemma 3 4B (FastFlowLM)</option>
              <option value="ollama/deepseek-r1:8b">DeepSeek R1 (Ollama)</option>
            </optgroup>
            <optgroup label="Cloud Models">
              <option value="gpt-4-turbo">GPT-4 Turbo</option>
              <option value="claude-3-sonnet">Claude 3 Sonnet</option>
            </optgroup>
          </select>
        </div>

        {/* Concurrency Slider */}
        <div className="form-group">
          <label className="form-label" htmlFor="swarm-concurrency">
            Max Concurrency: <strong>{config.max_concurrency}</strong>
          </label>
          <input
            id="swarm-concurrency"
            type="range"
            className="form-range"
            min={1}
            max={10}
            step={1}
            value={config.max_concurrency}
            onChange={(e) => handleChange('max_concurrency', parseInt(e.target.value))}
          />
          <div className="form-hint">
            {config.max_concurrency === 1 
              ? 'Sequential execution (safe for local LLM)'
              : config.max_concurrency <= 3
              ? 'Low concurrency (recommended for most setups)'
              : 'High concurrency (requires powerful LLM)'}
          </div>
        </div>

        {/* Workspace */}
        <div className="form-group">
          <label className="form-label" htmlFor="swarm-workspace">Workspace</label>
          <input
            id="swarm-workspace"
            type="text"
            className="form-input"
            value={config.workspace}
            onChange={(e) => handleChange('workspace', e.target.value)}
            placeholder="default"
          />
        </div>
      </div>
    </div>
  );
}
