-- Runs once, when the data volume is first initialised.
-- If the volume already exists, create the database manually:
--   docker compose exec postgres psql -U agentnest -c "CREATE DATABASE agentnest_test OWNER agentnest;"
CREATE DATABASE agentnest_test OWNER agentnest;
