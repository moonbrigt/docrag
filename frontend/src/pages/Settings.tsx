import { useEffect, useState } from 'react';
import { Cpu, Gauge, KeyRound, RefreshCw, Save } from 'lucide-react';
import { getRuntimeConfig, updateRuntimeConfig } from '@/api/config';
import { useBackends } from '@/hooks/useSystem';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import type { AcceleratorMode } from '@/types/api';

// 设置页：模型 API 运行时配置（写回后端，即时生效，无需改 env / 重建镜像）。
// embedding / rerank / 解析后端仍由后端环境变量决定，此处只读展示就绪状态。
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
      });
      setApiKey(''); // 清空输入框，避免明文驻留
      setApiKeySet(cfg.llm.api_key_set);
      setDevice(cfg.device ?? '');
      setCudaAvailable(!!cfg.cuda_available);
      setMessage({
        tone: 'ok',
        text: `已保存并即时生效：LLM 后端 = ${cfg.llm.backend}（模型 ${cfg.llm.model || '未设置'}）· 计算设备 = ${cfg.device || '自动'}`,
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
          <CardTitle>解析 / 嵌入 / 重排后端（只读）</CardTitle>
        </CardHeader>
        <CardBody className="space-y-2 text-sm">
          <p className="text-muted">
            这三类后端当前由部署环境变量（RAG_PARSE_BACKEND / RAG_EMBED_BACKEND / RAG_RERANK_BACKEND）决定，
            设置页暂不支持运行时切换；真实模型权重（Docling / bge-m3 / bge-reranker）需另行安装，见 docs/DEPLOYMENT.md。
          </p>
          {backends ? (
            <dl className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {(
                [
                  ['嵌入', backends.embedding],
                  ['重排', backends.rerank],
                  ['解析（经由健康接口）', undefined],
                ] as const
              ).map(([label, item]) => (
                <div key={label} className="rounded-md border border-line bg-surface px-3 py-2">
                  <dt className="text-xs text-meta">{label}</dt>
                  <dd className="mt-0.5 font-mono text-fg">
                    {item ? `${item.backend} · ${item.ready ? '就绪' : '未就绪'}` : '—'}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-muted">状态加载中…</p>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
