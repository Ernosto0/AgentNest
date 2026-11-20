-- Runs once, when the data volume is first initialised.
-- If the volume already exists, create the database manually:
--   docker compose exec postgres psql -U pivoris -c "CREATE DATABASE pivoris_test OWNER pivoris;"
CREATE DATABASE pivoris_test OWNER pivoris;
