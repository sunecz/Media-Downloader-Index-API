#!/usr/bin/env bash

usage() {
	printf 'Usage: %s <command> [<args>]\n' "$0"
	printf '  command: start, stop\n'
}

# Constant files
FILES=(
	-f docker-compose.yml
)

RUN_COMMAND="$1"
RUN_ARGS=()

case "$RUN_COMMAND" in
	start)
		RUN_ARGS+=(up)
		;;
	stop)
		RUN_ARGS+=(down)
		;;
	*)
		printf 'Invalid command: %s\n' "$RUN_COMMAND"
		usage
		exit 1
		;;
esac

printf 'Args: %s\n' "${RUN_ARGS[*]}"

shift 1

source .envrc
exec docker compose --project-directory . "${FILES[@]}" "${RUN_ARGS[@]}" "$@"
