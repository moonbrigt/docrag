import { useState } from 'react';
import { AlertTriangle, Play } from 'lucide-react';
import { runEvaluation } from '@/api/evaluation';
import { ApiError, extractErrorMessage } from '@/api/client';
import type { EvaluationReport } from '@/types/api';
import { cn } from '@/lib/cn';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card';
import { EvaluationReportView } from '@/components/common/EvaluationReport';

type Profile = 'public_nist' | 'synthetic_smoke';

const PROFILES: { id: Profile; title: string; description: string }[] = [
  {
    id: 'public_nist',
    title: 'public_nist',
    description: 'NIST AI 100-1 / 600-1 公开 PDF 语料评测（18 题，需先运行 scripts/evaluation/prepare.sh）',
  },
  {
    id: 'synthetic_smoke',
    title: 'synthetic_smoke',
    description: '内置 22 条中英问答冒烟集（离线可复现，覆盖 exact / set / numeric / unanswerable）',
  },
];

export function Evaluation() {
  const [profile, setProfile] = useState<Profile>('public_nist');
  const [report, setReport] = useState<EvaluationReport | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<{ message: string; notPrepared: boolean } | null>(null);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      const r = await runEvaluation({ profile });
      setReport(r);
    } catch (e) {
      const notPrepared = e instanceof ApiError && e.status === 409;
      setError({
        message: extractErrorMessage(e, '评测运行失败'),
        notPrepared,
      });
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-[var(--container-max)] space-y-6 px-4 py-6 md:px-6">
      <div>
        <h1 className="text-2xl font-announce text-fg">评测看板</h1>
        <p className="mt-1 text-sm text-muted">
          对固定评测集运行 RAG 流水线，量化引用准确率与召回质量；真实语料链路状态以 VERIFIED / NOT_RUN 标注。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>运行评测</CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <div role="radiogroup" aria-label="评测 profile" className="grid gap-3 sm:grid-cols-2">
            {PROFILES.map((p) => {
              const active = profile === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => setProfile(p.id)}
                  className={cn(
                    'rounded-md border p-3 text-left transition-colors focus-visible:outline-none',
                    active
                      ? 'border-accent bg-accent/10'
                      : 'border-line bg-surface hover:bg-surface-2',
                  )}
                >
                  <span className={cn('font-mono text-sm', active ? 'text-accent' : 'text-fg')}>
                    {p.title}
                  </span>
                  <span className="mt-1 block text-xs text-muted">{p.description}</span>
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-3">
            <Button onClick={run} loading={running} leadingIcon={<Play size={16} />}>
              运行评测
            </Button>
            <span className="text-xs text-meta">
              当前：{PROFILES.find((p) => p.id === profile)?.title}
            </span>
          </div>

          {error && (
            <div
              role="alert"
              className={cn(
                'rounded-md border p-3 text-sm',
                error.notPrepared
                  ? 'border-warn/40 bg-warn/5 text-warn'
                  : 'border-danger/40 bg-danger/5 text-danger',
              )}
            >
              <p className="flex items-center gap-2">
                <AlertTriangle size={16} className="shrink-0" aria-hidden />
                {error.message}
              </p>
              {error.notPrepared && (
                <p className="mt-1 pl-6 text-xs">
                  语料未就绪：请先在仓库根目录运行{' '}
                  <code className="rounded-sm bg-surface-2 px-1 font-mono">scripts/evaluation/prepare.sh</code>{' '}
                  下载并准备 NIST PDF 语料，然后重新运行评测。
                </p>
              )}
            </div>
          )}
        </CardBody>
      </Card>

      {report && <EvaluationReportView report={report} />}
    </div>
  );
}
