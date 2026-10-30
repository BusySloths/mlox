import { defineCollection, z } from 'astro:content';

const contentCollection = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    eyebrow: z.string().optional(),
    subtitle: z.string().optional(),
    description: z.string().optional(),
    cta_primary: z.string().optional(),
    cta_primary_link: z.string().optional(),
    cta_secondary: z.string().optional(),
    cta_secondary_link: z.string().optional(),
    install: z.string().optional(),
    stats: z.array(z.object({
      value: z.string(),
      label: z.string(),
    })).optional(),
    cards: z.array(z.object({
      title: z.string(),
      icon: z.string(),
      description: z.string(),
    })).optional(),
    features: z.array(z.object({
      title: z.string(),
      icon: z.string(),
      color: z.string(),
      description: z.string().optional(),
      items: z.array(z.string()),
    })).optional(),
    services: z.array(z.string()).optional(),
    steps: z.array(z.object({
      title: z.string(),
      description: z.string(),
      code: z.string().optional(),
      note: z.string().optional(),
      image: z.string().optional(),
      alt: z.string().optional(),
    })).optional(),
    shots: z.array(z.object({
      id: z.string(),
      label: z.string(),
      title: z.string(),
      description: z.string(),
      image: z.string(),
      alt: z.string(),
    })).optional(),
  }),
});

export const collections = {
  'pages': contentCollection,
};
