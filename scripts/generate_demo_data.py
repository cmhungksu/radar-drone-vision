#!/usr/bin/env python3
"""
Generate demo data for radar-drone-vision via XML-RPC.
Creates datasets, experiments, models, inferences, and hardware records.

Usage: python3 scripts/generate_demo_data.py
"""
import random
import sys
import time
import xmlrpc.client

ODOO_URL = 'http://localhost:46069'
DB = 'radar_drone_vision'
ADMIN_EMAIL = 'chun.min.hung@gmail.com'
ADMIN_PW = 'bio5234'


def main():
    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
    models_proxy = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')

    # Authenticate
    uid = None
    pw_used = ADMIN_PW
    for login, pw in [
        (ADMIN_EMAIL, ADMIN_PW),
        ('admin', 'admin'),
        ('admin', ADMIN_PW),
    ]:
        try:
            uid = common.authenticate(DB, login, pw, {})
            if uid:
                pw_used = pw
                print(f"Authenticated as '{login}' (uid={uid})")
                break
        except Exception:
            continue

    if not uid:
        print("ERROR: Cannot authenticate.")
        sys.exit(1)

    def ex(model, method, *args, **kwargs):
        kw = kwargs if kwargs else {}
        return models_proxy.execute_kw(DB, uid, pw_used, model, method, *args, **kw)

    # ── Check which models exist ─────────────────────────────────
    available_models = set()
    for m in ['radar.dataset', 'radar.experiment', 'radar.model',
              'radar.inference', 'radar.hardware']:
        try:
            ex(m, 'search', [[]], {'limit': 1})
            available_models.add(m)
        except Exception:
            print(f"  Model '{m}' not available, skipping.")

    # ── 1. Datasets ──────────────────────────────────────────────
    ds_zenodo_id = None
    ds_synth_id = None
    if 'radar.dataset' in available_models:
        print("\n[1] Creating datasets...")
        existing = ex('radar.dataset', 'search', [[('name', 'like', '[Demo]')]])
        if existing:
            print(f"  {len(existing)} demo datasets already exist, skipping creation")
            ds_zenodo_id = existing[0] if len(existing) > 0 else None
            ds_synth_id = existing[1] if len(existing) > 1 else None
        else:

        ds_zenodo_id = ex('radar.dataset', 'create', [{
            'name': '[Demo] Zenodo 77GHz FMCW Radar Dataset',
            'dataset_type': 'zenodo77',
            'state': 'ready',
            'num_samples': 227,
            'num_uav': 17,
            'num_non_uav': 210,
            'carrier_freq_hz': 77e9,
            'radar_type': 'FMCW 77GHz',
            'doi': '10.5281/zenodo.XXXXXXX',
            'notes': 'Zenodo 公開資料集：77 GHz FMCW 雷達 micro-Doppler 訊號，'
                     '包含 3 種 UAV 和 7 種非 UAV 目標（鳥類、行人等）。',
        }])
        print(f"  Zenodo dataset created (id={ds_zenodo_id})")

        ds_synth_id = ex('radar.dataset', 'create', [{
            'name': '[Demo] 合成雷達資料集 (Simulated)',
            'dataset_type': 'synthetic',
            'state': 'ready',
            'num_samples': 5000,
            'num_uav': 2500,
            'num_non_uav': 2500,
            'carrier_freq_hz': 77e9,
            'radar_type': 'Simulated FMCW',
            'notes': '使用 radar-drone-vision 合成引擎產生的模擬資料，'
                     '平衡 UAV/非 UAV 樣本數，適合 CNN 訓練。',
        }])
        print(f"  Synthetic dataset created (id={ds_synth_id})")
    else:
        print("\n[1] radar.dataset not available, skipping.")

    # ── 2. Experiments ───────────────────────────────────────────
    exp_sra_id = None
    exp_cnn_id = None
    exp_draft_id = None
    if 'radar.experiment' in available_models and ds_zenodo_id:
        print("\n[2] Creating experiments...")
        existing = ex('radar.experiment', 'search', [[('name', 'like', '[Demo]')]])
        if existing:
            ex('radar.experiment', 'unlink', [existing])

        # SRA experiment (trained)
        exp_sra_id = ex('radar.experiment', 'create', [{
            'name': '[Demo] SRA 論文演算法實驗',
            'model_type': 'sra',
            'dataset_id': ds_zenodo_id,
            'feature_type': 'proposed_regularized_complex_log_fft',
            'state': 'trained',
            'sra_m_uav': 10,
            'sra_m_non_uav': 100,
            'sra_repeat': 20,
            'accuracy': 0.9735,
            'precision_val': 0.9412,
            'recall_val': 0.9412,
            'f1_score': 0.9412,
            'eer': 0.0265,
            'far_at_frr1': 0.0588,
            'auc': 0.9971,
            'duration_seconds': 12.7,
            'model_path': '/data/models/sra_zenodo77_best.pkl',
            'training_log': (
                'SRA Training Log\n'
                '================\n'
                'Feature: proposed_regularized_complex_log_fft\n'
                'Dataset: Zenodo 77GHz (227 samples)\n'
                'm_uav=10, m_non_uav=100, repeat=20\n'
                '\n'
                'Iteration 1/20: acc=0.9647\n'
                'Iteration 5/20: acc=0.9706\n'
                'Iteration 10/20: acc=0.9735\n'
                'Iteration 15/20: acc=0.9706\n'
                'Iteration 20/20: acc=0.9735\n'
                '\n'
                'Best accuracy: 0.9735\n'
                'EER: 0.0265\n'
                'Training completed in 12.7 seconds\n'
            ),
        }])
        print(f"  SRA experiment created (id={exp_sra_id})")

        # CNN experiment (trained)
        exp_cnn_id = ex('radar.experiment', 'create', [{
            'name': '[Demo] CNN PyTorch 深度學習實驗',
            'model_type': 'cnn',
            'dataset_id': ds_synth_id or ds_zenodo_id,
            'feature_type': 'spectrogram',
            'state': 'trained',
            'cnn_epochs': 50,
            'cnn_batch_size': 64,
            'cnn_lr': 0.001,
            'accuracy': 0.9580,
            'precision_val': 0.9524,
            'recall_val': 0.9600,
            'f1_score': 0.9562,
            'eer': 0.0420,
            'far_at_frr1': 0.0850,
            'auc': 0.9912,
            'duration_seconds': 347.2,
            'model_path': '/data/models/cnn_synth_epoch50.pth',
            'training_log': (
                'CNN Training Log\n'
                '================\n'
                'Model: CNN (PyTorch)\n'
                'Feature: spectrogram\n'
                'Epochs: 50, Batch: 64, LR: 0.001\n'
                '\n'
                'Epoch  1/50: loss=0.6931, val_acc=0.5120\n'
                'Epoch 10/50: loss=0.2145, val_acc=0.8760\n'
                'Epoch 20/50: loss=0.0987, val_acc=0.9280\n'
                'Epoch 30/50: loss=0.0543, val_acc=0.9420\n'
                'Epoch 40/50: loss=0.0312, val_acc=0.9520\n'
                'Epoch 50/50: loss=0.0198, val_acc=0.9580\n'
                '\n'
                'Best val_acc: 0.9580 @ epoch 50\n'
                'Training completed in 347.2 seconds\n'
            ),
        }])
        print(f"  CNN experiment created (id={exp_cnn_id})")

        # Draft experiment
        exp_draft_id = ex('radar.experiment', 'create', [{
            'name': '[Demo] CRNN 實驗 (草稿)',
            'model_type': 'crnn',
            'dataset_id': ds_zenodo_id,
            'feature_type': 'cepstrogram',
            'state': 'draft',
            'cnn_epochs': 100,
            'cnn_batch_size': 32,
            'cnn_lr': 0.0005,
        }])
        print(f"  CRNN draft experiment created (id={exp_draft_id})")
    else:
        print("\n[2] Skipping experiments (missing model or dataset).")

    # ── 3. Models ────────────────────────────────────────────────
    model_sra_id = None
    model_cnn_id = None
    if 'radar.model' in available_models:
        print("\n[3] Creating model records...")
        existing = ex('radar.model', 'search', [[('name', 'like', '[Demo]')]])
        if existing:
            ex('radar.model', 'unlink', [existing])

        model_sra_id = ex('radar.model', 'create', [{
            'name': '[Demo] SRA 論文最佳模型',
            'model_type': 'sra',
            'experiment_id': exp_sra_id,
            'file_path': '/data/models/sra_zenodo77_best.pkl',
            'eer': 0.0265,
            'accuracy': 0.9735,
            'is_active': True,
            'notes': 'SRA 演算法 (m_uav=10, m_non_uav=100, repeat=20) 基於 Zenodo 77GHz 資料集訓練',
        }])
        print(f"  SRA model created (id={model_sra_id}, active=True)")

        # Link experiment to model
        if exp_sra_id:
            try:
                ex('radar.experiment', 'write', [[exp_sra_id], {'trained_model_id': model_sra_id}])
            except Exception:
                pass

        model_cnn_id = ex('radar.model', 'create', [{
            'name': '[Demo] CNN PyTorch 模型',
            'model_type': 'cnn',
            'experiment_id': exp_cnn_id,
            'file_path': '/data/models/cnn_synth_epoch50.pth',
            'eer': 0.0420,
            'accuracy': 0.9580,
            'is_active': False,
            'notes': 'CNN 深度學習模型 (50 epochs) 基於合成資料集訓練',
        }])
        print(f"  CNN model created (id={model_cnn_id})")

        if exp_cnn_id:
            try:
                ex('radar.experiment', 'write', [[exp_cnn_id], {'trained_model_id': model_cnn_id}])
            except Exception:
                pass
    else:
        print("\n[3] radar.model not available, skipping.")

    # ── 4. Inference Records ─────────────────────────────────────
    if 'radar.inference' in available_models:
        print("\n[4] Creating inference records...")
        existing = ex('radar.inference', 'search', [[('name', 'like', '[Demo]')]])
        if existing:
            ex('radar.inference', 'unlink', [existing])

        target_labels = ['UAV', 'Bird', 'Pedestrian', 'Helicopter', 'Noise',
                         'DJI Phantom', 'DJI Mavic', 'Pigeon', 'Hawk', 'Clutter']
        results = ['uav', 'non_uav']

        random.seed(42)
        for i in range(20):
            is_uav = random.random() < 0.45
            target = random.choice(['DJI Phantom', 'DJI Mavic', 'UAV']) if is_uav \
                else random.choice(['Bird', 'Pigeon', 'Hawk', 'Pedestrian', 'Clutter'])
            confidence = round(random.uniform(0.82, 0.99), 4) if random.random() > 0.1 \
                else round(random.uniform(0.55, 0.75), 4)
            result = 'uav' if is_uav else 'non_uav'
            correct = confidence > 0.75

            try:
                ex('radar.inference', 'create', [{
                    'name': f'[Demo] Inference #{i+1:03d} - {target}',
                    'model_id': model_sra_id or False,
                    'result': result,
                    'confidence': confidence,
                    'target_label': target,
                    'is_correct': correct,
                    'processing_time_ms': round(random.uniform(5.0, 85.0), 1),
                    'notes': f'Demo inference for {target} target',
                }])
            except Exception as e:
                # Model might have different fields, try minimal
                try:
                    ex('radar.inference', 'create', [{
                        'name': f'[Demo] Inference #{i+1:03d} - {target}',
                    }])
                except Exception as e2:
                    print(f"  Warning: Could not create inference #{i+1}: {e2}")
                    break
        print(f"  Created 20 inference records")
    else:
        print("\n[4] radar.inference not available, skipping.")

    # ── 5. Hardware Devices ──────────────────────────────────────
    if 'radar.hardware' in available_models:
        print("\n[5] Creating hardware devices...")
        existing = ex('radar.hardware', 'search', [[('name', 'like', '[Demo]')]])
        if existing:
            ex('radar.hardware', 'unlink', [existing])

        try:
            ex('radar.hardware', 'create', [{
                'name': '[Demo] Radar Simulator (Python)',
                'device_type': 'simulator',
                'state': 'connected',
                'host': '127.0.0.1',
                'port': 5555,
            }])
            print("  Simulator device created (connected)")
        except Exception as e:
            # Try with minimal fields
            try:
                ex('radar.hardware', 'create', [{
                    'name': '[Demo] Radar Simulator (Python)',
                }])
                print("  Simulator device created (minimal)")
            except Exception as e2:
                print(f"  Warning: Could not create simulator: {e2}")

        try:
            ex('radar.hardware', 'create', [{
                'name': '[Demo] TI IWR1443BOOST mmWave Sensor',
                'device_type': 'ti_mmwave',
                'state': 'disconnected',
                'host': '192.168.2.100',
                'port': 5555,
            }])
            print("  TI mmWave device created (disconnected)")
        except Exception as e:
            try:
                ex('radar.hardware', 'create', [{
                    'name': '[Demo] TI IWR1443BOOST mmWave Sensor',
                }])
                print("  TI mmWave device created (minimal)")
            except Exception as e2:
                print(f"  Warning: Could not create TI mmWave: {e2}")
    else:
        print("\n[5] radar.hardware not available, skipping.")

    # ── Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Demo data generation complete!")
    print("  Datasets:    2 (Zenodo + Synthetic, both ready)")
    print("  Experiments: 3 (SRA trained, CNN trained, CRNN draft)")
    print("  Models:      2 (SRA active, CNN inactive)")
    print("  Inferences:  20 (mixed UAV/non-UAV)")
    print("  Hardware:    2 (Simulator connected, TI mmWave disconnected)")
    print("=" * 60)


if __name__ == '__main__':
    main()
