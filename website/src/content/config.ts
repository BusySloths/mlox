import { defineCollection, z } from 'astro:content';

const contentCollection = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    subtitle: z.string().optional(),
    description: z.string().optional(),
    cta_primary: z.string().optional(),
    cta_primary_link: z.string().optional(),
    cta_secondary: z.string().optional(),
    cta_secondary_link: z.string().optional(),
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
    steps: z.array(z.object({
      title: z.string(),
      description: z.string(),
      code: z.string().optional(),
      note: z.string().optional(),
    })).optional(),
  }),
});

export const collections = {
  'pages': contentCollection,
};
