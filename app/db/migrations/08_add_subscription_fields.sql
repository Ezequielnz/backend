-- Add subscription fields to usuarios table

ALTER TABLE public.usuarios 
ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'trial',
ADD COLUMN IF NOT EXISTS trial_end TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS is_exempt BOOLEAN DEFAULT FALSE;

-- Update existing users to have a trial_end in the future (optional, or set to expired)
-- For now, let's give existing users a fresh trial or leave them null (which might need handling)
-- Let's set existing users to have a trial starting now for 30 days so they aren't locked out immediately
UPDATE public.usuarios 
SET trial_end = NOW() + INTERVAL '30 days', subscription_status = 'trial'
WHERE trial_end IS NULL;

-- Create an index for performance
CREATE INDEX IF NOT EXISTS idx_usuarios_subscription_status ON public.usuarios(subscription_status);
CREATE INDEX IF NOT EXISTS idx_usuarios_trial_end ON public.usuarios(trial_end);
