-- Daily retention purge for Facebook public data (posts/comments 90 days, skip log 30 days).
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
SELECT cron.unschedule(jobid) FROM cron.job WHERE jobname = 'purge-facebook-public-data';
SELECT cron.schedule('purge-facebook-public-data', '17 3 * * *', $$SELECT public.purge_expired_facebook_public_data()$$);
