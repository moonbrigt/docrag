import * as pdfjsLib from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

// =============================================================================
// pdfjs-dist v6 配置（SPEC §11 内嵌已知坑：必须配置 worker）
// - 经 ?url 引入 worker，避免 v4+ "Setting up fake worker" 警告与崩溃。
// - 旧 bundler 若缺失 Promise.withResolvers（pdfjs 内部依赖），补 polyfill。
// =============================================================================

type WithResolvers<T> = {
  promise: Promise<T>;
  resolve: (value: T | PromiseLike<T>) => void;
  reject: (reason?: unknown) => void;
};

if (typeof (Promise as unknown as { withResolvers?: unknown }).withResolvers !== 'function') {
  (Promise as unknown as { withResolvers: <T>() => WithResolvers<T> }).withResolvers =
    function <T>() {
      let resolve!: (value: T | PromiseLike<T>) => void;
      let reject!: (reason?: unknown) => void;
      const promise = new Promise<T>((res, rej) => {
        resolve = res;
        reject = rej;
      });
      return { promise, resolve, reject };
    };
}

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

export { pdfjsLib };
