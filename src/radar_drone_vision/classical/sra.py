"""Subspace Reliability Analysis (SRA) for UAV vs. non-UAV classification.

This is the core algorithm of the radar micro-Doppler classification
pipeline.  It projects data onto class-specific subspaces and uses the
ratio of Mahalanobis-like distances in those subspaces for detection.

References
----------
Algorithm follows the SRA formulation for micro-Doppler classification:
  1. Compute per-class statistics (mean, covariance).
  2. Build augmented scatter matrices S_k = Sigma_k + Sigma_b.
  3. Eigen-decompose each S_k and retain leading eigenvectors.
  4. Score each test sample by the ratio g1/g2 of subspace distances.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import joblib
import numpy as np


class SubspaceReliabilityAnalysis:
    """Subspace Reliability Analysis classifier.

    Parameters
    ----------
    m_uav : int
        Number of eigenvectors to retain for the UAV subspace.
    m_non_uav : int
        Number of eigenvectors to retain for the non-UAV subspace.
    ridge : float
        Tikhonov (ridge) regularisation added to covariance diagonals
        to prevent singular matrices.
    """

    def __init__(
        self,
        m_uav: int = 10,
        m_non_uav: int = 100,
        ridge: float = 1e-5,
    ) -> None:
        self.m_uav = m_uav
        self.m_non_uav = m_non_uav
        self.ridge = ridge

        # Fitted quantities (populated by .fit())
        self.mu1_: Optional[np.ndarray] = None  # UAV mean
        self.mu2_: Optional[np.ndarray] = None  # non-UAV mean
        self.cov1_: Optional[np.ndarray] = None  # UAV covariance
        self.cov2_: Optional[np.ndarray] = None  # non-UAV covariance
        self.cov_b_: Optional[np.ndarray] = None  # between-class covariance
        self.phi1_: Optional[np.ndarray] = None  # UAV subspace basis (d, m_uav)
        self.phi2_: Optional[np.ndarray] = None  # non-UAV subspace basis (d, m_non_uav)
        self.sub_cov_inv1_: Optional[np.ndarray] = None
        self.sub_cov_inv2_: Optional[np.ndarray] = None
        self.eigenvalues1_: Optional[np.ndarray] = None
        self.eigenvalues2_: Optional[np.ndarray] = None

    # ------------------------------------------------------------------ #
    # Fit
    # ------------------------------------------------------------------ #

    def fit(self, X: np.ndarray, y: np.ndarray) -> "SubspaceReliabilityAnalysis":
        """Fit the SRA model.

        Parameters
        ----------
        X : np.ndarray, shape (n, d)
            Training feature vectors.
        y : np.ndarray, shape (n,)
            Binary labels: ``1`` = UAV, ``0`` = non-UAV.

        Returns
        -------
        self
        """
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y).ravel()

        X1 = X[y == 1]  # UAV
        X2 = X[y == 0]  # non-UAV
        if len(X1) == 0 or len(X2) == 0:
            raise ValueError("Both classes (y=1 UAV, y=0 non-UAV) must be present.")

        d = X.shape[1]
        reg = self.ridge * np.eye(d, dtype=np.float64)

        # 1. Per-class means and covariances
        self.mu1_ = X1.mean(axis=0)
        self.mu2_ = X2.mean(axis=0)
        self.cov1_ = np.cov(X1, rowvar=False, ddof=1) + reg
        self.cov2_ = np.cov(X2, rowvar=False, ddof=1) + reg

        # Handle single-sample edge case (np.cov returns scalar for 1-D)
        if self.cov1_.ndim == 0:
            self.cov1_ = np.atleast_2d(self.cov1_)
        if self.cov2_.ndim == 0:
            self.cov2_ = np.atleast_2d(self.cov2_)

        # 2. Between-class scatter
        mu_diff = (self.mu1_ - self.mu2_).reshape(-1, 1)
        self.cov_b_ = mu_diff @ mu_diff.T

        # 3. Augmented scatter matrices
        S1 = self.cov1_ + self.cov_b_
        S2 = self.cov2_ + self.cov_b_

        # 4. Eigen-decomposition (eigh gives ascending order)
        eigvals1, eigvecs1 = np.linalg.eigh(S1)
        eigvals2, eigvecs2 = np.linalg.eigh(S2)

        # Sort descending
        idx1 = np.argsort(eigvals1)[::-1]
        idx2 = np.argsort(eigvals2)[::-1]
        eigvals1, eigvecs1 = eigvals1[idx1], eigvecs1[:, idx1]
        eigvals2, eigvecs2 = eigvals2[idx2], eigvecs2[:, idx2]

        self.eigenvalues1_ = eigvals1
        self.eigenvalues2_ = eigvals2

        # 5. Retain leading eigenvectors
        m1 = min(self.m_uav, d)
        m2 = min(self.m_non_uav, d)
        self.phi1_ = eigvecs1[:, :m1]  # (d, m1)
        self.phi2_ = eigvecs2[:, :m2]  # (d, m2)

        # 6. Precompute subspace covariance inverses:
        #    (Phi^T Sigma Phi)^{-1}
        sub_cov1 = self.phi1_.T @ self.cov1_ @ self.phi1_ + self.ridge * np.eye(m1)
        sub_cov2 = self.phi2_.T @ self.cov2_ @ self.phi2_ + self.ridge * np.eye(m2)
        self.sub_cov_inv1_ = np.linalg.pinv(sub_cov1)
        self.sub_cov_inv2_ = np.linalg.pinv(sub_cov2)

        return self

    # ------------------------------------------------------------------ #
    # Score & Predict
    # ------------------------------------------------------------------ #

    def score_ratio(self, X: np.ndarray) -> np.ndarray:
        """Compute the SRA score ratio g1/g2 for each sample.

        Lower ratio => more UAV-like.

        Parameters
        ----------
        X : np.ndarray, shape (n, d)

        Returns
        -------
        ratios : np.ndarray, shape (n,)
        """
        self._check_fitted()
        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(1, -1)

        g1 = self._subspace_distance(X, self.mu1_, self.phi1_, self.sub_cov_inv1_)
        g2 = self._subspace_distance(X, self.mu2_, self.phi2_, self.sub_cov_inv2_)

        # Avoid division by zero
        g2_safe = np.where(g2 == 0, np.finfo(np.float64).eps, g2)
        return g1 / g2_safe

    def predict(self, X: np.ndarray, threshold: float = 1.0) -> np.ndarray:
        """Predict class labels.

        Parameters
        ----------
        X : np.ndarray, shape (n, d)
        threshold : float
            Samples with ``ratio < threshold`` are classified as UAV (1).

        Returns
        -------
        y_pred : np.ndarray of int, shape (n,)
        """
        ratios = self.score_ratio(X)
        return (ratios < threshold).astype(int)

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def save(self, path: str) -> None:
        """Save the fitted model to disk via joblib."""
        joblib.dump(self.__dict__, path)

    def load(self, path: str) -> "SubspaceReliabilityAnalysis":
        """Load a fitted model from disk.

        Returns
        -------
        self
        """
        state = joblib.load(path)
        self.__dict__.update(state)
        return self

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    @staticmethod
    def _subspace_distance(
        X: np.ndarray,
        mu: np.ndarray,
        phi: np.ndarray,
        sub_cov_inv: np.ndarray,
    ) -> np.ndarray:
        """Mahalanobis-like distance in a subspace.

        g = (h - mu)^T Phi (Phi^T Sigma Phi)^{-1} Phi^T (h - mu)

        Parameters
        ----------
        X : (n, d)
        mu : (d,)
        phi : (d, m)
        sub_cov_inv : (m, m)

        Returns
        -------
        distances : (n,)
        """
        diff = X - mu  # (n, d)
        proj = diff @ phi  # (n, m)
        # g = sum_i proj_i^T @ sub_cov_inv @ proj_i
        transformed = proj @ sub_cov_inv  # (n, m)
        return np.sum(transformed * proj, axis=1)

    def _check_fitted(self) -> None:
        if self.phi1_ is None or self.phi2_ is None:
            raise RuntimeError("Model has not been fitted. Call .fit() first.")
