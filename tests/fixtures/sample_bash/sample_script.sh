#!/usr/bin/env bash

# Maximum retry count
MAX_RETRIES=5

# Base URL for API
API_URL="https://example.com/api"

# Log levels
LOG_LEVEL="INFO"

# Greet a user by name
greet() {
    local name="$1"
    echo "Hello, $name!"
}

# Compute the sum of two numbers
add() {
    local a="$1"
    local b="$2"
    echo $((a + b))
}

# Check if a file exists and is readable
check_file() {
    local filepath="$1"
    if [[ -f "$filepath" && -r "$filepath" ]]; then
        return 0
    fi
    return 1
}

# Deploy the application
deploy() {
    greet "World"
    check_file "/etc/config"
    add 1 2
}

# Cleanup temp files and exit
cleanup() {
    rm -f /tmp/codeatlas_*
}
