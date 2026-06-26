"""Visualisation tools for radar micro-Doppler analysis."""

from .spectrogram_plot import plot_spectrogram, plot_proposed_feature, plot_sample_overview
from .range_doppler_plot import plot_range_doppler_map, plot_doppler_time_waterfall, plot_range_time
from .airspace_plot import (
    Target,
    Track,
    TrackPoint,
    plot_2d_radar_sector,
    plot_track,
    plot_3d_airspace,
)
from .eigen_plot import plot_eigenspectrum, plot_feature_dim_vs_error, plot_subspace_comparison
from .roc_det_plot import (
    plot_roc_curve,
    plot_det_curve,
    plot_threshold_sweep,
    plot_multi_method_comparison,
)
from .dashboard_assets import generate_dashboard_summary

__all__ = [
    # spectrogram_plot
    "plot_spectrogram",
    "plot_proposed_feature",
    "plot_sample_overview",
    # range_doppler_plot
    "plot_range_doppler_map",
    "plot_doppler_time_waterfall",
    "plot_range_time",
    # airspace_plot
    "Target",
    "Track",
    "TrackPoint",
    "plot_2d_radar_sector",
    "plot_track",
    "plot_3d_airspace",
    # eigen_plot
    "plot_eigenspectrum",
    "plot_feature_dim_vs_error",
    "plot_subspace_comparison",
    # roc_det_plot
    "plot_roc_curve",
    "plot_det_curve",
    "plot_threshold_sweep",
    "plot_multi_method_comparison",
    # dashboard_assets
    "generate_dashboard_summary",
]
