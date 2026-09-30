-- Store the exact search page URL each crawl query opened (audit + reproducibility).
ALTER TABLE public.crawl_queries ADD COLUMN IF NOT EXISTS search_url text;
