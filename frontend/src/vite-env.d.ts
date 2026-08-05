/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Backend'i henüz production'a dağıtılmamış Lab modüllerini katalogda gösterir.
   * Geliştirmede (`import.meta.env.DEV`) zaten açıktır; production build'de yalnız bu
   * değişken "1" ise açılır. Bkz. `src/lab/LabApp.tsx`.
   */
  readonly VITE_LAB_UNRELEASED?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
