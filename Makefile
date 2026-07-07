.PHONY: help install download prepare train-sra eval-sra train-cnn eval-cnn airspace-demo test lint docker-up docker-down docker-init docker-install-module post-setup demo-data

help:
	@echo "radar-drone-vision - 低空小目標雷達 AI 驗證平台 (Odoo 18 + AI Worker)"
	@echo ""
	@echo "Docker (Odoo 18 + PostgreSQL + AI Worker):"
	@echo "  make docker-up             啟動所有服務"
	@echo "  make docker-down           停止所有服務"
	@echo "  make docker-init           初始化資料庫 + 安裝模組"
	@echo "  make docker-install-module 安裝/更新 Odoo 模組"
	@echo "  make post-setup            執行後製偏好設定 (繁中/帳號/主題/跳轉)"
	@echo "  make demo-data             匯入 Demo 資料"
	@echo ""
	@echo "AI Worker 資料處理:"
	@echo "  make download              下載 Zenodo 77GHz FMCW 資料集"
	@echo "  make prepare               準備處理後資料集"
	@echo ""
	@echo "AI Worker 訓練:"
	@echo "  make train-sra             訓練 SRA 分類器 (論文演算法)"
	@echo "  make train-cnn             訓練 PyTorch CNN 分類器"
	@echo ""
	@echo "AI Worker 評估:"
	@echo "  make eval-sra              評估 SRA 模型"
	@echo "  make eval-cnn              評估 CNN 模型"
	@echo "  make eval-all              評估所有模型並產出比較報告"
	@echo ""
	@echo "視覺化:"
	@echo "  make airspace-demo         產出空域視覺化 Demo"
	@echo ""
	@echo "開發:"
	@echo "  make install               本機安裝開發套件"
	@echo "  make test                  執行測試"
	@echo "  make lint                  執行 linter"

# === Docker Odoo 18 ===

docker-up:
	docker compose up --build -d
	@echo "✅ 服務已啟動"
	@echo "  Odoo:      http://localhost:46069"
	@echo "  AI Worker: http://localhost:46090"

docker-down:
	docker compose down

docker-init:
	docker compose up -d db
	sleep 5
	docker compose run --rm odoo odoo -d radar_drone_vision -i radar_drone_vision --stop-after-init --without-demo=all
	docker compose up -d

docker-install-module:
	docker compose exec odoo odoo -d radar_drone_vision -u radar_drone_vision --stop-after-init

post-setup:
	python3 scripts/post_odoo_preferences.py

demo-data:
	python3 scripts/generate_demo_data.py

# === AI Worker 資料集 ===

download:
	docker compose exec ai-worker python scripts/download_zenodo.py --out data/raw/zenodo_77ghz

prepare:
	docker compose exec ai-worker python scripts/prepare_dataset.py --dataset zenodo77 --config configs/datasets/zenodo77.yaml

# === AI Worker 訓練 ===

train-sra:
	docker compose exec ai-worker python scripts/train_sra.py \
		--config configs/models/sra.yaml \
		--dataset zenodo77 \
		--feature proposed_regularized_complex_log_fft \
		--repeat 20 \
		--split half

eval-sra:
	docker compose exec ai-worker python scripts/evaluate.py \
		--model models/sra_model.joblib \
		--dataset zenodo77 \
		--out reports/sra_eval

train-cnn:
	docker compose exec ai-worker python scripts/train_cnn.py \
		--config configs/models/cnn.yaml \
		--dataset zenodo77 \
		--feature proposed_complex_image \
		--epochs 50

eval-cnn:
	docker compose exec ai-worker python scripts/evaluate.py \
		--model models/cnn_best.pt \
		--dataset zenodo77 \
		--out reports/cnn_eval

eval-all:
	docker compose exec ai-worker python scripts/evaluate.py --all --dataset zenodo77 --out reports/full_eval
	docker compose exec ai-worker python scripts/export_report.py --out reports/paper_comparison.md

# === 視覺化 ===

airspace-demo:
	docker compose exec ai-worker python scripts/render_airspace.py \
		--dataset synthetic_airspace \
		--out reports/airspace_demo

# === 開發 ===

install:
	pip install -e ".[dev,notebook]"

test:
	python3 -m pytest tests/ -v --tb=short

lint:
	ruff check src/ tests/ scripts/
