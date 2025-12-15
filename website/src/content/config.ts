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
  }),
});

export const collections = {
  'pages': contentCollection,
};
