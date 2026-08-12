import { CheckCircle2, XCircle } from 'lucide-react';
import type { EvaluationMetrics, EvaluationReport } from '@/types/api';
import { formatPercent } from '@/lib/format';
import { Badge } from '@/components/ui/Badge';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card';
import { cn } from '@/lib/cn';

// 评测报告：概览指标卡（兼容 public_nist 扁平键 与 synthetic_smoke 字典键）
// + 检索消融对比 + provenance + per-query 明细表
const num = (m: EvaluationMetrics, flat?: string, dict?: string, k?: number) => {
  const v = flat ? (m as unknown as Record<string, unknown>)[flat] : undefined;
  if (typeof v === 'number') return v;
  if (dict && k != null) {
    const d = (m as unknown as Record<string, unknown>)[dict];
    if (d && typeof d === 'object' && k in (d as Record<string, unknown>)) {
      const dv = (d as Record<string, number>)[k];
      if (typeof dv === 'number') return dv;
    }
  }
  return 0;
};

const ABLATION_ROWS = [
  ['recall@1', '召回@1'],
  ['recall@5', '召回@5'],
  ['mrr', 'MRR'],
  ['ndcg@5', 'nDCG@5'],
  ['citation_recall', '引用召回'],
  ['citation_page_precision', '引用页精度'],
  ['answer_em', '答案 EM'],
  ['answer_f1', '答案 F1'],
] as const;

export function EvaluationReportView({ report }: { report: EvaluationReport }) {
  const m = report.metrics;
  const isPublic = Boolean(num(m, 'recall@5', undefined));
  const overview = isPublic
    ? [
        { key: 'recall@1', label: '召回@1', value: num(m, 'recall@1') },
        { key: 'recall@5', label: '召回@5', value: num(m, 'recall@5') },
        { key: 'mrr', label: 'MRR', value: num(m, 'mrr') },
        { key: 'ndcg@5', label: 'nDCG@5', value: num(m, 'ndcg@5') },
        { key: 'citation_recall', label: '引用召回', value: num(m, 'citation_recall') },
        { key: 'citation_page_precision', label: '引用页精度', value: num(m, 'citation_page_precision') },
        { key: 'answer_em', label: '答案 EM', value: num(m, 'answer_em') },
        { key: 'answer_f1', label: '答案 F1', value: num(m, 'answer_f1') },
      ]
    : [
        { key: 'citation_accuracy', label: '引用准确率', value: m.citation_accuracy ?? 0 },
        { key: 'recall@5', label: '召回@5', value: num(m, undefined, 'recall_at_k', 5) },
        { key: 'recall@10', label: '召回@10', value: num(m, undefined, 'recall_at_k', 10) },
        { key: 'hit@5', label: '命中率@5', value: num(m, undefined, 'hit_rate_at_k', 5) },
        { key: 'hit@10', label: '命中率@10', value: num(m, undefined, 'hit_rate_at_k', 10) },
        { key: 'mrr', label: 'MRR', value: m.mrr ?? 0 },
      ];
  const ablation = (m as unknown as Record<string, unknown>).ablation as
    | Record<string, { name?: string; metrics: Record<string, number> }>
    | undefined;
  const eligible = num(m, 'eligible', undefined);
  const total = num(m, 'total', undefined);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>概览</CardTitle>
          <span className="text-xs text-meta">
            {isPublic && total > 0 ? `${eligible}/${total} 题可判分` : `${m.num_queries ?? 0} 条问答`}
            {m.embedding_backend ? ` · 嵌入后端 ${m.embedding_backend}` : ''}
          </span>
        </CardHeader>
        <CardBody className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {overview.map((x) => (
              <div key={x.key} className="rounded-md border border-line bg-surface px-3 py-3">
                <p className="text-xs text-meta">{x.label}</p>
                <p className="mt-1 font-mono text-xl text-fg">{formatPercent(x.value)}</p>
                {ciText(x.key, m) && (
                  <p className="mt-0.5 font-mono text-[10px] text-meta">{ciText(x.key, m)}</p>
                )}
              </div>
            ))}
          </div>
          <ProvenanceLine provenance={report.metrics?.provenance ?? report.provenance} />
        </CardBody>
      </Card>

      {ablation && Object.keys(ablation).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>检索消融对比</CardTitle>
            <span className="text-xs text-meta">同一指标口径，四路检索变体（mock 稠密为确定性嵌入）</span>
          </CardHeader>
          <CardBody className="p-0">
            <div className="overflow-auto">
              <table className="w-full min-w-[720px] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs text-meta">
                    <th className="px-3 py-2 font-normal">变体</th>
                    {ABLATION_ROWS.map(([k, label]) => (
                      <th key={k} className="px-2 py-2 text-right font-normal">{label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(ablation).map(([variant, d]) => (
                    <tr key={variant} className="border-b border-line/60 last:border-0">
                      <td className="px-3 py-2 font-mono text-xs text-fg" title={d.name}>
                        {variant}
                      </td>
                      {ABLATION_ROWS.map(([k]) => (
                        <td key={k} className="px-2 py-2 text-right font-mono text-xs text-fg">
                          {formatPercent(d.metrics?.[k] ?? 0)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>
      )}

      {report.per_query && report.per_query.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>逐条明细</CardTitle>
          </CardHeader>
          <CardBody className="p-0">
            <div className="max-h-[520px] overflow-auto">
              <table className="w-full min-w-[860px] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs text-meta">
                    <th className="px-3 py-2 font-normal">ID</th>
                    <th className="px-3 py-2 font-normal">问题</th>
                    <th className="px-2 py-2 font-normal">类型</th>
                    <th className="px-2 py-2 text-right font-normal">召回@5</th>
                    <th className="px-2 py-2 text-right font-normal">MRR</th>
                    <th className="px-2 py-2 text-right font-normal">答案</th>
                    <th className="px-3 py-2 font-normal">引用</th>
                  </tr>
                </thead>
                <tbody>
                  {report.per_query.map((q) => {
                    const r5 = num(m, undefined, undefined) ? (q as unknown as Record<string, unknown>)['recall@5'] : undefined;
                    const recall = typeof r5 === 'number' ? r5 : undefined;
                    const mrr = (q as unknown as Record<string, unknown>)['mrr'];
                    const answerScore = (q as unknown as Record<string, unknown>)['answer_score'];
                    const hasAnswer =
                      typeof answerScore === 'number'
                        ? answerScore > 0
                        : (q as unknown as Record<string, unknown>).hit === true;
                    const qText =
                      (q as unknown as Record<string, unknown>).query ??
                      (q as unknown as Record<string, unknown>).question ??
                      (q as unknown as Record<string, unknown>).id;
                    return (
                      <tr key={q.id} className="border-b border-line/60 last:border-0 align-top">
                        <td className="px-3 py-2 font-mono text-xs text-fg">{q.id}</td>
                        <td className="max-w-[260px] px-3 py-2 text-xs text-fg">
                          <p className="line-clamp-2">{String(qText ?? '')}</p>
                        </td>
                        <td className="px-2 py-2 text-xs text-muted">
                          {String((q as unknown as Record<string, unknown>).answer_type ?? '') || '—'}
                        </td>
                        <td className="px-2 py-2 text-right font-mono text-xs text-fg">
                          {recall != null ? formatPercent(recall) : '—'}
                        </td>
                        <td className="px-2 py-2 text-right font-mono text-xs text-fg">
                          {typeof mrr === 'number' ? formatPercent(mrr) : '—'}
                        </td>
                        <td className="px-2 py-2 text-right">
                          <Badge tone={hasAnswer ? 'success' : 'neutral'}>
                            {hasAnswer ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                            {hasAnswer ? '命中' : '未中'}
                          </Badge>
                        </td>
                        <td className="px-3 py-2 text-xs text-muted">
                          {Array.isArray((q as unknown as Record<string, unknown>).citations)
                            ? `${(q.citations as unknown[]).length} 条`
                            : '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

/** 置信区间文本：metrics.ci[metric] -> "95% CI [low, high]" */
function ciText(key: string, m: EvaluationMetrics): string | null {
  const ci = m.ci as Record<string, unknown> | undefined;
  if (!ci) return null;
  const v = ci[key] ?? ci[`recall@${key.replace('recall@', '')}`];
  if (!v || typeof v !== 'object') return null;
  const rec = v as { low?: unknown; high?: unknown };
  const arr = Array.isArray(v) ? v : [rec.low, rec.high];
  if (arr.length < 2 || typeof arr[0] !== 'number' || typeof arr[1] !== 'number') return null;
  return `95% CI [${formatPercent(arr[0])}, ${formatPercent(arr[1])}]`;
}

/** 链路验证状态：单字符串或 {component: 'VERIFIED'|'NOT_RUN'} 映射 */
function ProvenanceLine({ provenance }: { provenance?: string | Record<string, string> }) {
  if (provenance == null) return null;
  const entries =
    typeof provenance === 'string' ? [['pipeline', provenance]] : Object.entries(provenance);
  if (entries.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      {entries.map(([k, v]) => (
        <span key={k} className="inline-flex items-center gap-1 rounded-sm bg-surface-2 px-2 py-1 font-mono text-meta">
          {k}
          <span className={cn(v === 'VERIFIED' ? 'text-success' : 'text-meta')}>{v}</span>
        </span>
      ))}
    </div>
  );
}
