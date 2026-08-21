import { useEffect, useState } from 'react';
import { Cpu, Gauge, KeyRound, RefreshCw, Save, Activity } from 'lucide-react';
import { getRuntimeConfig, reindexAll, updateRuntimeConfig } from '@/api/config';
import { getMetrics, type HistogramSnapshot } from '@/api/metrics';
import { useBackends } from '@/hooks/useSystem';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import type { AcceleratorMode, RerankBackend } from '@/types/api';

// 模型设置页：对话模型 / 向量嵌入 / 重排与解析。模型名自由填写，下拉只给常用建议，不锁死内置模型。

const LLM_PROVIDERS = [
  { value: 'ollama', label: 'Ollama（本地）', baseUrl: 'http://localhost:11434/v1' },
  { value: 'openai', label: 'OpenAI 兼容 API', baseUrl: '' },
] as const;

// 向量嵌入模型建议（自由输入，这些常用模型一键可选）
const EMBED_MODEL_SUGGESTIONS = [
  'bge-m3',
  'qwen3-embedding:0.6b',
  'text-embedding-3-small',
  'text-embedding-3-large',
  'text-embedding-004',
  'gemini-embedding-001',
  'nomic-embed-text',
  'mxbai-embed-large',
] as const;

const ACCELERATOR_OPTIONS = [
  { value: 'auto', label: '自动（有 GPU 则用，否则 CPU）' },
  { value: 'cuda', label: 'GPU（CUDA）' },
  { value: 'cpu', label: '仅 CPU' },
] as const;

function Select({
  id,
  value,
  onChange,
  options,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  options: ReadonlyArray<{ value: string; label: string }>;
}) {
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-md border border-line bg-surface-2 px-3 py-2 text-sm text-fg focus:outline-none focus:ring-1 focus:ring-accent"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function Settings() {
  const { refetch: refetchBackends } = useBackends();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);

  // —— 对话模型 ——
  const [llmProvider, setLlmProvider] = useState<'ollama' | 'openai'>('ollama');
  const [llmBaseUrl, setLlmBaseUrl] = useState('http://localhost:11434/v1');
  const [llmModel, setLlmModel] = useState('');
  const [llmApiKey, setLlmApiKey] = useState('');
  const [llmApiKeySet, setLlmApiKeySet] = useState(false);

  // —— 向量嵌入 ——
  const [embedEndpoint, setEmbedEndpoint] = useState('');
  const [embedModel, setEmbedModel] = useState('');
  const [embedApiKey, setEmbedApiKey] = useState('');
  const [embedApiKeySet, setEmbedApiKeySet] = useState(false);
  const [reindexing, setReindexing] = useState(false);

  // —— 重排 / 解析 / 计算设备 ——
  const [rerankModel, setRerankModel] = useState('');
  const [rerankBackend, setRerankBackend] = useState<RerankBackend>('bge-reranker-v2-m3');
  const [parseBackend, setParseBackend] = useState<'docling' | 'pdf'>('docling');
  const [accelerator, setAccelerator] = useState<AcceleratorMode>('auto');
  const [device, setDevice] = useState('');
  const [cudaAvailable, setCudaAvailable] = useState(false);

  // —— 性能指标 ——
  const [latency, setLatency] = useState<Record<string, HistogramSnapshot>>({});

  useEffect(() => {
    getRuntimeConfig()
      .then((cfg) => {
        const llmBackend = cfg.llm.backend === 'openai' ? 'openai' : 'ollama';
        setLlmProvider(llmBackend);
        setLlmBaseUrl(cfg.llm.base_url || 'http://localhost:11434/v1');
        setLlmModel(cfg.llm.model ?? '');
        setLlmApiKeySet(cfg.llm.api_key_set);
        setEmbedEndpoint(cfg.embed?.endpoint ?? '');
        setEmbedModel(cfg.embed?.model ?? '');
        setEmbedApiKeySet(!!cfg.embed?.api_key_set);
        setRerankModel(cfg.rerank?.model ?? '');
        setRerankBackend(cfg.rerank?.backend === 'mock' ? 'mock' : 'bge-reranker-v2-m3');
        setParseBackend(cfg.parse?.backend === 'pdf' ? 'pdf' : 'docling');
        setAccelerator(cfg.accelerator ?? 'auto');
        setDevice(cfg.device ?? '');
        setCudaAvailable(!!cfg.cuda_available);
      })
      .catch(() => setMessage({ tone: 'err', text: '读取当前配置失败，请刷新重试' }))
      .finally(() => setLoading(false));

    getMetrics()
      .then((m) => setLatency(m.histograms))
      .catch(() => {}); // 静默失败，指标非关键
  }, []);

  const onSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const cfg = await updateRuntimeConfig({
        llm: {
          backend: llmProvider,
          base_url: llmBaseUrl,
          model: llmModel,
          api_key: llmApiKey, // 空串 = 清除已存密钥
          accelerator,
        },
        embed: {
          backend: 'http',
          model: embedModel,
          endpoint: embedEndpoint,
          api_key: embedApiKey, // 空串 = 清除已存密钥
        },
        rerank: { backend: rerankBackend, model: rerankModel },
        parse: { backend: parseBackend },
      });
      setLlmApiKey(''); // 清空输入框，避免明文驻留
      setLlmApiKeySet(cfg.llm.api_key_set);
      setEmbedApiKey('');
      setEmbedApiKeySet(!!cfg.embed?.api_key_set);
      setDevice(cfg.device ?? '');
      setCudaAvailable(!!cfg.cuda_available);
      setMessage({
        tone: 'ok',
        text:
          `已保存并即时生效：对话=${llmModel || llmBaseUrl || '未配置'} · ` +
          `嵌入=${embedModel ? `${embedModel} @ ${embedEndpoint}` : embedEndpoint} · ` +
          `重排=${rerankModel || '默认'} · 设备=${device || '自动'}`,
      });
      refetchBackends();
    } catch (err) {
      setMessage({
        tone: 'err',
        text: `保存失败：${err instanceof Error ? err.message : String(err)}`,
      });
    } finally {
      setSaving(false);
    }
  };

  const onReindex = async () => {
    setReindexing(true);
    setMessage(null);
    try {
      const r = await reindexAll();
      setMessage({ tone: 'ok', text: `已按当前嵌入模型重新索引 ${r.reindexed} 个分块` });
    } catch (err) {
      setMessage({
        tone: 'err',
        text: `重新索引失败：${err instanceof Error ? err.message : String(err)}`,
      });
    } finally {
      setReindexing(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <Cpu size={18} className="text-accent" />
            对话模型
          </CardTitle>
          <p className="text-xs text-meta">负责回答生成。支持本地 Ollama 或任意 OpenAI 兼容接口。</p>
        </CardHeader>
        <CardBody className="space-y-4">
          {loading ? (
            <p className="text-sm text-muted">加载中…</p>
          ) : (
            <>
              <div className="space-y-1.5">
                <label htmlFor="llm-provider" className="text-sm text-muted">
                  服务商
                </label>
                <Select
                  id="llm-provider"
                  value={llmProvider}
                  onChange={(v) => {
                    setLlmProvider(v as 'ollama' | 'openai');
                    const preset = LLM_PROVIDERS.find((p) => p.value === v);
                    if (preset?.baseUrl) setLlmBaseUrl(preset.baseUrl);
                  }}
                  options={LLM_PROVIDERS}
                />
              </div>

              <div className="space-y-1.5">
                <label htmlFor="llm-base-url" className="text-sm text-muted">
                  接口地址（Endpoint）
                </label>
                <Input
                  id="llm-base-url"
                  value={llmBaseUrl}
                  onChange={(e) => setLlmBaseUrl(e.target.value)}
                  placeholder="http://localhost:11434/v1"
                  autoComplete="off"
                />
                <p className="text-xs text-meta">
                  Ollama 默认 http://localhost:11434/v1；留空则用后端环境变量默认值
                </p>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="llm-model" className="flex items-center gap-1.5 text-sm text-muted">
                  模型名
                </label>
                <Input
                  id="llm-model"
                  value={llmModel}
                  onChange={(e) => setLlmModel(e.target.value)}
                  placeholder="如 qwen3:4b / gpt-4o-mini"
                  autoComplete="off"
                />
              </div>

              <div className="space-y-1.5">
                <label htmlFor="llm-api-key" className="flex items-center gap-1.5 text-sm text-muted">
                  <KeyRound size={14} />
                  API 密钥
                  {llmApiKeySet && (
                    <span className="rounded-sm bg-success/10 px-1.5 py-0.5 text-xs text-success">
                      已设置（输入新值覆盖，留空保存则清除）
                    </span>
                  )}
                </label>
                <Input
                  id="llm-api-key"
                  type="password"
                  value={llmApiKey}
                  onChange={(e) => setLlmApiKey(e.target.value)}
                  placeholder={llmApiKeySet ? '••••••••（已保存，不回显）' : 'sk-…'}
                  autoComplete="off"
                />
                <p className="text-xs text-meta">本地 Ollama 通常不需要密钥；接口不回显明文</p>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="llm-accelerator" className="flex items-center gap-1.5 text-sm text-muted">
                  <Gauge size={14} />
                  计算设备（嵌入 / 重排，仅本地模型时生效）
                </label>
                <Select
                  id="llm-accelerator"
                  value={accelerator}
                  onChange={(v) => setAccelerator(v as AcceleratorMode)}
                  options={ACCELERATOR_OPTIONS}
                />
                <p className="text-xs text-meta">
                  {cudaAvailable
                    ? `当前生效设备：${device === 'cuda' ? 'GPU（CUDA，FP16）' : 'CPU（FP32）'}`
                    : '当前环境未检测到 CUDA，将使用 CPU（FP32）计算。'}
                </p>
              </div>
            </>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <Gauge size={18} className="text-accent" />
            向量嵌入
          </CardTitle>
          <p className="text-xs text-meta">文档先转成向量再做语义检索。填入任意 OpenAI 兼容的嵌入接口。</p>
        </CardHeader>
        <CardBody className="space-y-4">
          {loading ? (
            <p className="text-sm text-muted">加载中…</p>
          ) : (
            <>
              <div className="space-y-1.5">
                <label htmlFor="embed-endpoint" className="text-sm text-muted">
                  接口地址（Endpoint）
                </label>
                <Input
                  id="embed-endpoint"
                  value={embedEndpoint}
                  onChange={(e) => setEmbedEndpoint(e.target.value)}
                  placeholder="http://localhost:11434/v1/embeddings"
                  autoComplete="off"
                />
                <p className="text-xs text-meta">
                  OpenAI 兼容 /v1/embeddings 地址；本地 Ollama / LM Studio 等可留空 API 密钥
                </p>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="embed-model" className="text-sm text-muted">
                  模型名
                </label>
                <Input
                  id="embed-model"
                  list="embed-model-list"
                  value={embedModel}
                  onChange={(e) => setEmbedModel(e.target.value)}
                  placeholder="如 bge-m3 / text-embedding-3-large"
                  autoComplete="off"
                />
                <datalist id="embed-model-list">
                  {EMBED_MODEL_SUGGESTIONS.map((m) => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="embed-api-key" className="flex items-center gap-1.5 text-sm text-muted">
                  <KeyRound size={14} />
                  API 密钥
                  {embedApiKeySet && (
                    <span className="rounded-sm bg-success/10 px-1.5 py-0.5 text-xs text-success">
                      已设置（输入新值覆盖，留空保存则清除）
                    </span>
                  )}
                </label>
                <Input
                  id="embed-api-key"
                  type="password"
                  value={embedApiKey}
                  onChange={(e) => setEmbedApiKey(e.target.value)}
                  placeholder={embedApiKeySet ? '••••••••（已保存，不回显）' : 'sk-…（本地模型留空）'}
                  autoComplete="off"
                />
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <Button variant="ghost" onClick={onReindex} disabled={reindexing}>
                  <RefreshCw size={15} />
                  {reindexing ? '重新索引中…' : '重新索引全部文档'}
                </Button>
                <p className="text-xs text-meta">
                  更换嵌入模型 / 接口地址后需重新索引，让已有文档向量与当前配置对齐
                </p>
              </div>
            </>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <Cpu size={18} className="text-accent" />
            重排与解析
          </CardTitle>
          <p className="text-xs text-meta">提高检索精度与 PDF 解析；通常保持默认即可。</p>
        </CardHeader>
        <CardBody className="space-y-4">
          {loading ? (
            <p className="text-sm text-muted">加载中…</p>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label htmlFor="rerank-model" className="text-sm text-muted">
                  重排模型名
                </label>
                <Input
                  id="rerank-model"
                  value={rerankModel}
                  onChange={(e) => setRerankModel(e.target.value)}
                  placeholder="如 BAAI/bge-reranker-v2-m3"
                  autoComplete="off"
                />
                <p className="text-xs text-meta">留空则使用后端默认重排模型</p>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm text-muted">文档解析引擎</label>
                <Select
                  id="parse-backend"
                  value={parseBackend}
                  onChange={(v) => setParseBackend(v as 'docling' | 'pdf')}
                  options={[
                    { value: 'pdf', label: 'PDF 轻量解析（pypdf，按页抽取文本）' },
                    { value: 'docling', label: 'Docling（结构化解析，PDF → 布局/标题分块）' },
                  ]}
                />
              </div>
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          <div className="flex items-center gap-3">
            <Button onClick={onSave} disabled={saving || loading}>
              <Save size={16} />
              {saving ? '保存中…' : '保存并生效'}
            </Button>
            <Button variant="ghost" onClick={() => refetchBackends()} type="button">
              <RefreshCw size={16} />
              刷新状态
            </Button>
          </div>
          {message && (
            <p
              role={message.tone === 'err' ? 'alert' : 'status'}
              className={`mt-3 text-sm ${message.tone === 'err' ? 'text-danger' : 'text-success'}`}
            >
              {message.text}
            </p>
          )}
        </CardBody>
      </Card>

      {/* 性能概览 */}
      {Object.keys(latency).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>
              <Activity size={18} className="text-accent" />
              性能概览
            </CardTitle>
            <p className="text-xs text-meta">进程内延迟直方图（重启清零，需有流量才显示数据）</p>
          </CardHeader>
          <CardBody>
            <div className="grid gap-4 sm:grid-cols-3">
              {(['pipeline_latency_ms', 'retrieve_latency_ms', 'llm_latency_ms'] as const).map(
                (key) => {
                  const h = latency[key];
                  if (!h || h.count === 0) return null;
                  const label =
                    key === 'pipeline_latency_ms'
                      ? '索引管道'
                      : key === 'retrieve_latency_ms'
                        ? '检索'
                        : 'LLM 生成';
                  return (
                    <div key={key} className="space-y-2 rounded-md border border-line p-3">
                      <p className="text-sm font-medium text-fg">{label}</p>
                      <div className="space-y-1 text-xs text-muted">
                        <div className="flex justify-between">
                          <span>avg</span>
                          <span className="font-mono text-fg">{h.avg_ms.toFixed(0)} ms</span>
                        </div>
                        <div className="flex justify-between">
                          <span>p50</span>
                          <span className="font-mono text-fg">{h.p50_ms.toFixed(0)} ms</span>
                        </div>
                        <div className="flex justify-between">
                          <span>p95</span>
                          <span className="font-mono text-fg">{h.p95_ms.toFixed(0)} ms</span>
                        </div>
                        <div className="flex justify-between">
                          <span>max</span>
                          <span className="font-mono text-fg">{h.max_ms.toFixed(0)} ms</span>
                        </div>
                      </div>
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
                        <div
                          className="h-full rounded-full bg-accent"
                          style={{
                            width: `${Math.min(100, (h.p95_ms / Math.max(h.max_ms, 1)) * 100)}%`,
                          }}
                        />
                      </div>
                      <p className="text-[10px] text-meta">{h.count} 次采样</p>
                    </div>
                  );
                },
              )}
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  );
}