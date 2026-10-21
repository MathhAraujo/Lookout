-- Create the Infisical database only on fresh PostgreSQL volumes.
SELECT 'CREATE DATABASE infisical'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'infisical')\gexec
