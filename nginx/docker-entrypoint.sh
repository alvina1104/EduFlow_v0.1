#!/bin/sh
set -eu

trusted_proxy_cidrs=${TRUSTED_PROXY_CIDRS:-}
if [ "${ENVIRONMENT:-development}" = "production" ] && [ -z "$trusted_proxy_cidrs" ]; then
    echo "TRUSTED_PROXY_CIDRS must contain the trusted load balancer subnets in production" >&2
    exit 1
fi

trusted_proxy_file=/etc/nginx/trusted-proxies.conf
: > "$trusted_proxy_file"
if [ -n "$trusted_proxy_cidrs" ]; then
    set -f
    old_ifs=$IFS
    IFS=,
    for cidr in $trusted_proxy_cidrs; do
        case "$cidr" in
            ''|*[!0-9A-Fa-f:./]*)
                echo "Invalid value in TRUSTED_PROXY_CIDRS" >&2
                exit 1
                ;;
            0.0.0.0/0|::/0)
                echo "TRUSTED_PROXY_CIDRS must not trust every internet address" >&2
                exit 1
                ;;
        esac
        printf 'set_real_ip_from %s;\n' "$cidr" >> "$trusted_proxy_file"
    done
    IFS=$old_ifs
fi

exec /docker-entrypoint.sh "$@"
