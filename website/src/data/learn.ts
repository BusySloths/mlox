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
  /** Teaser shown when the entry is featured on the home page. */
  signal: {
    label: string;
    from?: string;
    value: string;
    state: string;
    note: string;
    tone: 'ok' | 'alert';
  };
}

export const learnEntries: LearnEntry[] = [
  {
    slug: 'first-steps',
    kind: 'tutorial',
    title: 'Your first project, five minutes from now',
    summary:
      'Install MLOX, create a project, let it launch an Ubuntu VM with Docker on your laptop and run a first app on it, all from the terminal UI. Recorded on a real machine, with the time for every step.',
    minutes: 5,
    tags: ['Getting started', 'Multipass', 'Docker', 'App catalog'],
    signal: { label: 'install → app in the browser', value: '4 min 13 s', state: 'RUNNING', note: 'one project, one VM, one app', tone: 'ok' },
  },
  {
    slug: 'operations-demo',
    kind: 'demo',
    title: 'Catching a silent model failure, live',
    summary:
      'A model on Kubernetes starts giving wrong answers without a single error. Watch MLOX discover the pipeline from telemetry, flag the broken step and let a reasoning model explain the cause and propose a fix.',
    minutes: 8,
    tags: ['Operations', 'MLflow Gateway', 'OpenTelemetry', 'InfluxDB', 'OpenBao'],
    experimental: true,
    signal: { label: 'pca.transform', from: '2.79', value: '14.55', state: 'ANOMALOUS', note: 'likely origin found in seconds', tone: 'alert' },
  },
];
