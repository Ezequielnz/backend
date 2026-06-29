-- Set default value for trial_end in usuarios table to (now() + interval '30 days')
ALTER TABLE public.usuarios 
ALTER COLUMN trial_end SET DEFAULT (now() + interval '30 days');
