"""Vision Transformer (ViT-like) for radar micro-Doppler classification."""

from __future__ import annotations

import math

import torch
import torch.nn as nn


class PatchEmbedding(nn.Module):
    """Split image into non-overlapping patches and embed them."""

    def __init__(self, in_channels: int, patch_size: int, embed_dim: int, img_size: int) -> None:
        super().__init__()
        self.num_patches = (img_size // patch_size) ** 2
        self.proj = nn.Conv2d(in_channels, embed_dim, kernel_size=patch_size, stride=patch_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # (B, C, H, W) -> (B, embed_dim, H', W') -> (B, num_patches, embed_dim)
        x = self.proj(x)
        x = x.flatten(2).transpose(1, 2)
        return x


class RadarTransformer(nn.Module):
    """Patch-based Transformer encoder for radar image classification.

    Parameters
    ----------
    in_channels : int
        Number of input channels.
    num_classes : int
        Number of output classes.
    img_size : int
        Expected spatial size (assumes square images).
    patch_size : int
        Patch size for the patch embedding.
    embed_dim : int
        Transformer embedding dimension.
    num_heads : int
        Number of attention heads.
    num_layers : int
        Number of Transformer encoder layers.
    mlp_ratio : float
        Ratio of MLP hidden dim to embed_dim.
    dropout : float
        Dropout probability.
    """

    def __init__(
        self,
        in_channels: int = 1,
        num_classes: int = 2,
        img_size: int = 128,
        patch_size: int = 16,
        embed_dim: int = 128,
        num_heads: int = 4,
        num_layers: int = 4,
        mlp_ratio: float = 2.0,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()

        self.patch_embed = PatchEmbedding(in_channels, patch_size, embed_dim, img_size)
        num_patches = self.patch_embed.num_patches

        # Learnable [CLS] token and position embeddings
        self.cls_token = nn.Parameter(torch.zeros(1, 1, embed_dim))
        self.pos_embed = nn.Parameter(torch.zeros(1, num_patches + 1, embed_dim))
        self.pos_drop = nn.Dropout(dropout)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=embed_dim,
            nhead=num_heads,
            dim_feedforward=int(embed_dim * mlp_ratio),
            dropout=dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.norm = nn.LayerNorm(embed_dim)

        self.head = nn.Linear(embed_dim, num_classes)

        self._init_weights()

    def _init_weights(self) -> None:
        nn.init.trunc_normal_(self.cls_token, std=0.02)
        nn.init.trunc_normal_(self.pos_embed, std=0.02)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Parameters
        ----------
        x : torch.Tensor
            Input ``(B, C, H, W)``.

        Returns
        -------
        torch.Tensor
            Logits ``(B, num_classes)``.
        """
        B = x.shape[0]
        patches = self.patch_embed(x)  # (B, N, D)

        cls_tokens = self.cls_token.expand(B, -1, -1)
        x = torch.cat([cls_tokens, patches], dim=1)  # (B, N+1, D)
        x = self.pos_drop(x + self.pos_embed)

        x = self.encoder(x)
        x = self.norm(x)

        # Classification from [CLS] token
        cls_out = x[:, 0]
        logits = self.head(cls_out)
        return logits
