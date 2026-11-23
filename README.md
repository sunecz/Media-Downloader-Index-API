# Media Downloader Index API
Simple Python REST API for [Media Downloader Index](https://github.com/sunecz/Media-Downloader-Index).

## Development
Dependencies are managed by [uv](https://docs.astral.sh/uv/) (`pyproject.toml`, locked in `uv.lock`):

	uv sync          # create .venv with the locked dependencies
	uv run pyright   # type check
	uv lock --upgrade-package <name>  # update a dependency

### Database models
`app/db/models.py` is generated from the indexer's Flyway migrations and committed. The script downloads the migrations of the indexer commit pinned in `INDEXER_REF`, applies them to a temporary PostgreSQL container and runs [sqlacodegen](https://github.com/agronholm/sqlacodegen) (requires Docker):

	scripts/generate-models.sh                      # migrations of INDEXER_REF from GitHub
	scripts/generate-models.sh --migrations <dir>   # local migrations, e.g. not pushed yet

Bump `INDEXER_REF` when the API needs a newer schema, and add tables the API starts using to `TABLES`.

## Running the application
You can use the `run.sh` script to run the application. However, it requires a little bit of setup first.

### Docker network
The Docker container is running in an external Docker network `net-mdi`. This network is used by the Media Downloader Index containers, the API connects to the indexer's PostgreSQL container `mdi-db` through it. First, create it (if not already) by running:

	docker network create net-mdi


### Environment variables
The script requires a `.envrc` file with the following environment variables:

	export APP_DATABASE_URL="postgresql+asyncpg://mdi:password@mdi-db:5432/mdi" # SQLAlchemy URL of the indexer's PostgreSQL database (use localhost:$POSTGRES_PORT when running locally)
	export APP_DB_POOL_SIZE=10                 # Number of pooled database connections
	export APP_DB_MAX_OVERFLOW=10              # Extra connections allowed above the pool size under load

	export APP_API_TITLE="MDI API"             # API title in Swagger UI
	export APP_API_VERSION="0.0.1"             # API version in Swagger UI
	export APP_API_DESCRIPTION="MDI REST API"  # API description in Swagger UI
	export APP_BASE_PATH=                      # API base path (e.g. `/api` for `http://my.domain/api`)

	export APP_DEFAULT_PAGE_SIZE=10            # Default page size used for pagination
	export APP_MAX_PAGE_SIZE=100               # Maximum page size used for pagination

	export APP_CACHE_DIR="/cache"              # Main directory for application cache
	export APP_CACHE_HOT_MAX_SIZE=1000         # Maximum number of entries that may be stored in the hot (in-memory) cache
	export APP_CACHE_DISK_MAX_SIZE=10737418240 # Maximum total size of on-disk cache
	export APP_CACHE_FILE_MAX_SIZE=52428800    # Maximum file size in the on-disk cache
	export APP_CACHE_MAX_CONCURRENCY=8         # Maximum number of concurrent uncached computations per worker
	export APP_CACHE_DISK_EVICT_TARGET=0.7     # Optional: when the on-disk cache exceeds its maximum size, the oldest entries are removed down to this fraction of it (default 0.7)

	export APP_PORT=20000                      # Application local port

### Running the script
You can run the script as follows:

	./run.sh COMMAND [ARGS]

where:
- `COMMAND` is one of: `start`, `stop`.
- `ARGS` are optional args passed to the `docker compose` command, e.g. `--build`.

## Cache
Responses are cached in memory (per worker) and on disk in `APP_CACHE_DIR` (shared by all workers). Both are invalidated whenever the indexer bumps the dataset version.

The on-disk cache is safe to use with multiple workers (e.g. `granian --workers N`). The workers coordinate through a small state file and `flock` locks in the cache directory, so it must be on a local volume, not a network filesystem:
- `.state` holds the current dataset version and the total size of the cache,
- `locks/` holds per-key locks, so that a response being computed by one worker is awaited, not computed again, by the others,
- `data/<version>/` holds the entries, the directory of an older version is removed when the version changes.

Always run granian with `--respawn-failed-workers` (the Dockerfile does). Without it, granian shuts down entirely when any worker dies, whatever the number of workers.

Entries are written by a background thread. Eviction scans the cache only when it exceeds `APP_CACHE_DISK_MAX_SIZE`, and then removes the oldest entries down to `APP_CACHE_DISK_EVICT_TARGET` of it.

## API docs
The application exposes Swagger UI docs for the REST API. By default it is available at `/docs`.
