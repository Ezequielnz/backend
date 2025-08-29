-- =====================================================
-- PRE-MIGRATION PATCH: NOTIFICATIONS + ML SCHEMA
-- =====================================================
-- Fecha: 2025-08-27
-- Objetivo: Alinear esquema existente con expectativas del backend antes de
--           ejecutar el script principal create_notifications_ml_schema.sql
-- Seguridad: 100% idempotente. Solo crea/ajusta si faltan objetos.

-- PASO 0: EXTENSIONES Y TABLA DE LOG
-- =====================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

DO $$
BEGIN
  CREATE TABLE IF NOT EXISTS migration_log (
      id SERIAL PRIMARY KEY,
      migration_name VARCHAR(255) NOT NULL,
      executed_at TIMESTAMP DEFAULT NOW(),
      status VARCHAR(50) DEFAULT 'completed',
      notes TEXT
  );
END $$;

-- PASO 1: PARCHEAR notification_rule_templates (columna is_latest y priority)
-- =====================================================
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_name = 'notification_rule_templates'
  ) THEN
    -- Agregar columna is_latest si falta
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_rule_templates' AND column_name = 'is_latest'
    ) THEN
      EXECUTE 'ALTER TABLE notification_rule_templates ADD COLUMN is_latest BOOLEAN DEFAULT true';
      EXECUTE 'UPDATE notification_rule_templates SET is_latest = true WHERE is_latest IS NULL';
    END IF;

    -- Agregar columna priority si falta
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_rule_templates' AND column_name = 'priority'
    ) THEN
      EXECUTE 'ALTER TABLE notification_rule_templates ADD COLUMN priority VARCHAR(20) DEFAULT ''medium''';
    END IF;

    -- Agregar columna rule_type si falta (mapear desde rule_key si existe)
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_rule_templates' AND column_name = 'rule_type'
    ) THEN
      EXECUTE 'ALTER TABLE notification_rule_templates ADD COLUMN rule_type VARCHAR(100)';
      -- Poblar rule_type desde columnas legacy si existen
      IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'notification_rule_templates' AND column_name = 'rule_key'
      ) THEN
        EXECUTE 'UPDATE notification_rule_templates SET rule_type = COALESCE(rule_key, ''general'') WHERE rule_type IS NULL';
      ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'notification_rule_templates' AND column_name = 'module'
      ) THEN
        EXECUTE 'UPDATE notification_rule_templates SET rule_type = COALESCE(module, ''general'') WHERE rule_type IS NULL';
      ELSE
        EXECUTE 'UPDATE notification_rule_templates SET rule_type = ''general'' WHERE rule_type IS NULL';
      END IF;
      EXECUTE 'ALTER TABLE notification_rule_templates ALTER COLUMN rule_type SET NOT NULL';
    END IF;

    -- Agregar columna version si falta
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_rule_templates' AND column_name = 'version'
    ) THEN
      EXECUTE 'ALTER TABLE notification_rule_templates ADD COLUMN version VARCHAR(20) DEFAULT ''1.0''';
      EXECUTE 'UPDATE notification_rule_templates SET version = ''1.0'' WHERE version IS NULL';
    END IF;

    -- Agregar columna condition_config si falta
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_rule_templates' AND column_name = 'condition_config'
    ) THEN
      EXECUTE 'ALTER TABLE notification_rule_templates ADD COLUMN condition_config JSONB';
      EXECUTE 'UPDATE notification_rule_templates SET condition_config = COALESCE(condition_config, ''{}''::jsonb)';
      EXECUTE 'ALTER TABLE notification_rule_templates ALTER COLUMN condition_config SET DEFAULT ''{}''::jsonb';
      EXECUTE 'ALTER TABLE notification_rule_templates ALTER COLUMN condition_config SET NOT NULL';
    END IF;

    -- Agregar columna default_parameters si falta (mapear desde default_value si existe)
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_rule_templates' AND column_name = 'default_parameters'
    ) THEN
      EXECUTE 'ALTER TABLE notification_rule_templates ADD COLUMN default_parameters JSONB';
      -- Si existe la columna legacy default_value, mapear; si no, setear '{}'
      IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'notification_rule_templates' AND column_name = 'default_value'
      ) THEN
        EXECUTE 'UPDATE notification_rule_templates SET default_parameters = CASE WHEN default_value IS NOT NULL THEN jsonb_build_object(''value'', default_value) ELSE ''{}''::jsonb END WHERE default_parameters IS NULL';
      ELSE
        EXECUTE 'UPDATE notification_rule_templates SET default_parameters = ''{}''::jsonb WHERE default_parameters IS NULL';
      END IF;
      EXECUTE 'ALTER TABLE notification_rule_templates ALTER COLUMN default_parameters SET DEFAULT ''{}''::jsonb';
      EXECUTE 'ALTER TABLE notification_rule_templates ALTER COLUMN default_parameters SET NOT NULL';
    END IF;

    -- Asegurar rubro con DEFAULT y NOT NULL
    IF EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_rule_templates' AND column_name = 'rubro'
    ) THEN
      EXECUTE 'UPDATE notification_rule_templates SET rubro = COALESCE(rubro, ''general'')';
      EXECUTE 'ALTER TABLE notification_rule_templates ALTER COLUMN rubro SET DEFAULT ''general''';
      EXECUTE 'ALTER TABLE notification_rule_templates ALTER COLUMN rubro SET NOT NULL';
    END IF;

    -- Índices: único por (rubro, rule_type, version)
    IF NOT EXISTS (
      SELECT 1 FROM pg_class c 
      JOIN pg_namespace n ON n.oid = c.relnamespace 
      WHERE c.relkind = 'i' AND c.relname = 'ux_notification_rule_templates_rubro_rule_version'
    ) THEN
      EXECUTE 'CREATE UNIQUE INDEX ux_notification_rule_templates_rubro_rule_version ON notification_rule_templates(rubro, rule_type, version)';
    END IF;

    -- Índice parcial para últimos (is_latest=true)
    IF NOT EXISTS (
      SELECT 1 FROM pg_class c 
      JOIN pg_namespace n ON n.oid = c.relnamespace 
      WHERE c.relkind = 'i' AND c.relname = 'idx_notification_rule_templates_rubro_latest'
    ) THEN
      EXECUTE 'CREATE INDEX idx_notification_rule_templates_rubro_latest ON notification_rule_templates(rubro, rule_type) WHERE is_latest = true';
    END IF;
  END IF;
END $$ LANGUAGE plpgsql;

-- PASO 1B: ASEGURAR notification_templates (alinear columnas claves para seeding)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_name = 'notification_templates'
  ) THEN
    -- template_key
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_templates' AND column_name = 'template_key'
    ) THEN
      EXECUTE 'ALTER TABLE notification_templates ADD COLUMN template_key VARCHAR(100)';
      -- mapear desde posibles columnas legacy
      IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'notification_templates' AND column_name = 'key'
      ) THEN
        EXECUTE 'UPDATE notification_templates SET template_key = key WHERE template_key IS NULL';
      ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'notification_templates' AND column_name = 'type'
      ) THEN
        EXECUTE 'UPDATE notification_templates SET template_key = type WHERE template_key IS NULL';
      ELSE
        EXECUTE 'UPDATE notification_templates SET template_key = ''generic'' WHERE template_key IS NULL';
      END IF;
    END IF;

    -- language
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_templates' AND column_name = 'language'
    ) THEN
      EXECUTE 'ALTER TABLE notification_templates ADD COLUMN language VARCHAR(5) DEFAULT ''es''';
    END IF;

    -- channel
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_templates' AND column_name = 'channel'
    ) THEN
      EXECUTE 'ALTER TABLE notification_templates ADD COLUMN channel VARCHAR(20) DEFAULT ''app''';
    END IF;

    -- title_template
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_templates' AND column_name = 'title_template'
    ) THEN
      EXECUTE 'ALTER TABLE notification_templates ADD COLUMN title_template TEXT';
      IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'notification_templates' AND column_name = 'title'
      ) THEN
        EXECUTE 'UPDATE notification_templates SET title_template = title WHERE title_template IS NULL';
      END IF;
    END IF;

    -- message_template
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_templates' AND column_name = 'message_template'
    ) THEN
      EXECUTE 'ALTER TABLE notification_templates ADD COLUMN message_template TEXT';
      IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'notification_templates' AND column_name = 'message'
      ) THEN
        EXECUTE 'UPDATE notification_templates SET message_template = message WHERE message_template IS NULL';
      END IF;
    END IF;

    -- icon
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_templates' AND column_name = 'icon'
    ) THEN
      EXECUTE 'ALTER TABLE notification_templates ADD COLUMN icon VARCHAR(50)';
    END IF;

    -- color
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_templates' AND column_name = 'color'
    ) THEN
      EXECUTE 'ALTER TABLE notification_templates ADD COLUMN color VARCHAR(20)';
    END IF;

    -- priority
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_templates' AND column_name = 'priority'
    ) THEN
      EXECUTE 'ALTER TABLE notification_templates ADD COLUMN priority INTEGER DEFAULT 3';
    END IF;

    -- Columnas legacy: asegurar DEFAULTs para evitar violar NOT NULL al insertar sin especificarlas
    -- module
    IF EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_templates' AND column_name = 'module'
    ) THEN
      EXECUTE 'ALTER TABLE notification_templates ALTER COLUMN module SET DEFAULT ''general''';
      EXECUTE 'UPDATE notification_templates SET module = COALESCE(module, ''general'')';
    END IF;
    -- type
    IF EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_templates' AND column_name = 'type'
    ) THEN
      EXECUTE 'ALTER TABLE notification_templates ALTER COLUMN "type" SET DEFAULT ''general''';
      EXECUTE 'UPDATE notification_templates SET "type" = COALESCE("type", ''general'')';
    END IF;
    -- locale
    IF EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_templates' AND column_name = 'locale'
    ) THEN
      EXECUTE 'ALTER TABLE notification_templates ALTER COLUMN locale SET DEFAULT ''es''';
      EXECUTE 'UPDATE notification_templates SET locale = COALESCE(locale, ''es'')';
    END IF;

    -- template_text (legacy): asegurar DEFAULT y rellenar desde message_template/title_template
    IF EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'notification_templates' AND column_name = 'template_text'
    ) THEN
      EXECUTE 'ALTER TABLE notification_templates ALTER COLUMN template_text SET DEFAULT '''''';';
      EXECUTE 'UPDATE notification_templates SET template_text = COALESCE(template_text, message_template, title_template, '''''')';
    END IF;

    -- Deduplicar por (template_key, language, channel) antes de crear el índice único
    IF EXISTS (
      SELECT 1
      FROM public.notification_templates t
      JOIN (
        SELECT template_key, language, channel
        FROM public.notification_templates
        GROUP BY template_key, language, channel
        HAVING COUNT(*) > 1
      ) d
      ON d.template_key = t.template_key AND d.language = t.language AND d.channel = t.channel
    ) THEN
      -- Construir lista de víctimas manteniendo un canónico por grupo (menor id)
      CREATE TEMP TABLE IF NOT EXISTS tmp_nt_victims AS
      SELECT id,
             FIRST_VALUE(id) OVER (PARTITION BY template_key, language, channel ORDER BY id::text) AS canonical_id,
             ROW_NUMBER() OVER (PARTITION BY template_key, language, channel ORDER BY id::text) AS rn
      FROM public.notification_templates;

      -- Dejar solo las filas duplicadas (rn > 1)
      DELETE FROM tmp_nt_victims WHERE rn = 1;

      -- Si existe la tabla notifications, actualizar referencias al canónico
      IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema='public' AND table_name='notifications'
      ) THEN
        UPDATE public.notifications n
        SET template_id = v.canonical_id
        FROM tmp_nt_victims v
        WHERE n.template_id = v.id;
      END IF;

      -- Eliminar duplicados
      DELETE FROM public.notification_templates t
      USING tmp_nt_victims v
      WHERE t.id = v.id;

      DROP TABLE IF EXISTS tmp_nt_victims;
    END IF;

    -- Índice único para soportar ON CONFLICT (template_key, language, channel)
    IF NOT EXISTS (
      SELECT 1 FROM pg_class c 
      JOIN pg_namespace n ON n.oid = c.relnamespace 
      WHERE c.relkind = 'i' AND c.relname = 'ux_notification_templates_template_lang_channel'
    ) THEN
      EXECUTE 'CREATE UNIQUE INDEX ux_notification_templates_template_lang_channel ON notification_templates(template_key, language, channel)';
    END IF;
  END IF;
END $$ LANGUAGE plpgsql;

-- PASO 2: ASEGURAR business_notification_config (tabla/columna strategy_config)
-- =====================================================
-- Crear tabla si no existe (estructura mínima requerida por backend)
CREATE TABLE IF NOT EXISTS business_notification_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES negocios(id) ON DELETE CASCADE,
    rubro VARCHAR(50) NOT NULL DEFAULT 'general',
    template_version VARCHAR(20) NOT NULL DEFAULT 'latest',
    custom_overrides JSONB DEFAULT '{}'::jsonb,
    strategy_config JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT unique_tenant_config UNIQUE (tenant_id)
);

-- Si existía la tabla pero falta la columna strategy_config, agregarla
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_name = 'business_notification_config'
  ) THEN
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'business_notification_config' AND column_name = 'strategy_config'
    ) THEN
      EXECUTE 'ALTER TABLE business_notification_config ADD COLUMN strategy_config JSONB DEFAULT ''{}''::jsonb';
    END IF;
  END IF;
END $$ LANGUAGE plpgsql;

-- PASO 3: ASEGURAR ml_features (tabla mínima)
-- =====================================================
CREATE TABLE IF NOT EXISTS ml_features (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES negocios(id) ON DELETE CASCADE,
    feature_date DATE NOT NULL,
    feature_type VARCHAR(50) NOT NULL,
    features JSONB NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT unique_tenant_date_type UNIQUE (tenant_id, feature_date, feature_type)
);

-- PASO 4: LOG DE PARCHE
-- =====================================================
INSERT INTO migration_log (migration_name, notes)
VALUES (
  'premigration_patch_notifications_ml',
  'Aplicado parche de pre-migración: agregado is_latest/priority/rule_type/version/condition_config/default_parameters en notification_rule_templates, índices y defaults, strategy_config en business_notification_config y aseguradas tablas business_notification_config y ml_features'
);

-- PASO 5: VALIDACIÓN RÁPIDA
-- =====================================================
SELECT 
  'PRE-PATCH VALIDATION' as status,
  (SELECT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema='public' AND table_name='notification_rule_templates' AND column_name='is_latest'
  )) as has_is_latest,
  (SELECT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema='public' AND table_name='notification_rule_templates' AND column_name='priority'
  )) as has_priority,
  (SELECT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema='public' AND table_name='notification_rule_templates' AND column_name='rule_type'
  )) as has_rule_type,
  (SELECT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema='public' AND table_name='notification_rule_templates' AND column_name='version'
  )) as has_version,
  (SELECT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema='public' AND table_name='notification_rule_templates' AND column_name='condition_config'
  )) as has_condition_config,
  (SELECT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema='public' AND table_name='notification_rule_templates' AND column_name='default_parameters'
  )) as has_default_parameters,
  (SELECT EXISTS (
      SELECT 1 FROM information_schema.tables 
      WHERE table_schema='public' AND table_name='business_notification_config'
  )) as has_business_notification_config,
  (SELECT EXISTS (
      SELECT 1 FROM information_schema.columns 
      WHERE table_schema='public' AND table_name='business_notification_config' AND column_name='strategy_config'
  )) as has_strategy_config,
  (SELECT EXISTS (
      SELECT 1 FROM information_schema.tables 
      WHERE table_schema='public' AND table_name='ml_features'
  )) as has_ml_features;
