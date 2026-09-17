.DEFAULT_GOAL := help
UV ?= uv

.PHONY: help venv install fmt lint test verify report check new clean

help: ## 显示所有命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

venv: ## 创建开发环境（uv + Python 3.13）
	$(UV) venv --python 3.13

install: ## 安装项目与开发依赖
	$(UV) sync --dev

fmt: ## 格式化
	$(UV) run ruff format .
	$(UV) run ruff check . --fix

lint: ## 只检查不修改
	$(UV) run ruff format --check .
	$(UV) run ruff check .

test: ## 运行测试
	$(UV) run pytest

verify: ## 校验实验合同（仓库尚无实验时放行，与 CI 一致）
	$(UV) run scirearch verify --allow-empty

report: ## 输出实验汇总表
	$(UV) run scirearch report

check: lint test verify ## 提交前完整闸门

new: ## 新建实验：make new name=slug hypothesis="..."
	$(UV) run scirearch new $(name) --hypothesis "$(hypothesis)"

clean: ## 清理缓存
	rm -rf .pytest_cache .ruff_cache **/__pycache__ src/*.egg-info
