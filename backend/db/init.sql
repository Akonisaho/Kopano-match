-- Runs once, at first container start (mounted into docker-entrypoint-initdb.d).
-- Three namespaces, one app role. DEV PASSWORD ONLY: rotate for any real environment.
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS sensitive;
CREATE SCHEMA IF NOT EXISTS audit;

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kopano_app') THEN
    CREATE ROLE kopano_app LOGIN PASSWORD 'kopano_app_dev';
  END IF;
END
$$;

GRANT USAGE ON SCHEMA core, sensitive, audit TO kopano_app;
