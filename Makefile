.PHONY: help install download prepare train-sra eval-sra train-cnn eval-cnn airspace-demo test lint docker-up docker-down

help:
	@echo "radar-drone-vision - Low-altitude radar AI validation platform"
	@echo ""
	@echo "Data:"
	@echo "  make download        Download Zenodo 77GHz FMCW dataset"
	@echo "  make prepare         Prepare processed dataset from raw"
	@echo ""
	@echo "Training:"
	@echo "  make train-sra       Train SRA classifier (paper algorithm)"
	@echo "  make train-cnn       Train PyTorch CNN classifier"
	@echo ""
	@echo "Evaluation:"
	@echo "  make eval-sra        Evaluate SRA model"
	@echo "  make eval-cnn        Evaluate CNN model"
	@echo "  make eval-all        Evaluate all models and generate comparison"
	@echo ""
	@echo "Visualization:"
	@echo "  make airspace-demo   Generate airspace visualization demo"
	@echo ""
	@echo "Development:"
	@echo "  make install         Install package in development mode"
	@echo "  make test            Run all tests"
	@echo "  make lint            Run linter"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-up       Start all services"
	@echo "  make docker-down     Stop all services"

install:
	pip install -e ".[dev,notebook]"

download:
	python scripts/download_zenodo.py --out data/raw/zenodo_77ghz

prepare:
	python scripts/prepare_dataset.py --dataset zenodo77 --config configs/datasets/zenodo77.yaml

train-sra:
	python scripts/train_sra.py \
		--config configs/models/sra.yaml \
		--dataset zenodo77 \
		--feature proposed_regularized_complex_log_fft \
		--repeat 20 \
		--split half

eval-sra:
	python scripts/evaluate.py \
		--model models/sra_model.joblib \
		--dataset zenodo77 \
		--out reports/sra_eval

train-cnn:
	python scripts/train_cnn.py \
		--config configs/models/cnn.yaml \
		--dataset zenodo77 \
		--feature proposed_complex_image \
		--epochs 50

eval-cnn:
	python scripts/evaluate.py \
		--model models/cnn_best.pt \
		--dataset zenodo77 \
		--out reports/cnn_eval

eval-all:
	python scripts/evaluate.py --all --dataset zenodo77 --out reports/full_eval
	python scripts/export_report.py --out reports/paper_comparison.md

airspace-demo:
	python scripts/render_airspace.py \
		--dataset synthetic_airspace \
		--out reports/airspace_demo

test:
	pytest tests/ -v --tb=short

lint:
	ruff check src/ tests/ scripts/

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down
