"""CRNN (Conv + Recurrent) model for radar micro-Doppler classification."""

from __future__ import annotations

import torch
import torch.nn as nn


class RadarCRNN(nn.Module):
    """Conv2d feature extractor followed by GRU and FC classification head.

    The spatial feature maps are collapsed along the frequency axis and fed
    as a time-sequence to a GRU, capturing temporal dynamics in the
    micro-Doppler signature.

    Parameters
    ----------
    in_channels : int
        Number of input channels.
    num_classes : int
        Number of output classes.
    hidden_size : int
        GRU hidden dimension.
    num_gru_layers : int
        Number of stacked GRU layers.
    dropout : float
        Dropout probability.
    bidirectional : bool
        Whether the GRU is bidirectional.
    """

    def __init__(
        self,
        in_channels: int = 1,
        num_classes: int = 2,
        hidden_size: int = 128,
        num_gru_layers: int = 2,
        dropout: float = 0.3,
        bidirectional: bool = True,
    ) -> None:
        super().__init__()

        self.cnn = nn.Sequential(
            nn.Conv2d(in_channels, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )

        self.hidden_size = hidden_size
        self.bidirectional = bidirectional
        self.num_directions = 2 if bidirectional else 1

        # GRU input size will be inferred on first forward pass
        self._gru_input_size: int | None = None
        self._gru: nn.GRU | None = None
        self._fc: nn.Sequential | None = None

        self.num_gru_layers = num_gru_layers
        self.dropout = dropout
        self.num_classes = num_classes

    def _build_rnn(self, gru_input_size: int) -> None:
        device = next(self.cnn.parameters()).device
        self._gru_input_size = gru_input_size
        self._gru = nn.GRU(
            input_size=gru_input_size,
            hidden_size=self.hidden_size,
            num_layers=self.num_gru_layers,
            batch_first=True,
            dropout=self.dropout if self.num_gru_layers > 1 else 0.0,
            bidirectional=self.bidirectional,
        ).to(device)
        self._fc = nn.Sequential(
            nn.Linear(self.hidden_size * self.num_directions, 64),
            nn.ReLU(inplace=True),
            nn.Dropout(self.dropout),
            nn.Linear(64, self.num_classes),
        ).to(device)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Parameters
        ----------
        x : torch.Tensor
            Input ``(B, C, H, W)`` — H is treated as the time axis after CNN
            downsampling, W (frequency) is collapsed into the feature dim.

        Returns
        -------
        torch.Tensor
            Logits ``(B, num_classes)``.
        """
        # CNN feature extraction
        feat = self.cnn(x)  # (B, Ch, T', F')
        B, Ch, T, F = feat.shape

        # Reshape: treat T as sequence length, Ch*F as feature dim
        seq = feat.permute(0, 2, 1, 3).reshape(B, T, Ch * F)  # (B, T, Ch*F)

        # Lazy init GRU once we know the feature dim
        if self._gru is None or self._gru_input_size != seq.shape[2]:
            self._build_rnn(seq.shape[2])

        out, _ = self._gru(seq)  # (B, T, hidden*dirs)
        # Use last time-step
        last = out[:, -1, :]  # (B, hidden*dirs)
        logits = self._fc(last)
        return logits
