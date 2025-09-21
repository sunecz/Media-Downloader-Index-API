# Media Downloader Index API
Simple Python REST API for [Media Downloader Index](https://github.com/sunecz/Media-Downloader-Index).

## Running the application
You can use the `run.sh` script to run the application. However, it requires a little bit of setup first.

### Docker network
The Docker container is running in an external Docker network `net-mdi`. This network is used by the Media Downloader Index containers. First, create it (if not already) by running:

	docker network create net-mdi


### Environment variables
The script requires a `.envrc` file with the following environment variables:

	export APP_DATABASE_URL="http://mdi-db:3030/mdi" # DB URI used by the API

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
	export APP_CACHE_MAX_CONCURRENCY=8         # Maximum number of concurrent write async operations

	export APP_PORT=20000                      # Application local port

### Running the script
You can run the script as follows:

	./run.sh COMMAND [ARGS]

where:
- `COMMAND` is one of: `start`, `stop`.
- `ARGS` are optional args passed to the `docker compose` command, e.g. `--build`.

## API docs
The application exposes Swagger UI docs for the REST API. By default it is available at `/docs`.
