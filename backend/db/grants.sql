-- Applied by seed.py AFTER the tables exist, as the admin role.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core TO kopano_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA sensitive TO kopano_app;

-- The application can add to its audit trail and read it. It can never rewrite it.
GRANT INSERT, SELECT ON audit.audit_logs TO kopano_app;
REVOKE UPDATE, DELETE ON audit.audit_logs FROM kopano_app;

-- POPIA erasure: anonymise rather than delete, so audit rows survive.
CREATE OR REPLACE FUNCTION core.anonymise_user(uid uuid) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = core, pg_temp AS $$
  UPDATE core.users
     SET full_name = 'Anonymised user',
         email = 'anonymised-' || uid::text || '@invalid',
         phone = NULL,
         password_hash = '!',
         deleted_at = now()
   WHERE id = uid;
$$;
REVOKE ALL ON FUNCTION core.anonymise_user(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION core.anonymise_user(uuid) TO kopano_app;
