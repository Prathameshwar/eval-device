\set ON_ERROR_STOP on
-- psql 17 ignores an exit-code argument to \quit; SQL exceptions fail preflight reliably.
\if :{?db_name}
\else
  DO $preflight$ BEGIN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Supply -v db_name=device_platform and connect to the postgres maintenance database.';
  END $preflight$;
\endif
-- Run separately from install.sql: CREATE DATABASE cannot run in a transaction.
-- The connected deployment role becomes database owner; no passwords are seeded.
CREATE DATABASE :"db_name" TEMPLATE template0 ENCODING 'UTF8';
ALTER DATABASE :"db_name" SET timezone TO 'UTC';
REVOKE ALL ON DATABASE :"db_name" FROM PUBLIC;
