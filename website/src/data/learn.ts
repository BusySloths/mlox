// Tutorials & demos: one entry per piece, newest first. Pages live in src/pages/learn/.

export type LearnKind = 'tutorial' | 'demo';

export interface LearnEntry {
  slug: string;
  kind: LearnKind;
  title: string;
  summary: string;
  minutes: number;
  tags: string[];
  experimental?: boolean;
}

export const learnEntries: LearnEntry[] = [
  {
    slug: 'operations-demo',
    kind: 'demo',
    title: 'Catching a silent model failure, live',
    summary:
      'A model on Kubernetes starts giving wrong answers without a single error. Watch MLOX discover the pipeline from telemetry, flag the broken step and let a reasoning model explain the cause and propose a fix.',
    minutes: 8,
    tags: ['Operations', 'MLflow Gateway', 'OpenTelemetry', 'InfluxDB', 'OpenBao'],
    experimental: true,
  },
];
