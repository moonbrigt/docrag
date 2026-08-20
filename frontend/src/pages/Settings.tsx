import { useEffect, useState } from 'react';
import { Cpu, Gauge, KeyRound, RefreshCw, Save } from 'lucide-react';
import { getRuntimeConfig, updateRuntimeConfig } from '@/api/config';
import { useBackends } from '@/hooks/useSystem';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import type {
  AcceleratorMode,
  EmbedBackend,
  ParseBackend,
  RerankBackend,
} from '@/types/api';

// 设置页：模型 API / 解析 / 嵌入 / 重排运行时配置（写回后端，即时生效，无需改 env / 重建镜像）。
const BACKEND_OPTIONS = [
  { value: 'mock', label: 'Mock（离线演示）' },
  { value: 'ollama', label: 'Ollama（本地）' },
  { value: 'openai', label: 'OpenAI 兼容 API' },
] as const;

const ACCELERATOR_OPTIONS = [
  { value: 'auto', label: '自动（有 GPU 则用，否则 CPU）' },
  { value: 'cuda', label: 'GPU（CUDA）' },
  { value: 'cpu', label: '仅 CPU' },
] as const;

const EMBED_OPTIONS = [
  { value: 'bge-m3', label: 'bge-m3（本地模型）' },
  { value: 'mock', label: 'Mock（离线演示）' },
] as const;

const RERANK_OPTIONS = [
  { value: 'bge-reranker-v2-m3', label: 'bge-reranker-v2-m3（本地模型）' },
  { value: 'mock', label: 'Mock（离线演示）' },
] as const;

const PARSE_OPTIONS = [
  { value: 'docling', label: 'Docling（本地解析）' },
  { value: 'mock', label: 'Mock（离线演示）' },
] as const;

// 回显后端：mock 不拼模型名（mock 并不加载真实模型），避免"mock 挂着真模型"歧义
function fmtBackend(backend: string, model: string): string {
  return backend === 'mock' ? backend : `${backend}(${model || '默认'})`;
}

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
  const { data: backends, refetch: refetchBackends } = useBackends();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);
  const [backend, setBackend] = useState<'mock' | 'ollama' | 'openai'>('mock');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [apiKeySet, setApiKeySet] = useState(false);
  const [accelerator, setAccelerator] = useState<AcceleratorMode>('auto');
  const [device, setDevice] = useState('');
  const [cudaAvailable, setCudaAvailable] = useState(false);
  const [embedBackend, setEmbedBackend] = useState<EmbedBackend>('bge-m3');
  const [embedModel, setEmbedModel] = useState('');
  const [rerankBackend, setRerankBackend] = useState<RerankBackend>('bge-reranker-v2-m3');
  const [rerankModel, setRerankModel] = useState('');
  const [parseBackend, setParseBackend] = useState<ParseBackend>('docling');

  useEffect(() => {
    getRuntimeConfig()
      .then((cfg) => {
        setBackend(cfg.llm.backend);
        setBaseUrl(cfg.llm.base_url);
        setModel(cfg.llm.model);
        setApiKeySet(cfg.llm.api_key_set);
        setAccelerator(cfg.accelerator ?? 'auto');
        setDevice(cfg.device ?? '');
        setCudaAvailable(!!cfg.cuda_available);
        setEmbedBackend(cfg.embed?.backend ?? 'bge-m3');
        setEmbedModel(cfg.embed?.model ?? '');
        setRerankBackend(cfg.rerank?.backend ?? 'bge-reranker-v2-m3');
        setRerankModel(cfg.rerank?.model ?? '');
        setParseBackend(cfg.parse?.backend ?? 'docling');
      })
      .catch(() => setMessage({ tone: 'err', text: '读取当前配置失败，请刷新重试' }))
      .finally(() => setLoading(false));
  }, []);

  const onSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const cfg = await updateRuntimeConfig({
        llm: {
          backend,
          base_url: baseUrl,
          model,
          api_key: apiKey, // 空串 = 清除已存密钥
          accelerator,
        },
        embed: { backend: embedBackend, model: embedModel },
        rerank: { backend: rerankBackend, model: rerankModel },
        parse: { backend: parseBackend },
      });
      setApiKey(''); // 清空输入框，避免明文驻留
      setApiKeySet(cfg.llm.api_key_set);
      setDevice(cfg.device ?? '');
      setCudaAvailable(!!cfg.cuda_available);
      setMessage({
        tone: 'ok',
        text: `已保存并即时生效：LLM=${fmtBackend(cfg.llm.backend, cfg.llm.model)} · 嵌入=${fmtBackend(cfg.embed.backend, cfg.embed.model)} · 重排=${fmtBackend(cfg.rerank.backend, cfg.rerank.model)} · 解析=${cfg.parse.backend} · 设备=${cfg.device || '自动'}`,
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

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <Cpu size={18} className="text-accent" />
            模型 API
          </CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          {loading ? (
            <p className="text-sm text-muted">加载中…</p>
          ) : (
            <>
              <div className="space-y-1.5">
                <label htmlFor="llm-backend" className="text-sm text-muted">
                  LLM 后端
                </label>
                <Select
                  id="llm-backend"
                  value={backend}
                  onChange={(v) => setBackend(v as typeof backend)}
                  options={BACKEND_OPTIONS}
                />
              </div>

              <div className="space-y-1.5">
                <label htmlFor="llm-base-url" className="text-sm text-muted">
                  Base URL
                </label>
                <Input
                  id="llm-base-url"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder={backend === 'ollama' ? 'http://localhost:11434/v1' : 'https://api.openai.com/v1'}
                  autoComplete="off"
                />
                <p className="text-xs text-meta">
                  Ollama 默认 {backends?.llm.backend === 'ollama' ? '已使用' : 'http://localhost:11434/v1'}；
                  留空则使用后端环境变量默认值
                </p>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="llm-model" className="text-sm text-muted">
                  模型名
                </label>
                <Input
                  id="llm-model"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="如 llama3.1:8b / gpt-4o-mini"
                  autoComplete="off"
                />
              </div>

              <div className="space-y-1.5">
                <label htmlFor="llm-api-key" className="flex items-center gap-1.5 text-sm text-muted">
                  <KeyRound size={14} />
                  API Key
                  {apiKeySet && (
                    <span className="rounded-sm bg-success/10 px-1.5 py-0.5 text-xs text-success">
                      已设置（输入新值覆盖，留空保存则清除）
                    </span>
                  )}
                </label>
                <Input
                  id="llm-api-key"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={apiKeySet ? '••••••••（已保存，不回显）' : 'sk-…'}
                  autoComplete="off"
                />
                <p className="text-xs text-meta">仅 Ollama 模式不需要；存储于本地 SQLite，接口不回显明文</p>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="llm-accelerator" className="flex items-center gap-1.5 text-sm text-muted">
                  <Gauge size={14} />
                  计算加速（嵌入 / 重排）
                </label>
                <Select
                  id="llm-accelerator"
                  value={accelerator}
                  onChange={(v) => setAccelerator(v as AcceleratorMode)}
                  options={ACCELERATOR_OPTIONS}
                />
                <p className="text-xs text-meta">
                  {cudaAvailable
                    ? `当前生效设备：${device === 'cuda' ? 'GPU（CUDA，FP16）' : 'CPU（FP32）'}。切换后模型热重载，立即生效。`
                    : '当前环境未检测到 CUDA，将使用 CPU（FP32）计算。'}
                </p>
              </div>

              <div className="flex items-center gap-3">
                <Button onClick={onSave} disabled={saving}>
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
                  className={`text-sm ${message.tone === 'err' ? 'text-danger' : 'text-success'}`}
                >
                  {message.text}
                </p>
              )}
            </>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <Gauge size={18} className="text-accent" />
            解析 / 嵌入 / 重排
          </CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <p className="text-xs text-meta">
            运行时覆盖生效（持久化到本地 SQLite），无需改 env 或重建镜像；留空模型名则用后端环境变量默认。
          </p>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <label htmlFor="embed-backend" className="text-sm text-muted">
                嵌入后端
              </label>
              <Select
                id="embed-backend"
                value={embedBackend}
                onChange={(v) => setEmbedBackend(v as EmbedBackend)}
                options={EMBED_OPTIONS}
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="rerank-backend" className="text-sm text-muted">
                重排后端
              </label>
              <Select
                id="rerank-backend"
                value={rerankBackend}
                onChange={(v) => setRerankBackend(v as RerankBackend)}
                options={RERANK_OPTIONS}
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="parse-backend" className="text-sm text-muted">
                解析后端
              </label>
              <Select
                id="parse-backend"
                value={parseBackend}
                onChange={(v) => setParseBackend(v as ParseBackend)}
                options={PARSE_OPTIONS}
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="embed-model" className="text-sm text-muted">
                嵌入模型名
              </label>
              {embedBackend === 'mock' ? (
                <p className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-meta">
                  — Mock 下不适用 —
                </p>
              ) : (
                <Input
                  id="embed-model"
                  value={embedModel}
                  onChange={(e) => setEmbedModel(e.target.value)}
                  placeholder="如 BAAI/bge-m3"
                  autoComplete="off"
                />
              )}
            </div>
            <div className="space-y-1.5">
              <label htmlFor="rerank-model" className="text-sm text-muted">
                重排模型名
              </label>
              {rerankBackend === 'mock' ? (
                <p className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-meta">
                  — Mock 下不适用 —
                </p>
              ) : (
                <Input
                  id="rerank-model"
                  value={rerankModel}
                  onChange={(e) => setRerankModel(e.target.value)}
                  placeholder="如 BAAI/bge-reranker-v2-m3"
                  autoComplete="off"
                />
              )}
            </div>
          </div>

          {embedBackend !== 'mock' && (
            <p className="text-xs text-meta">
              切换嵌入模型后，既有文档向量仍在旧模型空间，需重新上传以正确检索；新上传文档即时用新模型。
            </p>
          )}

          <div className="flex items-center gap-3">
            <Button onClick={onSave} disabled={saving}>
              <Save size={16} />
              {saving ? '保存中…' : '保存并生效'}
            </Button>
            <Button variant="ghost" onClick={() => refetchBackends()} type="button">
              <RefreshCw size={16} />
              刷新状态
            </Button>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
