# Makefile for YouTube Downloader Docker Environment

.PHONY: help up down build rebuild restart logs shell clean

# Default target
help: ## Show this help message
	@echo "YouTube Downloader Docker Environment"
	@echo ""
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

up: ## Start the docker-compose environment
	docker-compose up -d

down: ## Stop the docker-compose environment
	docker-compose down

build: ## Build the docker image
	docker-compose build

rebuild: ## Rebuild the docker image without cache
	docker-compose down
	docker-compose build
	docker-compose up -d

restart: ## Restart the docker-compose environment
	docker-compose restart

logs: ## Show logs from the running containers
	docker-compose logs -f

shell: ## Open a shell in the running container
	docker-compose exec yt-downloader bash

status: ## Show status of running containers
	docker-compose ps

clean: ## Remove containers, networks, and volumes
	docker-compose down -v --remove-orphans

clean-all: ## Remove everything including images
	docker-compose down -v --remove-orphans --rmi all