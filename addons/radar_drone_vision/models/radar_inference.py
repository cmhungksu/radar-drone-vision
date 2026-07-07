import base64
import logging
import time

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RadarInference(models.Model):
    _name = 'radar.inference'
    _description = '推論紀錄'
    _order = 'create_date desc'

    name = fields.Char('編號', readonly=True, copy=False,
                       default=lambda self: _('新推論'))
    model_id = fields.Many2one('radar.model', string='使用模型',
                               domain=[('is_active', '=', True)])
    sample_id = fields.Char('樣本 ID')
    prediction = fields.Selection([
        ('uav', 'UAV'),
        ('non_uav', '非 UAV'),
    ], string='預測結果', readonly=True)
    confidence = fields.Float('信心分數', digits=(6, 4), readonly=True)
    ground_truth = fields.Selection([
        ('uav', 'UAV'),
        ('non_uav', '非 UAV'),
    ], string='真實標籤')
    is_correct = fields.Boolean('正確', compute='_compute_is_correct', store=True)
    spectrogram_img = fields.Binary('頻譜圖', readonly=True)
    latency_ms = fields.Float('延遲 (ms)', readonly=True)

    @api.depends('prediction', 'ground_truth')
    def _compute_is_correct(self):
        for rec in self:
            if rec.prediction and rec.ground_truth:
                rec.is_correct = rec.prediction == rec.ground_truth
            else:
                rec.is_correct = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('新推論')) == _('新推論'):
                seq = self.env['ir.sequence'].next_by_code('radar.inference')
                vals['name'] = seq or _('新推論')
        return super().create(vals_list)

    def action_run_inference(self):
        """執行推論"""
        self.ensure_one()
        if not self.model_id:
            raise UserError('請選擇模型。')
        if not self.sample_id:
            raise UserError('請輸入樣本 ID。')

        worker_url = self.env['ir.config_parameter'].sudo().get_param(
            'radar.ai_worker_url', 'http://ai-worker:8000')

        try:
            start_time = time.time()
            resp = requests.post(
                f'{worker_url}/inference/sample',
                json={
                    'sample_id': self.sample_id,
                    'model_path': self.model_id.file_path or '',
                },
                timeout=60,
            )
            elapsed_ms = (time.time() - start_time) * 1000
            resp.raise_for_status()
            result = resp.json()

            vals = {
                'latency_ms': elapsed_ms,
            }
            prediction = result.get('prediction') or result.get('label')
            if prediction:
                vals['prediction'] = prediction
            confidence = result.get('confidence') or result.get('score')
            if confidence is not None:
                vals['confidence'] = confidence

            # 頻譜圖
            spec_data = result.get('spectrogram') or result.get('spectrogram_img')
            if spec_data and isinstance(spec_data, str):
                vals['spectrogram_img'] = spec_data

            self.write(vals)

        except requests.exceptions.ConnectionError:
            raise UserError('無法連線至 AI Worker。')
        except requests.exceptions.Timeout:
            raise UserError('AI Worker 回應逾時。')
        except requests.exceptions.HTTPError as e:
            raise UserError(f'推論失敗：{e}')

    def action_load_spectrogram(self):
        """從 AI Worker 載入頻譜圖"""
        self.ensure_one()
        if not self.sample_id:
            raise UserError('請輸入樣本 ID。')

        worker_url = self.env['ir.config_parameter'].sudo().get_param(
            'radar.ai_worker_url', 'http://ai-worker:8000')
        try:
            resp = requests.get(
                f'{worker_url}/samples/{self.sample_id}/spectrogram',
                timeout=30,
            )
            resp.raise_for_status()
            content_type = resp.headers.get('content-type', '')
            if 'image' in content_type:
                self.spectrogram_img = base64.b64encode(resp.content).decode()
            else:
                result = resp.json()
                img_data = result.get('image') or result.get('spectrogram')
                if img_data:
                    self.spectrogram_img = img_data
        except Exception as e:
            raise UserError(f'載入頻譜圖失敗：{e}')
