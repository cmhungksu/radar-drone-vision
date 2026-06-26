"""PCA baseline for dimensionality reduction."""

from __future__ import annotations

from typing import Optional, Union

import numpy as np
from sklearn.decomposition import PCA


def fit_pca(
    X_train: np.ndarray,
    n_components: Union[int, float] = 50,
) -> PCA:
    """Fit a PCA model on training data.

    Parameters
    ----------
    X_train : np.ndarray
        Training feature matrix ``(n_samples, n_features)``.
    n_components : int or float
        Number of components to keep.  If ``< 1`` it is interpreted as
        the fraction of variance to retain.

    Returns
    -------
    model : sklearn.decomposition.PCA
        Fitted PCA model.
    """
    model = PCA(n_components=n_components)
    model.fit(X_train)
    return model


def transform_pca(X: np.ndarray, model: PCA) -> np.ndarray:
    """Project data into the PCA subspace.

    Parameters
    ----------
    X : np.ndarray
        Feature matrix ``(n_samples, n_features)``.
    model : PCA
        Fitted PCA model (from :func:`fit_pca`).

    Returns
    -------
    X_proj : np.ndarray
        Projected data ``(n_samples, n_components)``.
    """
    return model.transform(X)
