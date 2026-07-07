import base64
import json
import logging

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RadarExperiment(models.Model):
    _name = 'radar.experiment'
    _description = '訓練實驗'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    name = fields.Char('實驗名稱', required=True, tracking=True)
    model_type = fields.Selection([
        ('sra', 'SRA (論文演算法)'),
        ('cnn', 'CNN (PyTorch)'),
        ('crnn', 'CRNN'),
        ('transformer', 'Transformer'),
    ], string='模型類型', required=True, tracking=True)
    dataset_id = fields.Many2one('radar.dataset', string='資料集', required=True,
                                 domain=[('state', '=', 'ready')])
    feature_type = fields.Selection([
        ('proposed_regularized_complex_log_fft', '論文特徵 (Complex-Log-FFT)'),
        ('spectrogram', '頻譜圖'),
        ('cepstrogram', '倒頻譜'),
        ('cvd', 'CVD'),
        ('proposed_complex_image', '論文特徵影像'),
    ], string='特徵類型', default='proposed_regularized_complex_log_fft')
    state = fields.Selection([
        ('draft', '草稿'),
        ('training', '訓練中'),
        ('trained', '已完成'),
        ('error', '錯誤'),
    ], string='狀態', default='draft', tracking=True)

    # SRA 參數
    sra_m_uav = fields.Integer('SRA m_uav', default=10,
                               help='SRA 演算法 UAV 子集大小')
    sra_m_non_uav = fields.Integer('SRA m_non_uav', default=100,
                                   help='SRA 演算法非 UAV 子集大小')
    sra_repeat = fields.Integer('重複次數', default=20,
                                help='SRA 隨機子集重複次數')

    # CNN 參數
    cnn_epochs = fields.Integer('Epochs', default=50)
    cnn_batch_size = fields.Integer('Batch Size', default=64)
    cnn_lr = fields.Float('Learning Rate', default=0.001, digits=(10, 6))

    # 結果
    accuracy = fields.Float('準確率', digits=(6, 4), readonly=True)
    precision_val = fields.Float('精確率', digits=(6, 4), readonly=True)
    recall_val = fields.Float('召回率', digits=(6, 4), readonly=True)
    f1_score = fields.Float('F1 Score', digits=(6, 4), readonly=True)
    eer = fields.Float('EER', digits=(6, 4), readonly=True)
    far_at_frr1 = fields.Float('FAR@FRR=1%', digits=(6, 4), readonly=True)
    auc = fields.Float('AUC', digits=(6, 4), readonly=True)

    model_path = fields.Char('模型路徑', readonly=True)
    confusion_matrix_img = fields.Binary('混淆矩陣', readonly=True)
    roc_curve_img = fields.Binary('ROC 曲線', readonly=True)
    det_curve_img = fields.Binary('DET 曲線', readonly=True)
    training_log = fields.Text('訓練日誌', readonly=True)
    duration_seconds = fields.Float('訓練耗時 (秒)', readonly=True)

    # 關聯模型
    trained_model_id = fields.Many2one('radar.model', string='已訓練模型', readonly=True)

    def action_train(self):
        """啟動訓練"""
        self.ensure_one()
        if self.dataset_id.state != 'ready':
            raise UserError('資料集尚未就緒，請先準備資料集。')

        self.state = 'training'
        self.message_post(body=f'開始訓練 {self.get_selection_label("model_type")} 模型...')

        try:
            if self.model_type == 'sra':
                endpoint = '/models/sra/train'
                payload = {
                    'dataset_type': self.dataset_id.dataset_type,
                    'feature_type': self.feature_type,
                    'm_uav': self.sra_m_uav,
                    'm_non_uav': self.sra_m_non_uav,
                    'repeat': self.sra_repeat,
                }
            else:
                endpoint = '/models/cnn/train'
                payload = {
                    'dataset_type': self.dataset_id.dataset_type,
                    'feature_type': self.feature_type,
                    'model_type': self.model_type,
                    'epochs': self.cnn_epochs,
                    'batch_size': self.cnn_batch_size,
                    'lr': self.cnn_lr,
                }

            result = self._call_worker(endpoint, 'POST', payload)
            self._process_train_result(result)
        except UserError:
            raise
        except Exception as e:
            self.state = 'error'
            self.training_log = str(e)
            self.message_post(body=f'訓練失敗：{e}')
            raise UserError(f'訓練失敗：{e}')

    def action_evaluate(self):
        """評估模型"""
        self.ensure_one()
        if self.state != 'trained':
            raise UserError('模型尚未訓練完成。')
        try:
            result = self._call_worker('/models/evaluate', 'POST', {
                'model_path': self.model_path,
                'dataset_type': self.dataset_id.dataset_type,
                'feature_type': self.feature_type,
            })
            self._process_eval_result(result)
        except Exception as e:
            self.message_post(body=f'評估失敗：{e}')
            raise UserError(f'評估失敗：{e}')

    def action_reset_draft(self):
        """重設為草稿"""
        self.ensure_one()
        self.state = 'draft'

    def get_selection_label(self, field_name):
        """取得 Selection 欄位的顯示標籤"""
        val = getattr(self, field_name, None)
        if not val:
            return ''
        selection = self._fields[field_name].selection
        for key, label in selection:
            if key == val:
                return label
        return val

    def _process_train_result(self, result):
        """處理訓練結果"""
        if not result:
            self.state = 'error'
            return

        vals = {'state': 'trained'}
        for key in ('accuracy', 'precision_val', 'recall_val', 'f1_score',
                     'eer', 'far_at_frr1', 'auc', 'duration_seconds', 'model_path'):
            api_key = key.replace('precision_val', 'precision').replace('recall_val', 'recall')
            if api_key in result:
                vals[key] = result[api_key]
            elif key in result:
                vals[key] = result[key]

        if result.get('training_log'):
            vals['training_log'] = result['training_log']

        # 圖表（base64 encoded）
        for img_key in ('confusion_matrix_img', 'roc_curve_img', 'det_curve_img'):
            api_key = img_key.replace('_img', '')
            img_data = result.get(img_key) or result.get(api_key)
            if img_data:
                if isinstance(img_data, str):
                    vals[img_key] = img_data
                else:
                    vals[img_key] = base64.b64encode(img_data).decode()

        self.write(vals)
        self.message_post(body=f'訓練完成！準確率：{vals.get("accuracy", "N/A")}')

        # 建立模型記錄
        if vals.get('model_path'):
            model = self.env['radar.model'].create({
                'name': f'{self.name} - {self.get_selection_label("model_type")}',
                'model_type': self.model_type,
                'experiment_id': self.id,
                'file_path': vals.get('model_path', ''),
                'eer': vals.get('eer', 0),
                'accuracy': vals.get('accuracy', 0),
            })
            self.trained_model_id = model.id

    def _process_eval_result(self, result):
        """處理評估結果"""
        if not result:
            return
        vals = {}
        for key in ('accuracy', 'precision_val', 'recall_val', 'f1_score',
                     'eer', 'far_at_frr1', 'auc'):
            api_key = key.replace('precision_val', 'precision').replace('recall_val', 'recall')
            if api_key in result:
                vals[key] = result[api_key]
            elif key in result:
                vals[key] = result[key]

        for img_key in ('confusion_matrix_img', 'roc_curve_img', 'det_curve_img'):
            api_key = img_key.replace('_img', '')
            img_data = result.get(img_key) or result.get(api_key)
            if img_data and isinstance(img_data, str):
                vals[img_key] = img_data

        if vals:
            self.write(vals)
            self.message_post(body='模型評估完成')

    def _call_worker(self, endpoint, method='GET', data=None):
        """呼叫 AI Worker API"""
        worker_url = self.env['ir.config_parameter'].sudo().get_param(
            'radar.ai_worker_url', 'http://ai-worker:8000')
        url = f'{worker_url}{endpoint}'
        try:
            if method == 'GET':
                resp = requests.get(url, timeout=30)
            elif method == 'POST':
                resp = requests.post(url, json=data or {}, timeout=600)
            else:
                raise UserError(f'不支援的 HTTP 方法：{method}')
            resp.raise_for_status()
            return resp.json() if resp.text else {}
        except requests.exceptions.ConnectionError:
            raise UserError('無法連線至 AI Worker，請確認服務是否啟動。')
        except requests.exceptions.Timeout:
            raise UserError('AI Worker 回應逾時（訓練可能需要較長時間）。')
        except requests.exceptions.HTTPError as e:
            raise UserError(f'AI Worker 回傳錯誤：{e}')
