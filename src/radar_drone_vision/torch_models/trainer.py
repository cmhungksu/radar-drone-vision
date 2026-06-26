"""Training loop with early stopping, class weighting, and ONNX export."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader

logger = logging.getLogger(__name__)


@dataclass
class TrainerConfig:
    """Configuration for the training loop."""

    lr: float = 1e-3
    weight_decay: float = 1e-4
    epochs: int = 50
    patience: int = 10
    device: str = "cuda" if torch.cuda.is_available() else "cpu"
    checkpoint_dir: Optional[str] = None
    use_class_weights: bool = True
    scheduler: str = "cosine"  # "cosine" or "step"


class Trainer:
    """Training loop with early stopping, balanced class weights, and LR scheduling.

    Parameters
    ----------
    model : nn.Module
        The network to train.
    config : TrainerConfig or dict
        Training hyper-parameters.
    """

    def __init__(self, model: nn.Module, config: TrainerConfig | dict | None = None) -> None:
        if config is None:
            config = TrainerConfig()
        elif isinstance(config, dict):
            config = TrainerConfig(**config)

        self.model = model
        self.config = config
        self.device = torch.device(config.device)
        self.model.to(self.device)

        self.history: Dict[str, List[float]] = {
            "train_loss": [],
            "train_acc": [],
            "train_f1": [],
            "val_loss": [],
            "val_acc": [],
            "val_f1": [],
        }
        self.best_model_state: Optional[dict] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def train(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
        epochs: Optional[int] = None,
    ) -> Dict[str, List[float]]:
        """Run the training loop.

        Returns the training history dict.
        """
        epochs = epochs or self.config.epochs

        # Class weights
        criterion = self._make_criterion(train_loader)

        optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=self.config.lr,
            weight_decay=self.config.weight_decay,
        )
        scheduler = self._make_scheduler(optimizer, epochs)

        best_val_f1 = -1.0
        patience_counter = 0

        for epoch in range(1, epochs + 1):
            train_loss, train_acc, train_f1 = self._train_epoch(
                train_loader, criterion, optimizer
            )
            val_loss, val_acc, val_f1 = self._eval_epoch(val_loader, criterion)

            if scheduler is not None:
                scheduler.step()

            self.history["train_loss"].append(train_loss)
            self.history["train_acc"].append(train_acc)
            self.history["train_f1"].append(train_f1)
            self.history["val_loss"].append(val_loss)
            self.history["val_acc"].append(val_acc)
            self.history["val_f1"].append(val_f1)

            logger.info(
                "Epoch %3d/%d  train_loss=%.4f  train_f1=%.4f  "
                "val_loss=%.4f  val_f1=%.4f",
                epoch, epochs, train_loss, train_f1, val_loss, val_f1,
            )

            # Early stopping on val F1
            if val_f1 > best_val_f1:
                best_val_f1 = val_f1
                patience_counter = 0
                self.best_model_state = copy.deepcopy(self.model.state_dict())
                if self.config.checkpoint_dir:
                    self._save_checkpoint(epoch)
            else:
                patience_counter += 1
                if patience_counter >= self.config.patience:
                    logger.info("Early stopping at epoch %d", epoch)
                    break

        # Restore best model
        if self.best_model_state is not None:
            self.model.load_state_dict(self.best_model_state)

        return self.history

    def evaluate(
        self, test_loader: DataLoader
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        """Evaluate on a test set.

        Returns
        -------
        y_pred : np.ndarray
            Predicted class labels.
        y_prob : np.ndarray
            Class probabilities (softmax).
        metrics : dict
            Accuracy, F1, loss.
        """
        self.model.eval()
        all_preds: List[np.ndarray] = []
        all_probs: List[np.ndarray] = []
        all_labels: List[np.ndarray] = []
        total_loss = 0.0
        criterion = nn.CrossEntropyLoss()
        n = 0

        with torch.no_grad():
            for X, y in test_loader:
                X, y = X.to(self.device), y.to(self.device)
                logits = self.model(X)
                loss = criterion(logits, y)
                total_loss += loss.item() * y.size(0)
                n += y.size(0)

                probs = torch.softmax(logits, dim=1).cpu().numpy()
                preds = logits.argmax(dim=1).cpu().numpy()
                all_probs.append(probs)
                all_preds.append(preds)
                all_labels.append(y.cpu().numpy())

        y_pred = np.concatenate(all_preds)
        y_prob = np.concatenate(all_probs)
        y_true = np.concatenate(all_labels)

        acc = float(np.mean(y_pred == y_true))
        f1 = float(f1_score(y_true, y_pred, average="binary", pos_label=1, zero_division=0))

        metrics = {
            "accuracy": acc,
            "f1": f1,
            "loss": total_loss / max(n, 1),
        }
        return y_pred, y_prob, metrics

    def export_onnx(
        self,
        path: str | Path,
        input_shape: Tuple[int, ...] = (1, 1, 128, 128),
    ) -> None:
        """Export the model to ONNX format.

        Parameters
        ----------
        path : str or Path
            Destination file path.
        input_shape : tuple
            Shape of the dummy input tensor ``(B, C, H, W)``.
        """
        self.model.eval()
        dummy = torch.randn(*input_shape, device=self.device)
        torch.onnx.export(
            self.model,
            dummy,
            str(path),
            input_names=["input"],
            output_names=["logits"],
            dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
            opset_version=17,
        )
        logger.info("ONNX model exported to %s", path)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _make_criterion(self, train_loader: DataLoader) -> nn.CrossEntropyLoss:
        if not self.config.use_class_weights:
            return nn.CrossEntropyLoss()

        # Collect labels to compute balanced weights
        labels: List[int] = []
        for _, y in train_loader:
            labels.extend(y.numpy().tolist())
        labels_arr = np.array(labels)
        classes = np.unique(labels_arr)
        counts = np.array([np.sum(labels_arr == c) for c in classes], dtype=np.float64)
        weights = 1.0 / np.maximum(counts, 1)
        weights = weights / weights.sum() * len(classes)
        weight_tensor = torch.tensor(weights, dtype=torch.float32, device=self.device)
        return nn.CrossEntropyLoss(weight=weight_tensor)

    def _make_scheduler(self, optimizer, epochs: int):
        if self.config.scheduler == "cosine":
            return torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
        elif self.config.scheduler == "step":
            return torch.optim.lr_scheduler.StepLR(optimizer, step_size=max(epochs // 3, 1))
        return None

    def _train_epoch(self, loader, criterion, optimizer):
        self.model.train()
        total_loss = 0.0
        correct = 0
        n = 0
        all_preds = []
        all_labels = []

        for X, y in loader:
            X, y = X.to(self.device), y.to(self.device)
            optimizer.zero_grad()
            logits = self.model(X)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()

            total_loss += loss.item() * y.size(0)
            preds = logits.argmax(dim=1)
            correct += (preds == y).sum().item()
            n += y.size(0)
            all_preds.extend(preds.cpu().numpy().tolist())
            all_labels.extend(y.cpu().numpy().tolist())

        acc = correct / max(n, 1)
        f1 = f1_score(all_labels, all_preds, average="binary", pos_label=1, zero_division=0)
        return total_loss / max(n, 1), acc, f1

    def _eval_epoch(self, loader, criterion):
        self.model.eval()
        total_loss = 0.0
        correct = 0
        n = 0
        all_preds = []
        all_labels = []

        with torch.no_grad():
            for X, y in loader:
                X, y = X.to(self.device), y.to(self.device)
                logits = self.model(X)
                loss = criterion(logits, y)

                total_loss += loss.item() * y.size(0)
                preds = logits.argmax(dim=1)
                correct += (preds == y).sum().item()
                n += y.size(0)
                all_preds.extend(preds.cpu().numpy().tolist())
                all_labels.extend(y.cpu().numpy().tolist())

        acc = correct / max(n, 1)
        f1 = f1_score(all_labels, all_preds, average="binary", pos_label=1, zero_division=0)
        return total_loss / max(n, 1), acc, f1

    def _save_checkpoint(self, epoch: int) -> None:
        ckpt_dir = Path(self.config.checkpoint_dir)
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        path = ckpt_dir / f"best_model_epoch{epoch}.pt"
        torch.save(self.model.state_dict(), path)
        logger.info("Checkpoint saved: %s", path)
