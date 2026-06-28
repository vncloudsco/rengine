.PHONY: up down down-all logs status disable sync-once recover-db verify help

UP_OPTS ?=

up:           ## Bootstrap full reNgine (if needed) + Urban proxy. Use: make up UP_OPTS=-n
	@bash ./up.sh $(UP_OPTS)

down:         ## Stop Urban proxy module only
	@bash ./down.sh

down-all:     ## Stop full reNgine stack + proxy module
	@bash ./down-all.sh

logs:         ## Tail urban-proxy-fetcher logs
	@bash ./scripts/logs.sh

status:       ## Show core + proxy module status
	@bash ./scripts/status.sh

disable:      ## Set use_proxy=false in reNgine DB
	@bash ./scripts/disable.sh

sync-once:    ## Push proxy file to DB once
	@bash ./scripts/sync-once.sh

recover-db:   ## Reset PostgreSQL volume (fixes broken migrations). Use: make recover-db RECOVER_OPTS=-y
	@bash ./scripts/recover-db.sh $(RECOVER_OPTS)

verify:       ## Confirm reNgine proxy storage + sync path (run after make sync-once)
	@bash ./scripts/verify-proxy.sh

help:         ## Show help
	@bash ./scripts/help.sh
